"""Local subprocess executor for generated Python analysis code."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

TIMEOUT_SECONDS = 30

_RUNNER_SCRIPT = r'''
import base64
import io
import json
import pickle
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
try:
    import seaborn as sns
except Exception:
    sns = None


def _serialize_result(value):
    if value is None:
        return {"result_type": "none", "result": None}
    if isinstance(value, pd.DataFrame):
        return {
            "result_type": "dataframe",
            "result": value.to_json(orient="split", date_format="iso"),
        }
    if isinstance(value, pd.Series):
        frame = value.to_frame(name=value.name or "value").reset_index()
        return {
            "result_type": "dataframe",
            "result": frame.to_json(orient="split", date_format="iso"),
        }

    try:
        return {"result_type": "json", "result": json.dumps(value, default=str)}
    except Exception:
        return {"result_type": "text", "result": str(value)}


pickle_path, code_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]
prior_results_path = sys.argv[4] if len(sys.argv) > 4 else ""

with open(pickle_path, "rb") as f:
    df = pickle.load(f)

with open(code_path, "r", encoding="utf-8") as f:
    code = f.read()

prior_results = []
if prior_results_path and os.path.exists(prior_results_path):
    try:
        with open(prior_results_path, "r", encoding="utf-8") as f:
            prior_payload = json.load(f)
        for item in prior_payload:
            try:
                prior_results.append(pd.read_json(io.StringIO(item), orient="split"))
            except Exception:
                continue
    except Exception:
        prior_results = []

namespace = {
    "pd": pd,
    "np": np,
    "plt": plt,
    "sns": sns,
    "df": df,
    "prior_results": prior_results,
    "result": None,
}

stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()

try:
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exec(code, namespace)
except Exception:
    stderr_buffer.write(traceback.format_exc())

figures = []
for fig_num in plt.get_fignums():
    fig = plt.figure(fig_num)
    img = io.BytesIO()
    fig.savefig(img, format="png", bbox_inches="tight")
    img.seek(0)
    figures.append(base64.b64encode(img.read()).decode("utf-8"))
plt.close("all")

payload = {
    "stdout": stdout_buffer.getvalue(),
    "stderr": stderr_buffer.getvalue(),
    "outputs": {
        **_serialize_result(namespace.get("result")),
        "figures": figures,
    },
}

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(payload, f)
'''


def run_code(code: str, df: pd.DataFrame, prior_results: list[str] | None = None) -> dict:
    """Execute code in a subprocess with a preloaded dataframe named `df`."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pickle_path = tmp_path / "df.pkl"
        code_path = tmp_path / "analysis.py"
        output_path = tmp_path / "output.json"
        runner_path = tmp_path / "runner.py"
        prior_path = tmp_path / "prior_results.json"

        df.to_pickle(pickle_path)
        code_path.write_text(code, encoding="utf-8")
        runner_path.write_text(_RUNNER_SCRIPT, encoding="utf-8")
        prior_path.write_text(json.dumps(prior_results or []), encoding="utf-8")

        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(runner_path),
                    str(pickle_path),
                    str(code_path),
                    str(output_path),
                    str(prior_path),
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmpdir,
                env={**os.environ},
            )
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {TIMEOUT_SECONDS} seconds.",
                "outputs": {"result_type": "none", "result": None, "figures": []},
            }

        if not output_path.exists():
            stderr = completed.stderr.strip() or "Execution failed before producing output."
            return {
                "stdout": completed.stdout,
                "stderr": stderr,
                "outputs": {"result_type": "none", "result": None, "figures": []},
            }

        try:
            return json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "stdout": completed.stdout,
                "stderr": "Executor returned invalid JSON output.",
                "outputs": {"result_type": "none", "result": None, "figures": []},
            }
