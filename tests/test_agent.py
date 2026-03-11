"""
tests/test_agent.py
Phase 1: Unit tests for file_parser module.
"""

import io
import importlib.util
import json

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from agent.prompt import build_system_prompt
from agent.core import DataAnalystAgent, ReActStep
from agent.memory import SessionMemory
from agent.tools import AgentTools
from executor.local_exec import run_code
from parser.file_parser import extract_schema, get_excel_sheet_names, load_file
from renderer.output import detect_output_type, render_chart, render_dataframe, render_output

HAS_OPENPYXL = importlib.util.find_spec("openpyxl") is not None


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

@pytest.mark.skipif(not HAS_OPENPYXL, reason="openpyxl is not installed")
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

@pytest.mark.skipif(not HAS_OPENPYXL, reason="openpyxl is not installed")
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


# ---------------------------------------------------------------------------
# Phase 2 - prompt and execution
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_build_system_prompt_includes_schema(self):
        schema = extract_schema(SAMPLE_DF)
        prompt = build_system_prompt(schema)
        assert "Columns and types" in prompt
        assert "Revenue" in prompt
        assert "Row count: 3" in prompt
        assert "dataframe is pre-loaded as `df`" in prompt
        assert "prior_results" in prompt


class TestLocalExecutor:
    def test_run_code_returns_dataframe_result(self):
        code = "result = df.groupby('Region', as_index=False)['Revenue'].mean()"
        output = run_code(code=code, df=SAMPLE_DF)
        assert output["stderr"] == ""
        assert output["outputs"]["result_type"] == "dataframe"

    def test_run_code_captures_stdout(self):
        code = "print('hello from executor')\nresult = None"
        output = run_code(code=code, df=SAMPLE_DF)
        assert "hello from executor" in output["stdout"]

    def test_run_code_captures_matplotlib_figures(self):
        code = (
            "import matplotlib.pyplot as plt\n"
            "plt.figure()\n"
            "df['Revenue'].plot(kind='bar')\n"
            "result = None"
        )
        output = run_code(code=code, df=SAMPLE_DF)
        assert output["stderr"] == ""
        assert len(output["outputs"].get("figures", [])) >= 1

    def test_run_code_exposes_prior_results(self):
        prior_df = SAMPLE_DF.groupby("Region", as_index=False)["Revenue"].sum()
        code = "result = prior_results[-1]"
        output = run_code(
            code=code,
            df=SAMPLE_DF,
            prior_results=[prior_df.to_json(orient="split")],
        )
        assert output["stderr"] == ""
        assert output["outputs"]["result_type"] == "dataframe"


class TestAgentTools:
    def test_describe_data_contains_schema(self):
        schema = extract_schema(SAMPLE_DF)
        tools = AgentTools(df=SAMPLE_DF, schema=schema)
        description = tools.describe_data()
        assert "Schema summary" in description
        assert "Row count" in description
        assert "Revenue" in description


class TestSessionMemory:
    def test_sliding_window_keeps_recent_messages(self):
        memory = SessionMemory(max_messages=3)
        memory.add_turn("user", "q1")
        memory.add_turn("assistant", "a1")
        memory.add_turn("user", "q2")
        memory.add_turn("assistant", "a2")

        history = memory.get_history()
        assert len(history) == 3
        assert history[0]["content"] == "a1"
        assert history[-1]["content"] == "a2"


class TestRendererOutput:
    def test_render_dataframe_returns_html_table(self):
        html = render_dataframe(SAMPLE_DF.head(2))
        assert "<table" in html
        assert "Alice" in html

    def test_render_chart_decodes_base64(self):
        raw = b"fake-png-bytes"
        decoded = render_chart(raw)
        assert decoded == raw
        assert isinstance(decoded, bytes)

    def test_detect_output_type_table(self):
        exec_result = {
            "stdout": "",
            "stderr": "",
            "outputs": {
                "result_type": "dataframe",
                "result": SAMPLE_DF.to_json(orient="split"),
                "figures": [],
            },
        }
        assert detect_output_type(exec_result) == "table"

    def test_detect_output_type_chart(self):
        exec_result = {
            "stdout": "",
            "stderr": "",
            "outputs": {
                "result_type": "none",
                "result": None,
                "figures": ["ZmFrZQ=="],
            },
        }
        assert detect_output_type(exec_result) == "chart"

    def test_render_output_supports_mixed_content(self):
        exec_result = {
            "stdout": "Summary line",
            "stderr": "",
            "outputs": {
                "result_type": "dataframe",
                "result": SAMPLE_DF.head(1).to_json(orient="split"),
                "figures": ["ZmFrZQ=="],
            },
        }
        rendered = render_output(exec_result)
        assert rendered["type"] == "mixed"
        item_types = [item["type"] for item in rendered["content"]]
        assert "text" in item_types
        assert "table" in item_types
        assert "chart" in item_types


