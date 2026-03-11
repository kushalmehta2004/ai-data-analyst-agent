"""
app.py
Streamlit UI entry point for the AI Data Analyst Agent.
Phase 1: File upload, schema preview, chat shell (no LLM yet).
"""

from __future__ import annotations

from io import StringIO

import pandas as pd
import streamlit as st

from agent.core import DataAnalystAgent
from agent.memory import SessionMemory
from executor.sandbox import SandboxExecutor
from parser.file_parser import (
    extract_schema,
    get_excel_sheet_names,
    load_file,
)
from renderer.output import render_output

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Data Analyst Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Slightly wider chat area */
    .block-container { padding-top: 1.5rem; }

    /* Schema badge pills */
    .dtype-badge {
        background: #1e3a5f;
        color: #7ecfff;
        border-radius: 4px;
        padding: 1px 7px;
        font-size: 0.75rem;
        font-family: monospace;
    }

    /* Agent thinking expander border */
    .stExpander { border-left: 3px solid #f0a500 !important; }

    /* Chat input fix */
    div[data-testid="stChatInput"] { padding-bottom: 0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []          # {role, content, type}

if "dataframe" not in st.session_state:
    st.session_state.dataframe = None

if "schema" not in st.session_state:
    st.session_state.schema = None

if "uploaded_filename" not in st.session_state:
    st.session_state.uploaded_filename = None

if "memory" not in st.session_state:
    st.session_state.memory = SessionMemory(max_messages=20)

if "prior_results" not in st.session_state:
    st.session_state.prior_results = []

if "sandbox_executor" not in st.session_state:
    st.session_state.sandbox_executor = None


def render_chat_payload(message: dict, key_prefix: str = "") -> None:
    """Render a stored assistant payload in the chat transcript."""
    message_type = message.get("type")
    if message_type == "table":
        st.markdown(message["content"], unsafe_allow_html=True)
        dataframe_json = message.get("dataframe_json")
        if dataframe_json:
            try:
                csv_data = pd.read_json(StringIO(dataframe_json), orient="split").to_csv(index=False)
                st.download_button(
                    "⬇ Download CSV",
                    data=csv_data,
                    file_name="results.csv",
                    mime="text/csv",
                    key=f"{key_prefix}_table_export",
                )
            except Exception:
                pass
    elif message_type == "chart":
        st.image(message["content"])
        st.download_button(
            "⬇ Download PNG",
            data=message["content"],
            file_name="chart.png",
            mime="image/png",
            key=f"{key_prefix}_chart_export",
        )
    elif message_type == "text":
        if message.get("format") == "stdout":
            st.code(message["content"], language="text")
        else:
            st.markdown(message["content"])
    elif message_type == "error":
        st.error(message["content"])
    elif message_type == "trace":
        with st.expander("Agent Thinking", expanded=False):
            for item in message["content"]:
                header = f"**Step {item['step']}**  \nThought: {item['thought']}  \nAction: `{item['action']}`"
                if item.get("attempt"):
                    header += f"  \nAttempt: {item['attempt']}"
                st.markdown(header)
                if item.get("action_input"):
                    st.code(item["action_input"], language="python")
                if item.get("observation"):
                    st.markdown("**Observation**")
                    st.code(item["observation"], language="text")
    else:
        st.markdown(message["content"])


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🤖 AI Data Analyst")
    st.caption("Powered by GPT-4o · LangChain · E2B")

    st.divider()

    # --- Model selector -------------------------------------------------------
    st.subheader("⚙️ Model Settings")
    llm_provider = st.selectbox(
        "LLM Provider",
        options=["openai", "anthropic"],
        index=0,
        format_func=lambda p: "OpenAI GPT-4o" if p == "openai" else "Anthropic Claude Sonnet",
        help="Configure provider keys in .env",
    )
    st.session_state["llm_provider"] = llm_provider

    st.divider()

    # --- File uploader --------------------------------------------------------
    st.subheader("📂 Upload Dataset")

    uploaded_file = st.file_uploader(
        "Drag & drop or browse",
        type=["csv", "xlsx", "xls", "json"],
        help="Supports CSV, Excel (.xlsx), and JSON. Max 50 MB.",
        label_visibility="collapsed",
    )

    # Excel sheet selector (shown only for multi-sheet xlsx)
    selected_sheet = None
    if uploaded_file is not None and uploaded_file.name.lower().endswith((".xlsx", ".xls")):
        sheet_names = get_excel_sheet_names(uploaded_file)
        if len(sheet_names) > 1:
            selected_sheet = st.selectbox(
                "Select sheet",
                options=sheet_names,
                index=0,
            )

    # Parse file when uploaded (or when sheet changes)
    if uploaded_file is not None:
        file_key = f"{uploaded_file.name}_{selected_sheet}"
        if st.session_state.get("_last_file_key") != file_key:
            with st.spinner("Parsing file..."):
                try:
                    df = load_file(uploaded_file, sheet_name=selected_sheet)
                    schema = extract_schema(df)
                    st.session_state.dataframe = df
                    st.session_state.schema = schema
                    st.session_state.uploaded_filename = uploaded_file.name
                    st.session_state["_last_file_key"] = file_key
                    # Reset conversation on new file
                    st.session_state.messages = []
                    st.session_state.memory.clear()
                    st.session_state.prior_results = []

                    sandbox_executor = SandboxExecutor()
                    sandbox_executor.set_dataframe(df)
                    st.session_state.sandbox_executor = sandbox_executor
                    st.success(f"✅ Loaded **{uploaded_file.name}**")
                except ValueError as e:
                    st.error(str(e))

    st.divider()

    # --- Session info ---------------------------------------------------------
    if st.session_state.dataframe is not None:
        schema = st.session_state.schema
        st.subheader("📊 Dataset Info")
        st.metric("Rows", f"{schema['row_count']:,}")
        st.metric("Columns", schema["col_count"])
        sandbox_executor = st.session_state.get("sandbox_executor")
        if sandbox_executor is not None and sandbox_executor.is_available:
            st.caption("Execution mode: E2B sandbox")
        else:
            st.caption("Execution mode: Local subprocess fallback")
            if sandbox_executor is not None and sandbox_executor.last_error:
                st.caption(f"Reason: {sandbox_executor.last_error}")
        if schema["missing_info"]:
            st.caption(f"⚠️ {len(schema['missing_info'])} column(s) have missing values")

    st.divider()

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.memory.clear()
        st.session_state.prior_results = []
        st.rerun()


# ---------------------------------------------------------------------------
# Main content area
# ---------------------------------------------------------------------------

if st.session_state.dataframe is None:
    # ── Landing / empty state ─────────────────────────────────────────────
    st.markdown(
        """
        <div style="text-align:center; padding: 4rem 2rem;">
            <h1 style="font-size:2.8rem;">🤖 AI Data Analyst Agent</h1>
            <p style="font-size:1.2rem; color:#888; max-width:600px; margin:1rem auto;">
                Upload a CSV, Excel, or JSON file to get started.<br>
                Ask questions in plain English — the agent writes and executes Python code
                to answer you with charts, tables, and insights.
            </p>
            <br>
            <div style="display:flex; justify-content:center; gap:2rem; flex-wrap:wrap;">
                <div style="background:#1a1a2e; border-radius:12px; padding:1.2rem 1.8rem; max-width:200px;">
                    <div style="font-size:2rem;">📁</div>
                    <strong>Upload</strong><br>
                    <span style="color:#888; font-size:0.9rem;">CSV · Excel · JSON</span>
                </div>
                <div style="background:#1a1a2e; border-radius:12px; padding:1.2rem 1.8rem; max-width:200px;">
                    <div style="font-size:2rem;">💬</div>
                    <strong>Ask</strong><br>
                    <span style="color:#888; font-size:0.9rem;">Plain English questions</span>
                </div>
                <div style="background:#1a1a2e; border-radius:12px; padding:1.2rem 1.8rem; max-width:200px;">
                    <div style="font-size:2rem;">📊</div>
                    <strong>Analyse</strong><br>
                    <span style="color:#888; font-size:0.9rem;">Charts · Tables · Insights</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

else:
    schema = st.session_state.schema
    df = st.session_state.dataframe

    # ── Tabs: Chat | Schema Preview ────────────────────────────────────────
    tab_chat, tab_preview = st.tabs(["💬 Chat", "🔍 Data Preview"])

    # ------------------------------------------------------------------
    # Tab: Data Preview
    # ------------------------------------------------------------------
    with tab_preview:
        st.subheader(f"📄 {st.session_state.uploaded_filename}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Rows", f"{schema['row_count']:,}")
        col2.metric("Columns", schema["col_count"])
        col3.metric(
            "Missing values",
            sum(schema["missing_info"].values()) if schema["missing_info"] else 0,
        )

        st.markdown("#### First 5 rows")
        st.dataframe(df.head(5), use_container_width=True)

        st.markdown("#### Column types")
        dtype_rows = [
            {"Column": col, "Type": dtype, "Non-null": int(df[col].notna().sum())}
            for col, dtype in schema["dtypes"].items()
        ]
        st.dataframe(dtype_rows, use_container_width=True, hide_index=True)

        if schema["missing_info"]:
            st.markdown("#### Missing values")
            missing_rows = [
                {"Column": col, "Missing": count, "% Missing": f"{count/schema['row_count']*100:.1f}%"}
                for col, count in schema["missing_info"].items()
            ]
            st.dataframe(missing_rows, use_container_width=True, hide_index=True)

        st.markdown("#### Numeric statistics")
        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            st.dataframe(numeric_df.describe().round(2), use_container_width=True)
        else:
            st.info("No numeric columns found.")

    # ------------------------------------------------------------------
    # Tab: Chat
    # ------------------------------------------------------------------
    with tab_chat:
        # Render existing conversation messages
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                render_chat_payload(msg, key_prefix=f"history_{idx}")

        # Chat input
        user_input = st.chat_input(
            placeholder="Ask anything about your data… e.g. 'What is the average revenue by category?'"
        )

        if user_input:
            # Store and display user message
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.memory.add_turn("user", user_input)
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                status_box = st.status("Running analysis...", expanded=True)

                def update_status(label: str, state: str = "running") -> None:
                    status_box.update(label=label, state=state, expanded=True)

                with st.spinner("Thinking…"):
                    try:
                        history_for_agent = st.session_state.memory.get_history()
                        agent = DataAnalystAgent(
                            df=df,
                            schema=schema,
                            provider=st.session_state.get("llm_provider", "openai"),
                            history=history_for_agent,
                            status_callback=update_status,
                            sandbox_executor=st.session_state.sandbox_executor,
                            prior_results=st.session_state.prior_results,
                        )
                        response = agent.run(user_input)
                    except Exception as e:
                        update_status(f"Agent error: {e}", "error")
                        response = {
                            "final_answer": f"Agent error: {e}",
                            "trace": [],
                            "execution": None,
                            "retry_events": [],
                        }

                final_answer = response.get("final_answer", "No response generated.")
                st.markdown(final_answer)
                st.session_state.messages.append({"role": "assistant", "content": final_answer})
                st.session_state.memory.add_turn("assistant", final_answer)

                if final_answer.startswith("Analysis failed after"):
                    update_status(final_answer, "error")
                else:
                    update_status("Analysis complete", "complete")

                trace = response.get("trace", [])
                if trace:
                    render_chat_payload(
                        {"role": "assistant", "type": "trace", "content": trace},
                        key_prefix=f"trace_{len(st.session_state.messages)}",
                    )
                    st.session_state.messages.append(
                        {"role": "assistant", "type": "trace", "content": trace}
                    )

                execution = response.get("execution")
                if execution:
                    rendered = render_output(execution)
                    for item_idx, item in enumerate(rendered["content"]):
                        payload = {"role": "assistant", **item}
                        render_chat_payload(
                            payload,
                            key_prefix=f"new_{len(st.session_state.messages)}_{item_idx}",
                        )
                        st.session_state.messages.append(payload)
                        if item.get("type") == "table" and item.get("dataframe_json"):
                            st.session_state.prior_results.append(item["dataframe_json"])
                            if len(st.session_state.prior_results) > 5:
                                st.session_state.prior_results = st.session_state.prior_results[-5:]
