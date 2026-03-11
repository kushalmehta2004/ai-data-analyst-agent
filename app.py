"""
app.py
Streamlit UI entry point for the AI Data Analyst Agent.
Phase 1: File upload, schema preview, chat shell (no LLM yet).
"""

from __future__ import annotations

import streamlit as st

from parser.file_parser import (
    extract_schema,
    get_excel_sheet_names,
    load_file,
)

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
        options=["OpenAI GPT-4o", "Anthropic Claude Sonnet"],
        index=0,
        help="Configure your API key in .env",
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
        if schema["missing_info"]:
            st.caption(f"⚠️ {len(schema['missing_info'])} column(s) have missing values")

    st.divider()

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
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
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg.get("type") == "dataframe":
                    st.markdown(msg["content"], unsafe_allow_html=True)
                elif msg.get("type") == "image":
                    st.image(msg["content"])
                else:
                    st.markdown(msg["content"])

        # Chat input
        user_input = st.chat_input(
            placeholder="Ask anything about your data… e.g. 'What is the average revenue by category?'"
        )

        if user_input:
            # Store and display user message
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # ── Phase 1 placeholder — replaced in Phase 2 with ReAct agent ──
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    placeholder_msg = (
                        "🔧 **Agent not yet connected.** "
                        "The LLM + ReAct loop will be wired up in Phase 2. "
                        f"\n\nYou asked: *\"{user_input}\"*"
                        f"\n\nDataset loaded: **{st.session_state.uploaded_filename}** "
                        f"({schema['row_count']:,} rows × {schema['col_count']} columns)"
                    )
                    st.markdown(placeholder_msg)

            st.session_state.messages.append(
                {"role": "assistant", "content": placeholder_msg}
            )
