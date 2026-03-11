"""Optional E2B sandbox executor with automatic local fallback."""

from __future__ import annotations

import base64
import io
import json
import os
from typing import Any

import pandas as pd

from executor.local_exec import run_code as run_code_local


class SandboxExecutor:
    """Runs code in E2B when available; falls back to local subprocess otherwise."""

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.getenv("E2B_API_KEY", "")).strip()
        self._sandbox: Any | None = None
        self._df: pd.DataFrame | None = None
        self.last_error: str | None = None

        if not self.api_key:
            self.last_error = "E2B_API_KEY is not set. Using local executor."
            return

        try:
            from e2b_code_interpreter import Sandbox  # type: ignore

            self._sandbox = Sandbox(api_key=self.api_key)
        except Exception as exc:
            self._sandbox = None
            self.last_error = f"Failed to initialize E2B sandbox: {exc}"

    @property
    def is_available(self) -> bool:
        return self._sandbox is not None

    def set_dataframe(self, df: pd.DataFrame) -> None:
        """Bind dataframe for the current session and upload to sandbox if available."""
        self._df = df
        if not self.is_available:
            return

        csv_text = df.to_csv(index=False)
        bootstrap_code = (
            "import pandas as pd\n"
            "df = pd.read_csv('/tmp/session_df.csv')\n"
            "result = None\n"
            "print('df_loaded')"
        )

        try:
            files = getattr(self._sandbox, "files", None)
            if files is None or not hasattr(files, "write"):
                raise RuntimeError("E2B files.write API not available in this SDK version")
            files.write("/tmp/session_df.csv", csv_text)
            self._run_raw(bootstrap_code)
        except Exception as exc:
            self.last_error = f"E2B upload/bootstrap failed: {exc}"

    def _extract_text(self, obj: Any) -> str:
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, list):
            return "\n".join(self._extract_text(x) for x in obj)

        for attr in ("stdout", "stderr", "text", "message", "content"):
            if hasattr(obj, attr):
                return self._extract_text(getattr(obj, attr))

        logs = getattr(obj, "logs", None)
        if logs is not None:
            return self._extract_text(logs)

        return str(obj)

    def _run_raw(self, code: str) -> Any:
        if not self.is_available:
            raise RuntimeError("Sandbox is not available")

        for method_name in ("run_code", "run_python", "exec_cell"):
            if hasattr(self._sandbox, method_name):
                return getattr(self._sandbox, method_name)(code)

        raise RuntimeError("No supported run method found on E2B sandbox instance")

    def _run_e2b(self, code: str, prior_results: list[str] | None = None) -> dict:
        prior_results = prior_results or []
        wrapped_code = f"""
import base64
import io
import json
import traceback

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
try:
    import seaborn as sns
except Exception:
    sns = None

if 'df' not in globals():
    df = pd.read_csv('/tmp/session_df.csv')

prior_results = []
for payload in {json.dumps(prior_results)}:
    try:
        prior_results.append(pd.read_json(io.StringIO(payload), orient='split'))
    except Exception:
        pass

result = None
_stdout = io.StringIO()
_stderr = io.StringIO()
try:
    with io.StringIO() as _local_stdout, io.StringIO() as _local_stderr:
        import contextlib
        with contextlib.redirect_stdout(_local_stdout), contextlib.redirect_stderr(_local_stderr):
            exec({json.dumps(code)}, globals())
        _stdout.write(_local_stdout.getvalue())
        _stderr.write(_local_stderr.getvalue())
except Exception:
    _stderr.write(traceback.format_exc())

figures = []
for fig_num in plt.get_fignums():
    fig = plt.figure(fig_num)
    img = io.BytesIO()
    fig.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    figures.append(base64.b64encode(img.read()).decode('utf-8'))
plt.close('all')

def _serialize_result(value):
    if value is None:
        return {{'result_type': 'none', 'result': None}}
    if isinstance(value, pd.DataFrame):
        return {{'result_type': 'dataframe', 'result': value.to_json(orient='split', date_format='iso')}}
    if isinstance(value, pd.Series):
        frame = value.to_frame(name=value.name or 'value').reset_index()
        return {{'result_type': 'dataframe', 'result': frame.to_json(orient='split', date_format='iso')}}
    try:
        return {{'result_type': 'json', 'result': json.dumps(value, default=str)}}
    except Exception:
        return {{'result_type': 'text', 'result': str(value)}}

payload = {{
    'stdout': _stdout.getvalue(),
    'stderr': _stderr.getvalue(),
    'outputs': {{
        **_serialize_result(globals().get('result')),
        'figures': figures,
    }},
}}
print(json.dumps(payload))
"""
        raw = self._run_raw(wrapped_code)
        text = self._extract_text(raw).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Empty sandbox response")

        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

        raise RuntimeError(f"Could not parse sandbox JSON output: {text[:400]}")

    def run_code(self, code: str, prior_results: list[str] | None = None) -> dict:
        """Execute analysis code in sandbox when available; otherwise local executor."""
        if self._df is None:
            raise ValueError("Dataframe not initialized in executor session.")

        if not self.is_available:
            return run_code_local(code=code, df=self._df, prior_results=prior_results)

        try:
            return self._run_e2b(code=code, prior_results=prior_results)
        except Exception as exc:
            self.last_error = f"Sandbox execution failed, using local executor: {exc}"
            return run_code_local(code=code, df=self._df, prior_results=prior_results)
