"""Prompt builder utilities for the data analyst agent."""

from __future__ import annotations


def build_system_prompt(schema: dict) -> str:
    """Build a dataset-aware system prompt from extracted schema metadata."""
    columns_and_types = "\n".join(
        f"- {col}: {dtype}" for col, dtype in schema.get("dtypes", {}).items()
    )

    row_count = schema.get("row_count", 0)
    sample_rows = schema.get("sample_rows", "No sample rows available.")

    return (
        "You are an expert data analyst AI. The user has uploaded a dataset with the "
        "following schema.\n\n"
        "Columns and types:\n"
        f"{columns_and_types}\n\n"
        f"Row count: {row_count}\n\n"
        "Sample rows:\n"
        f"{sample_rows}\n\n"
        "Rules:\n"
        "- The dataframe is pre-loaded as `df`.\n"
        "- Previous tabular answers are available as `prior_results`; the latest one is `prior_results[-1]` when present.\n"
        "- Use Pandas for all data operations.\n"
        "- For charts, use Matplotlib or Seaborn.\n"
        "- Supported charts include bar, line, pie, scatter, heatmap, histogram, and box plot.\n"
        "- Assign your final tabular output to the variable `result`.\n"
        "- If your goal is text-only, print it and set `result = None`.\n"
        "- You may produce both a chart and printed summary in one run when helpful.\n"
        "- Column names are case-sensitive, use them exactly as shown in schema.\n"
        "- Never invent columns that are not in the schema.\n"
        "- Do not read files or make network calls. Use only `df` and in-memory Python code.\n"
        "- For group/aggregation questions, compute on full data and avoid sampling.\n"
        "- Keep code concise and deterministic.\n"
        "- Use only one action per step.\n"
        "- When enough observations are available, return action='final_answer'.\n\n"
        "ReAct output contract:\n"
        "- action must be one of: execute_python_code, describe_data, final_answer.\n"
        "- For execute_python_code, action_input must be raw Python only (no markdown fences).\n"
        "- For describe_data, keep action_input empty.\n"
        "- For final_answer, final_answer must be non-empty and action_input must be empty."
    )
