"""Custom ReAct loop implementation for Phase 2."""

from __future__ import annotations

import difflib
import json
import os
import re
from importlib import import_module
from typing import Callable, Literal

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from agent.prompt import build_system_prompt
from agent.tools import AgentTools
from executor.sandbox import SandboxExecutor

load_dotenv()


class ReActStep(BaseModel):
    thought: str = Field(description="Reasoning for this step")
    action: Literal["execute_python_code", "describe_data", "final_answer"] = Field(
        description="Single action to run in this step"
    )
    action_input: str = Field(default="", description="Code or input for the selected action")
    final_answer: str = Field(default="", description="Final answer when action is final_answer")


class DataAnalystAgent:
    """A minimal custom ReAct agent for dataframe analysis."""

    def __init__(
        self,
        df: pd.DataFrame,
        schema: dict,
        provider: str = "openai",
        history: list[dict] | None = None,
        model: str | None = None,
        max_steps: int = 5,
        max_retries: int = 3,
        status_callback: Callable[[str, str], None] | None = None,
        sandbox_executor: SandboxExecutor | None = None,
        prior_results: list[str] | None = None,
    ):
        self.df = df
        self.schema = schema
        self.provider = provider
        self.history = history or []
        self.max_steps = max_steps
        self.max_retries = max_retries
        self.status_callback = status_callback
        self.tools = AgentTools(
            df=df,
            schema=schema,
            sandbox_executor=sandbox_executor,
            prior_results=prior_results,
        )

        if provider == "anthropic":
            self.model = model or "claude-3-5-sonnet-latest"
            self.client = self._build_anthropic_client()
        else:
            self.model = model or "gpt-4o"
            self.client = self._build_openai_client()

    def _build_openai_client(self):
        instructor = import_module("instructor")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file.")
        return instructor.from_openai(OpenAI(api_key=api_key))

    def _build_anthropic_client(self):
        anthropic = import_module("anthropic")
        instructor = import_module("instructor")
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))

    def _call_llm(self, messages: list[dict]) -> ReActStep:
        if self.provider == "anthropic":
            return self.client.messages.create(
                model=self.model,
                max_tokens=1200,
                temperature=0,
                messages=messages,
                response_model=ReActStep,
            )

        return self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=messages,
            response_model=ReActStep,
        )

    @staticmethod
    def _normalize_code(code: str) -> str:
        """Strip markdown fences if the model accidentally wraps code."""
        cleaned = (code or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("python"):
                cleaned = cleaned[len("python"):].lstrip()
        return cleaned

    def _emit_status(self, label: str, state: str = "running") -> None:
        if self.status_callback is not None:
            self.status_callback(label, state)

    @staticmethod
    def _extract_column_references(code: str) -> set[str]:
        patterns = [
            r"df\s*\[\s*[\"']([^\"']+)[\"']\s*\]",
            r"groupby\(\s*[\"']([^\"']+)[\"']\s*\)",
            r"sort_values\(\s*[\"']([^\"']+)[\"']",
            r"(?:x|y|hue|values|columns|index|subset|by)\s*=\s*[\"']([^\"']+)[\"']",
        ]
        refs: set[str] = set()
        for pattern in patterns:
            refs.update(re.findall(pattern, code))

        list_arg_matches = re.findall(
            r"(?:x|y|hue|values|columns|index|subset|by)\s*=\s*\[([^\]]+)\]",
            code,
        )
        for match in list_arg_matches:
            refs.update(re.findall(r"[\"']([^\"']+)[\"']", match))

        return {ref for ref in refs if ref}

    def _validate_column_references(self, code: str) -> str | None:
        referenced = self._extract_column_references(code)
        if not referenced:
            return None

        columns = list(map(str, self.df.columns.tolist()))
        invalid = sorted(ref for ref in referenced if ref not in columns)
        if not invalid:
            return None

        suggestions = []
        for ref in invalid:
            match = difflib.get_close_matches(ref, columns, n=1, cutoff=0.5)
            if match:
                suggestions.append(f"- {ref} -> {match[0]}")
            else:
                suggestions.append(f"- {ref} -> no close match")

        suggestion_text = "\n".join(suggestions)
        valid_columns = ", ".join(columns)
        return (
            "Pre-execution column validation failed. The code referenced columns not present in the dataframe.\n"
            f"Invalid references:\n{suggestion_text}\n"
            f"Valid columns are: {valid_columns}\n"
            "Rewrite the code using only exact column names from the dataframe schema."
        )

    def run(self, user_query: str) -> dict:
        system_prompt = build_system_prompt(self.schema)
        tool_guide = (
            "Available actions:\n"
            "1) describe_data: use when you need dataset statistics/schema details.\n"
            "2) execute_python_code: action_input must be runnable Python code.\n"
            "3) final_answer: use after you have enough observations.\n\n"
            "Execution quality requirements:\n"
            "- Use exactly one action per step.\n"
            "- Do not use markdown fences in action_input.\n"
            "- If execution returns stderr, fix code and run execute_python_code again.\n"
            "- For follow-up questions about a prior table, use `prior_results[-1]` when available.\n"
            "- Prefer describe_data before code when schema ambiguity exists.\n"
            "- Only call final_answer when you have an observation from a tool.\n\n"
            "Always return valid structured fields."
        )

        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{tool_guide}"},
        ]

        for turn in self.history:
            role = turn.get("role")
            content = str(turn.get("content", ""))
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_query})

        trace: list[dict] = []
        retry_events: list[dict] = []
        last_exec: dict | None = None
        execution_attempts = 0

        self._emit_status("Running analysis...", "running")

        for step_num in range(1, self.max_steps + 1):
            step = self._call_llm(messages)
            normalized_input = self._normalize_code(step.action_input)
            trace.append(
                {
                    "step": step_num,
                    "thought": step.thought,
                    "action": step.action,
                    "action_input": normalized_input,
                }
            )

            if step.action == "final_answer":
                final = step.final_answer.strip() or "Analysis complete."
                self._emit_status("Analysis complete", "complete")
                return {
                    "final_answer": final,
                    "trace": trace,
                    "execution": last_exec,
                    "retry_events": retry_events,
                }

            if step.action == "describe_data":
                observation = self.tools.describe_data()
                trace[-1]["observation"] = observation[:1200]
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"Action: describe_data\nThought: {step.thought}",
                    }
                )
                messages.append({"role": "user", "content": f"Observation:\n{observation}"})
                continue

            if step.action == "execute_python_code":
                if not normalized_input:
                    trace[-1]["observation"] = (
                        "execute_python_code was returned without any runnable code."
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "Observation: action_input for execute_python_code was empty. Provide runnable Python code.",
                        }
                    )
                    continue

                validation_feedback = self._validate_column_references(normalized_input)
                if validation_feedback:
                    trace.append(
                        {
                            "step": step_num,
                            "thought": "Column validation intercepted invalid references before execution.",
                            "action": "column_validation",
                            "action_input": normalized_input,
                            "observation": validation_feedback,
                        }
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": f"Action: execute_python_code\nThought: {step.thought}\nCode:\n{normalized_input}",
                        }
                    )
                    messages.append({"role": "user", "content": f"Observation:\n{validation_feedback}"})
                    continue

                execution_attempts += 1
                if execution_attempts == 1:
                    self._emit_status("Executing generated Python code...", "running")
                last_exec = self.tools.execute_python_code(normalized_input)
                outputs = last_exec.get("outputs", {})
                observation = {
                    "stdout": last_exec.get("stdout", ""),
                    "stderr": last_exec.get("stderr", ""),
                    "result_type": outputs.get("result_type", "none"),
                    "result_preview": str(outputs.get("result", ""))[:500],
                    "has_figures": bool(outputs.get("figures", [])),
                    "figure_count": len(outputs.get("figures", [])),
                }
                trace[-1]["attempt"] = execution_attempts
                trace[-1]["observation"] = json.dumps(observation, indent=2)
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"Action: execute_python_code\nThought: {step.thought}\nCode:\n{normalized_input}",
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": "Observation:\n" + json.dumps(observation, indent=2),
                    }
                )

                stderr = last_exec.get("stderr", "").strip()
                if stderr:
                    retry_events.append(
                        {
                            "attempt": execution_attempts,
                            "error": stderr,
                            "code": normalized_input,
                        }
                    )
                    trace.append(
                        {
                            "step": step_num,
                            "thought": "Execution failed and a retry will be requested.",
                            "action": "execution_error",
                            "action_input": normalized_input,
                            "attempt": execution_attempts,
                            "observation": stderr,
                        }
                    )
                    if execution_attempts >= self.max_retries:
                        failure = (
                            f"Analysis failed after {self.max_retries} attempts. Please rephrase your question."
                        )
                        self._emit_status(failure, "error")
                        return {
                            "final_answer": failure,
                            "trace": trace,
                            "execution": last_exec,
                            "retry_events": retry_events,
                        }

                    next_attempt = execution_attempts + 1
                    self._emit_status(
                        f"Retrying... (attempt {next_attempt}/{self.max_retries})",
                        "running",
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The previous code failed on attempt {execution_attempts} with this error:\n"
                                f"{stderr}\n"
                                "Fix the error and rewrite the full Python code."
                            ),
                        }
                    )
                else:
                    self._emit_status("Execution succeeded", "running")
                continue

            messages.append(
                {
                    "role": "user",
                    "content": "Observation: Unknown action returned. Choose a valid action.",
                }
            )

        fallback = "I could not complete the analysis in the allowed steps. Please rephrase your question."
        self._emit_status(fallback, "error")
        return {
            "final_answer": fallback,
            "trace": trace,
            "execution": last_exec,
            "retry_events": retry_events,
        }
