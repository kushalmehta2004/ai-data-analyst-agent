"""Tool implementations used by the custom ReAct loop."""

from __future__ import annotations

import pandas as pd

from executor.local_exec import run_code
from executor.sandbox import SandboxExecutor


class AgentTools:
    """Tools callable by the agent during reasoning."""

    def __init__(
        self,
        df: pd.DataFrame,
        schema: dict,
        sandbox_executor: SandboxExecutor | None = None,
        prior_results: list[str] | None = None,
    ):
        self.df = df
        self.schema = schema
        self.sandbox_executor = sandbox_executor
        self.prior_results = prior_results or []

    def execute_python_code(self, code: str) -> dict:
        if self.sandbox_executor is not None:
            return self.sandbox_executor.run_code(code=code, prior_results=self.prior_results)
        return run_code(code=code, df=self.df, prior_results=self.prior_results)

    def describe_data(self) -> str:
        describe_df = self.df.describe(include="all").fillna("")
        try:
            describe_text = describe_df.to_markdown()
        except Exception:
            describe_text = describe_df.to_string()
        return (
            "Schema summary:\n"
            f"Columns: {self.schema.get('columns', [])}\n"
            f"Dtypes: {self.schema.get('dtypes', {})}\n"
            f"Row count: {self.schema.get('row_count', 0)}\n\n"
            "Descriptive statistics:\n"
            f"{describe_text}"
        )
