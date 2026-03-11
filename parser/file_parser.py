"""
parser/file_parser.py
Handles ingestion of CSV, Excel (.xlsx), and JSON files.
Extracts schema metadata for injection into the LLM system prompt.
"""

from __future__ import annotations

import io
import json
from typing import Optional

import numpy as np
import pandas as pd

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def _to_markdown_safe(df: pd.DataFrame, *, index: bool = True) -> str:
    """Render markdown when tabulate is installed, otherwise plain table text."""
    try:
        return df.to_markdown(index=index)
    except Exception:
        return df.to_string(index=index)


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_file(
    uploaded_file,
    sheet_name: Optional[str] = None,
) -> pd.DataFrame:
    """
    Parse an uploaded Streamlit file object into a Pandas DataFrame.

    Supports: .csv, .xlsx / .xls, .json

    Args:
        uploaded_file: Streamlit UploadedFile object.
        sheet_name:    For Excel files with multiple sheets, the sheet to load.
                       If None and there are multiple sheets, the first is used.

    Returns:
        pd.DataFrame

    Raises:
        ValueError: If file type is unsupported, file exceeds size limit,
                    or the file cannot be parsed.
    """
    # --- Size guard -----------------------------------------------------------
    file_bytes = uploaded_file.getvalue()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        raise ValueError(
            f"File size ({size_mb:.1f} MB) exceeds the {MAX_FILE_SIZE_MB} MB limit. "
            "Please upload a smaller file."
        )

    filename: str = uploaded_file.name.lower()
    buf = io.BytesIO(file_bytes)

    try:
        if filename.endswith(".csv"):
            df = _load_csv(buf)

        elif filename.endswith((".xlsx", ".xls")):
            df = _load_excel(buf, sheet_name=sheet_name)

        elif filename.endswith(".json"):
            df = _load_json(buf)

        else:
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "unknown"
            raise ValueError(
                f"Unsupported file type '.{ext}'. "
                "Please upload a CSV, Excel (.xlsx), or JSON file."
            )
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not parse file '{uploaded_file.name}': {e}") from e

    if df.empty:
        raise ValueError("The uploaded file appears to be empty.")

    # Sanitise column names (strip leading/trailing whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    return df


def _load_csv(buf: io.BytesIO) -> pd.DataFrame:
    """Try UTF-8 first, fall back to latin-1 for files with special characters."""
    try:
        buf.seek(0)
        return pd.read_csv(buf, encoding="utf-8")
    except UnicodeDecodeError:
        buf.seek(0)
        return pd.read_csv(buf, encoding="latin-1")


def _load_excel(buf: io.BytesIO, sheet_name: Optional[str] = None) -> pd.DataFrame:
    buf.seek(0)
    xl = pd.ExcelFile(buf)
    target = sheet_name if sheet_name and sheet_name in xl.sheet_names else xl.sheet_names[0]
    buf.seek(0)
    return pd.read_excel(buf, sheet_name=target)


def _load_json(buf: io.BytesIO) -> pd.DataFrame:
    buf.seek(0)
    raw = json.loads(buf.read().decode("utf-8"))
    # Handle both array-of-objects and records-style JSON
    if isinstance(raw, list):
        return pd.DataFrame(raw)
    elif isinstance(raw, dict):
        # Try orient='split', 'records', 'index', or wrap scalar dict
        try:
            return pd.DataFrame(raw)
        except ValueError:
            return pd.DataFrame([raw])
    raise ValueError("JSON must be an array of objects or a records-style dict.")


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------

def extract_schema(df: pd.DataFrame) -> dict:
    """
    Extract metadata from a DataFrame for injection into the LLM system prompt.

    Returns a dict with:
        - columns:        list of column names
        - dtypes:         dict {column: dtype_string}
        - row_count:      int
        - col_count:      int
        - sample_rows:    markdown table string of the first 5 rows
        - numeric_stats:  markdown table string of df.describe() for numeric cols
        - missing_info:   dict {column: missing_count} for columns with nulls
    """
    col_dtypes = {col: str(df[col].dtype) for col in df.columns}

    sample_md = _to_markdown_safe(df.head(5), index=False)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_stats_md = (
        _to_markdown_safe(df[numeric_cols].describe().round(2))
        if numeric_cols
        else "No numeric columns."
    )

    missing = {
        col: int(df[col].isna().sum())
        for col in df.columns
        if df[col].isna().sum() > 0
    }

    return {
        "columns": list(df.columns),
        "dtypes": col_dtypes,
        "row_count": len(df),
        "col_count": len(df.columns),
        "sample_rows": sample_md,
        "numeric_stats": numeric_stats_md,
        "missing_info": missing,
    }


def get_excel_sheet_names(uploaded_file) -> list[str]:
    """
    Return list of sheet names for an Excel file.
    Returns an empty list for non-Excel files.
    """
    filename: str = uploaded_file.name.lower()
    if not filename.endswith((".xlsx", ".xls")):
        return []
    buf = io.BytesIO(uploaded_file.getvalue())
    xl = pd.ExcelFile(buf)
    return xl.sheet_names
