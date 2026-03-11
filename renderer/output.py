"""Utilities for rendering execution outputs in the Streamlit UI."""

from __future__ import annotations

import base64
import json
from io import StringIO
from typing import Any

import pandas as pd


def render_dataframe(df: pd.DataFrame) -> str:
    """Render a dataframe as styled HTML for chat display."""
    styled = df.copy()
    return styled.to_html(
        index=False,
        classes="agent-table",
        border=0,
        justify="left",
        escape=False,
    )


def render_chart(chart_payload: bytes | str) -> bytes:
    """Normalize chart payloads to raw PNG bytes."""
    if isinstance(chart_payload, bytes):
        return chart_payload
    return base64.b64decode(chart_payload)


def detect_output_type(exec_result: dict) -> str:
    """Classify an execution result for routing in the UI."""
    outputs = exec_result.get("outputs", {})
    has_table = outputs.get("result_type") == "dataframe" and bool(outputs.get("result"))
    has_chart = bool(outputs.get("figures", []))
    has_text = bool(exec_result.get("stdout", "").strip()) or (
        outputs.get("result_type") in {"json", "text"} and bool(outputs.get("result"))
    )

    active_types = sum([has_table, has_chart, has_text])
    if active_types > 1:
        return "mixed"
    if has_table:
        return "table"
    if has_chart:
        return "chart"
    return "text"


def render_output(exec_result: dict) -> dict[str, Any]:
    """Convert executor output into UI-renderable items."""
    outputs = exec_result.get("outputs", {})
    result_type = outputs.get("result_type")
    result_payload = outputs.get("result")
    items: list[dict[str, Any]] = []

    stdout = exec_result.get("stdout", "").strip()
    if stdout:
        items.append({"type": "text", "content": stdout, "format": "stdout"})

    stderr = exec_result.get("stderr", "").strip()
    if stderr:
        items.append({"type": "error", "content": stderr})

    if result_type == "dataframe" and result_payload:
        df = pd.read_json(StringIO(result_payload), orient="split")
        items.append(
            {
                "type": "table",
                "content": render_dataframe(df),
                "dataframe_json": result_payload,
            }
        )
    elif result_payload and result_type in {"json", "text"}:
        if result_type == "json":
            try:
                parsed = json.loads(result_payload)
                text_content = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                text_content = str(result_payload)
        else:
            text_content = str(result_payload)
        items.append({"type": "text", "content": text_content, "format": result_type})

    for figure in outputs.get("figures", []):
        items.append({"type": "chart", "content": render_chart(figure)})

    return {
        "type": detect_output_type(exec_result),
        "content": items,
    }
