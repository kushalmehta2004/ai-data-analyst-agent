"""
tests/test_agent.py
Phase 1: Unit tests for file_parser module.
"""

import io
import json

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from parser.file_parser import extract_schema, get_excel_sheet_names, load_file


# ---------------------------------------------------------------------------
# Helpers — build fake UploadedFile objects
# ---------------------------------------------------------------------------

class FakeUploadedFile:
    """Minimal mock of Streamlit's UploadedFile."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def make_csv_file(df: pd.DataFrame, name: str = "test.csv") -> FakeUploadedFile:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return FakeUploadedFile(name, buf.getvalue().encode("utf-8"))


def make_json_file(data: list, name: str = "test.json") -> FakeUploadedFile:
    return FakeUploadedFile(name, json.dumps(data).encode("utf-8"))


def make_excel_file(df: pd.DataFrame, name: str = "test.xlsx", sheet: str = "Sheet1") -> FakeUploadedFile:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet, index=False)
    return FakeUploadedFile(name, buf.getvalue())


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_DF = pd.DataFrame({
    "Name": ["Alice", "Bob", "Charlie"],
    "Age": [30, 25, 35],
    "Revenue": [10000.0, 8500.0, 12000.0],
    "Region": ["East", "West", "East"],
})


# ---------------------------------------------------------------------------
# load_file — CSV
# ---------------------------------------------------------------------------

class TestLoadCSV:
    def test_basic_csv_load(self):
        f = make_csv_file(SAMPLE_DF)
        df = load_file(f)
        assert list(df.columns) == list(SAMPLE_DF.columns)
        assert len(df) == 3

    def test_csv_column_names_stripped(self):
        """Columns with leading/trailing spaces should be stripped."""
        raw = b" Name , Age \nAlice,30\nBob,25\n"
        f = FakeUploadedFile("test.csv", raw)
        df = load_file(f)
        assert "Name" in df.columns
        assert "Age" in df.columns

    def test_csv_latin1_encoding(self):
        """CSV with latin-1 characters should load without error."""
        raw = "Name,City\nMüller,München\n".encode("latin-1")
        f = FakeUploadedFile("test.csv", raw)
        df = load_file(f)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# load_file — Excel
# ---------------------------------------------------------------------------

class TestLoadExcel:
    def test_basic_excel_load(self):
        f = make_excel_file(SAMPLE_DF)
        df = load_file(f)
        assert list(df.columns) == list(SAMPLE_DF.columns)
        assert len(df) == 3

    def test_excel_sheet_selection(self):
        """Sheet selection should load the correct sheet."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            SAMPLE_DF.to_excel(writer, sheet_name="Sales", index=False)
            pd.DataFrame({"X": [1, 2]}).to_excel(writer, sheet_name="Other", index=False)
        f = FakeUploadedFile("multi.xlsx", buf.getvalue())

        df_sales = load_file(f, sheet_name="Sales")
        assert list(df_sales.columns) == list(SAMPLE_DF.columns)

        df_other = load_file(f, sheet_name="Other")
        assert list(df_other.columns) == ["X"]

    def test_excel_defaults_to_first_sheet(self):
        """If no sheet_name provided + multiple sheets, load first."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            SAMPLE_DF.to_excel(writer, sheet_name="First", index=False)
            pd.DataFrame({"X": [1]}).to_excel(writer, sheet_name="Second", index=False)
        f = FakeUploadedFile("multi.xlsx", buf.getvalue())
        df = load_file(f)
        assert list(df.columns) == list(SAMPLE_DF.columns)


# ---------------------------------------------------------------------------
# load_file — JSON
# ---------------------------------------------------------------------------

class TestLoadJSON:
    def test_basic_json_array(self):
        data = [{"A": 1, "B": "x"}, {"A": 2, "B": "y"}]
        f = make_json_file(data)
        df = load_file(f)
        assert list(df.columns) == ["A", "B"]
        assert len(df) == 2

    def test_json_dict_of_lists(self):
        data = {"A": [1, 2], "B": ["x", "y"]}
        f = FakeUploadedFile("test.json", json.dumps(data).encode())
        df = load_file(f)
        assert len(df) == 2


# ---------------------------------------------------------------------------
# load_file — Error cases
# ---------------------------------------------------------------------------

class TestLoadFileErrors:
    def test_unsupported_file_type(self):
        f = FakeUploadedFile("data.txt", b"col1,col2\n1,2")
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_file(f)

    def test_empty_csv(self):
        f = FakeUploadedFile("empty.csv", b"")
        with pytest.raises(ValueError):
            load_file(f)

    def test_file_too_large(self):
        # Mock getvalue() to return a bytes-like object that reports > 50MB
        # without actually allocating 50MB in memory
        mock_data = MagicMock()
        mock_data.__len__ = lambda self: (50 * 1024 * 1024) + 1
        f = MagicMock()
        f.name = "large.csv"
        f.getvalue.return_value = mock_data
        with pytest.raises(ValueError, match="exceeds the 50 MB limit"):
            load_file(f)


# ---------------------------------------------------------------------------
# extract_schema
# ---------------------------------------------------------------------------

class TestExtractSchema:
    def test_returns_expected_keys(self):
        schema = extract_schema(SAMPLE_DF)
        assert "columns" in schema
        assert "dtypes" in schema
        assert "row_count" in schema
        assert "col_count" in schema
        assert "sample_rows" in schema
        assert "numeric_stats" in schema
        assert "missing_info" in schema

    def test_correct_row_and_col_counts(self):
        schema = extract_schema(SAMPLE_DF)
        assert schema["row_count"] == 3
        assert schema["col_count"] == 4

    def test_correct_columns(self):
        schema = extract_schema(SAMPLE_DF)
        assert schema["columns"] == list(SAMPLE_DF.columns)

    def test_missing_info_detected(self):
        df_with_nulls = SAMPLE_DF.copy()
        df_with_nulls.loc[0, "Age"] = np.nan
        schema = extract_schema(df_with_nulls)
        assert "Age" in schema["missing_info"]
        assert schema["missing_info"]["Age"] == 1

    def test_no_false_missing_reported(self):
        schema = extract_schema(SAMPLE_DF)
        assert schema["missing_info"] == {}

    def test_sample_rows_is_string(self):
        schema = extract_schema(SAMPLE_DF)
        assert isinstance(schema["sample_rows"], str)
        assert len(schema["sample_rows"]) > 0

    def test_numeric_stats_covers_numeric_cols(self):
        schema = extract_schema(SAMPLE_DF)
        # Should include Age and Revenue stats
        assert "Age" in schema["numeric_stats"] or "count" in schema["numeric_stats"]


# ---------------------------------------------------------------------------
# get_excel_sheet_names
# ---------------------------------------------------------------------------

class TestGetExcelSheetNames:
    def test_returns_sheet_names(self):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            SAMPLE_DF.to_excel(writer, sheet_name="Alpha", index=False)
            SAMPLE_DF.to_excel(writer, sheet_name="Beta", index=False)
        f = FakeUploadedFile("multi.xlsx", buf.getvalue())
        names = get_excel_sheet_names(f)
        assert "Alpha" in names
        assert "Beta" in names

    def test_returns_empty_for_csv(self):
        f = make_csv_file(SAMPLE_DF)
        assert get_excel_sheet_names(f) == []