class TestSelfCorrectionLoop:
    def _make_agent(self, monkeypatch):
        monkeypatch.setattr(DataAnalystAgent, "_build_openai_client", lambda self: object())
        schema = extract_schema(SAMPLE_DF)
        return DataAnalystAgent(df=SAMPLE_DF, schema=schema)

    def test_column_validation_intercepts_hallucinated_column(self, monkeypatch):
        agent = self._make_agent(monkeypatch)
        steps = iter(
            [
                ReActStep(
                    thought="Use a revenue column.",
                    action="execute_python_code",
                    action_input="result = df['Revenu'].sum()",
                    final_answer="",
                ),
                ReActStep(
                    thought="Use the exact column name.",
                    action="execute_python_code",
                    action_input="result = df[['Revenue']].sum().to_frame().reset_index()",
                    final_answer="",
                ),
                ReActStep(
                    thought="The calculation succeeded.",
                    action="final_answer",
                    action_input="",
                    final_answer="Revenue total computed successfully.",
                ),
            ]
        )
        monkeypatch.setattr(agent, "_call_llm", lambda messages: next(steps))
        executed_code: list[str] = []

        def fake_execute(code: str) -> dict:
            executed_code.append(code)
            return {
                "stdout": "",
                "stderr": "",
                "outputs": {
                    "result_type": "dataframe",
                    "result": SAMPLE_DF[["Revenue"]].sum().to_frame().reset_index().to_json(orient="split"),
                    "figures": [],
                },
            }

        monkeypatch.setattr(agent.tools, "execute_python_code", fake_execute)

        response = agent.run("What is total revenue?")

        assert response["final_answer"] == "Revenue total computed successfully."
        assert executed_code == ["result = df[['Revenue']].sum().to_frame().reset_index()"]
        assert any(item["action"] == "column_validation" for item in response["trace"])

    def test_retry_after_invalid_pandas_syntax(self, monkeypatch):
        agent = self._make_agent(monkeypatch)
        steps = iter(
            [
                ReActStep(
                    thought="Try a groupby.",
                    action="execute_python_code",
                    action_input="result = df.groupby('Region')['Revenue'].mean(",
                    final_answer="",
                ),
                ReActStep(
                    thought="Fix the syntax.",
                    action="execute_python_code",
                    action_input="result = df.groupby('Region', as_index=False)['Revenue'].mean()",
                    final_answer="",
                ),
                ReActStep(
                    thought="Now answer.",
                    action="final_answer",
                    action_input="",
                    final_answer="Average revenue by region computed.",
                ),
            ]
        )
        monkeypatch.setattr(agent, "_call_llm", lambda messages: next(steps))
        attempts = {"count": 0}

        def fake_execute(code: str) -> dict:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return {
                    "stdout": "",
                    "stderr": "SyntaxError: '(' was never closed",
                    "outputs": {"result_type": "none", "result": None, "figures": []},
                }
            return {
                "stdout": "",
                "stderr": "",
                "outputs": {
                    "result_type": "dataframe",
                    "result": SAMPLE_DF.groupby("Region", as_index=False)["Revenue"].mean().to_json(orient="split"),
                    "figures": [],
                },
            }

        monkeypatch.setattr(agent.tools, "execute_python_code", fake_execute)

        response = agent.run("Average revenue by region")

        assert response["final_answer"] == "Average revenue by region computed."
        assert attempts["count"] == 2
        assert len(response["retry_events"]) == 1
        assert "SyntaxError" in response["retry_events"][0]["error"]

    def test_final_failure_after_three_attempts(self, monkeypatch):
        status_updates = []
        monkeypatch.setattr(DataAnalystAgent, "_build_openai_client", lambda self: object())
        schema = extract_schema(SAMPLE_DF)
        agent = DataAnalystAgent(
            df=SAMPLE_DF,
            schema=schema,
            max_retries=3,
            status_callback=lambda label, state: status_updates.append((label, state)),
        )
        steps = iter(
            [
                ReActStep(
                    thought="Use math.",
                    action="execute_python_code",
                    action_input="result = math.sqrt(df['Revenue'].mean())",
                    final_answer="",
                ),
                ReActStep(
                    thought="Try again.",
                    action="execute_python_code",
                    action_input="result = math.sqrt(df['Revenue'].mean())",
                    final_answer="",
                ),
                ReActStep(
                    thought="Try once more.",
                    action="execute_python_code",
                    action_input="result = math.sqrt(df['Revenue'].mean())",
                    final_answer="",
                ),
            ]
        )
        monkeypatch.setattr(agent, "_call_llm", lambda messages: next(steps))
        monkeypatch.setattr(
            agent.tools,
            "execute_python_code",
            lambda code: {
                "stdout": "",
                "stderr": "NameError: name 'math' is not defined",
                "outputs": {"result_type": "none", "result": None, "figures": []},
            },
        )

        response = agent.run("Compute square root of average revenue")

        assert response["final_answer"] == "Analysis failed after 3 attempts. Please rephrase your question."
        assert len(response["retry_events"]) == 3
        assert status_updates[-1][1] == "error"

    def test_full_session_history_is_forwarded(self, monkeypatch):
        captured_messages = []
        monkeypatch.setattr(DataAnalystAgent, "_build_openai_client", lambda self: object())
        schema = extract_schema(SAMPLE_DF)
        history = [
            {"role": "user", "content": f"question {index}"} if index % 2 == 0
            else {"role": "assistant", "content": f"answer {index}"}
            for index in range(10)
        ]
        agent = DataAnalystAgent(df=SAMPLE_DF, schema=schema, history=history)

        def fake_call_llm(messages):
            captured_messages.extend(messages)
            return ReActStep(
                thought="Enough context available.",
                action="final_answer",
                action_input="",
                final_answer="Done.",
            )

        monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

        response = agent.run("final question")

        assert response["final_answer"] == "Done."
        forwarded_contents = [message["content"] for message in captured_messages if message["role"] != "system"]
        for turn in history:
            assert turn["content"] in forwarded_contents
