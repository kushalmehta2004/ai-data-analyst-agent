# AI Data Analyst Agent — Phase-wise Build Plan

> **Version:** 1.0 | **Date:** March 2026  
> Based on PRD & System Design Document v1.0

---

## Architectural Decisions (Pre-Build)

| Decision | Choice | Rationale |
|---|---|---|
| Agent Loop | **Custom ReAct loop** | Explicit `Thought → Action → Observation` steps visible in UI — strongest portfolio signal, shows deep understanding of agentic AI vs. just calling a library |
| Code Execution | **E2B Sandbox (primary)**, subprocess fallback | Security isolation is a hard requirement (§17); E2B is industry-standard for AI code execution; degrades gracefully to subprocess if no E2B key |
| LLM Provider | **Configurable via `.env`** — GPT-4o default, Claude Sonnet optional | Lets any reviewer plug in their own key; demonstrates multi-provider thinking |
| DataFrame Injection | **CSV upload to E2B sandbox** at session start; pickle for local fallback | Clean, stateless, and avoids serialization gotchas |
| Frontend | **Streamlit** with custom CSS polish | Speed to build; focus stays on the AI architecture, not React boilerplate |
| Structured Output | **Pydantic + instructor library** | Prevents malformed code blocks from LLM; clean extraction every time |
| Visualization | **Matplotlib + Seaborn** (primary), **Plotly** (interactive, optional) | Broad chart type coverage; Plotly adds interactivity as a bonus |

---

## Phase 1 — Foundation & File Parsing
**Timeline: Days 1–2**  
**Covers: FR-01, FR-02, US-01**

### Goal
Scaffold the full project, wire up file ingestion, and build the Streamlit UI shell with data preview — no LLM yet.

### Folder Structure to Scaffold
```
ai-data-analyst-agent/
├── app.py                      # Streamlit UI entry point
├── agent/
│   ├── __init__.py
│   ├── core.py                 # Custom ReAct loop
│   ├── tools.py                # Tool definitions
│   ├── prompt.py               # System prompt builder
│   └── memory.py               # Session conversation history
├── executor/
│   ├── __init__.py
│   ├── sandbox.py              # E2B sandbox wrapper
│   └── local_exec.py           # Subprocess fallback executor
├── parser/
│   ├── __init__.py
│   └── file_parser.py          # CSV / Excel / JSON ingestion
├── renderer/
│   ├── __init__.py
│   └── output.py               # Table + chart rendering utilities
├── tests/
│   └── test_agent.py
├── .env.example
├── requirements.txt
├── Dockerfile
└── README.md
```

### Tasks

1. **`requirements.txt`** — pin all dependencies:
   ```
   streamlit>=1.32.0
   langchain>=0.2.0
   langchain-openai>=0.1.0
   langchain-anthropic>=0.1.0
   openai>=1.20.0
   anthropic>=0.25.0
   pandas>=2.2.0
   numpy>=1.26.0
   matplotlib>=3.8.0
   seaborn>=0.13.0
   plotly>=5.20.0
   pydantic>=2.6.0
   instructor>=1.2.0
   python-dotenv>=1.0.0
   openpyxl>=3.1.0
   e2b-code-interpreter>=0.0.10
   pytest>=8.1.0
   ```

2. **`parser/file_parser.py`**:
   - `load_file(uploaded_file) → pd.DataFrame` — supports `.csv`, `.xlsx`, `.json`
   - `extract_schema(df) → dict` — returns `{columns, dtypes, row_count, sample_rows, numeric_stats}`
   - 50MB file size guard with descriptive error
   - Multi-sheet Excel: detect multiple sheets, return sheet names for user selection

3. **`app.py` — Streamlit UI shell**:
   - `st.file_uploader` accepting `.csv`, `.xlsx`, `.json`
   - On upload: parse → render `st.dataframe` preview (first 5 rows) + dtypes table
   - Chat input (`st.chat_input`) + scrollable message history via `st.session_state`
   - Sidebar: model selector (GPT-4o / Claude Sonnet), session info
   - UI-only at this stage — no LLM calls yet

### Deliverable
App runs locally. Upload any CSV/Excel/JSON and see a schema preview. Chat input visible but non-functional.

---

## Phase 2 — LLM Integration & Code Generation
**Timeline: Days 3–4**  
**Covers: FR-03, FR-04, FR-05 (local), US-02**

### Goal
Full end-to-end flow: upload → ask a question → LLM generates Python code → execute locally → return raw output in chat.

### Tasks

1. **`.env.example`**:
   ```
   LLM_PROVIDER=openai          # or anthropic
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   E2B_API_KEY=...              # leave blank to use local subprocess
   ```

2. **`agent/prompt.py` — Dynamic system prompt builder**:
   - `build_system_prompt(schema: dict) → str`
   - Injects: column names + dtypes, row count, 5 sample rows as markdown table
   - Instructions: "Use Pandas; dataframe is pre-loaded as `df`; for charts use Matplotlib; assign final result to `result`"
   - Column names injected verbatim to prevent hallucination (per §17 risk mitigation)

3. **`executor/local_exec.py` — Subprocess executor**:
   - `run_code(code: str, df: pd.DataFrame) → dict{stdout, stderr, outputs}`
   - Injects `df` by pickling it into the subprocess namespace
   - 30-second subprocess timeout
   - Captures: stdout text, stderr, any DataFrames assigned to `result`, any Matplotlib figures

4. **`agent/core.py` — Custom ReAct Loop** *(the portfolio centrepiece)*:
   ```
   Thought:  LLM reasons about how to answer the question
   Action:   LLM selects a tool and provides arguments
   Observation: Tool result is returned
   → repeat until Final Answer
   ```
   - Pydantic model enforces structured LLM output: `{thought, action, action_input, final_answer}`
   - `instructor` library used for reliable structured extraction from LLM
   - Conversation history + schema injected at every step
   - Full ReAct trace stored in session (displayed in expandable "Agent Thinking" section in UI)

5. **`agent/tools.py`** — Two tools registered with the ReAct loop:
   - `execute_python_code(code: str)` — wraps executor, returns results
   - `describe_data()` — returns full schema + `df.describe()` statistics

6. **Wire `app.py`**: chat input → `agent/core.py` → executor → display raw stdout/result in chat

### Deliverable
Ask *"What is the average revenue by category?"* and get a correct text answer. "Agent Thinking" expander shows full ReAct trace.

---

## Phase 3 — Output Rendering
**Timeline: Day 5**  
**Covers: FR-06, FR-07, US-02**

### Goal
Charts and tables render cleanly inline in the Streamlit chat — not just raw text.

### Tasks

1. **`renderer/output.py`**:
   - `render_dataframe(df) → HTML` — styled HTML table via `df.to_html()`
   - `render_chart(fig) → bytes` — encodes Matplotlib figure as base64 PNG
   - `detect_output_type(exec_result) → "table" | "chart" | "text"` — routes automatically
   - `render_output(exec_result) → dict{type, content}` — unified entry point

2. **Extend `executor/local_exec.py`**:
   - Intercept `plt.savefig()` calls — capture figure bytes before display
   - Detect and return any `pd.DataFrame` assigned to `result` variable
   - Support multiple outputs in a single execution (chart + summary text)

3. **Update `app.py`**:
   - `st.markdown(html, unsafe_allow_html=True)` for rendered tables
   - `st.image(png_bytes)` for charts
   - Plain `st.markdown` for text summaries
   - Support mixed output: chart + text in the same response

4. **Chart types supported** (prompt LLM to use these):
   - Bar, Line, Pie, Scatter, Heatmap (Seaborn), Histogram, Box plot

### Deliverable
Ask *"Show me a bar chart of sales by region"* and see a rendered chart inline in the chat alongside a text summary.

---

## Phase 4 — Self-Correction Loop
**Timeline: Day 6**  
**Covers: FR-08, US-03**

### Goal
When generated code fails, the agent automatically retries up to 3 times, feeding the error back to the LLM for self-correction. This is the most impressive agentic feature in the portfolio.

### Tasks

1. **Self-correction logic in `agent/core.py`**:
   ```python
   for attempt in range(1, 4):
       result = executor.run(code, df)
       if result["stderr"]:
           # Append error as tool observation
           history.add("tool", f"Error on attempt {attempt}:\n{result['stderr']}")
           # Re-prompt: "Fix the following error and rewrite the code"
           code = llm.regenerate(history)
       else:
           break
   else:
       return {"error": "Analysis failed after 3 attempts. Please rephrase your question."}
   ```

2. **Column name validation** (pre-execution guard):
   - Extract column references from generated code via regex
   - Validate against `df.columns` before executing
   - If mismatch found: inject correction into prompt without burning a retry

3. **UI feedback**:
   - Show `st.status("Retrying... (attempt 2/3)")` spinner during retries
   - On final failure: display clean error message with suggestion to rephrase
   - In "Agent Thinking" expander: show all retry attempts with their errors and corrections

4. **Test self-correction explicitly** with:
   - Hallucinated column name
   - Invalid Pandas syntax
   - Missing import in generated code

### Deliverable
Trigger a bad/ambiguous query. Watch the agent retry 1–3 times in the UI, then either recover with the correct answer or show a graceful failure message.

---

## Phase 5 — E2B Sandbox, Session Memory & Exports
**Timeline: Day 7**  
**Covers: FR-05 (secure), FR-09, FR-10, FR-11, US-04, US-05**

### Goal
Secure sandboxed code execution, persistent multi-turn conversation memory, and file export buttons.

### Tasks

1. **`executor/sandbox.py` — E2B Sandbox**:
   - On file upload: serialize `df` to CSV → upload to E2B sandbox via `sandbox.files.write()`
   - `run_code(code: str) → dict{stdout, stderr, outputs}` — execute in isolated cloud sandbox
   - Retrieve output files (charts as PNG, CSVs) from sandbox after execution
   - Graceful fallback: if `E2B_API_KEY` not set → use `local_exec.py` automatically
   - Sandbox lifetime tied to Streamlit session

2. **`agent/memory.py` — Session Memory**:
   - `SessionMemory` class with `add_turn(role, content)` and `get_history() → list[dict]`
   - Stored in `st.session_state` — persists across the Streamlit session
   - History truncation at 20 messages to avoid token overflow (sliding window)
   - Full history passed to LLM at every call for multi-turn context

3. **Multi-turn wiring**:
   - *"Now break that down by month"* correctly references the prior result
   - Prior `result` DataFrames stored in session for reference in follow-up queries

4. **Export buttons** (rendered below each output):
   - Chart: `st.download_button("⬇ Download PNG", data=png_bytes, file_name="chart.png", mime="image/png")`
   - Table: `st.download_button("⬇ Download CSV", data=csv_str, file_name="results.csv", mime="text/csv")`

### Deliverable
Multi-turn conversation works. Code runs securely in E2B sandbox (or local fallback). Every chart and table has download buttons.

---

## Phase 6 — Testing, README & Docker
**Timeline: Days 8–9**  
**Covers: §8 Success Metrics, §18 Portfolio Tips**

### Goal
Production-quality project: tested, documented, containerized, and demo-ready.

### Tasks

1. **Testing (`tests/test_agent.py`)**:
   - Unit: `file_parser.py` — test all 3 file types, malformed files, 50MB guard
   - Unit: self-correction loop — mock executor to fail on attempt 1, succeed on attempt 2
   - Unit: column name validator — inject hallucinated column, verify interception
   - Integration: load Titanic CSV → ask 3 questions → assert non-empty outputs
   - Integration: load Superstore Sales CSV → ask chart question → assert PNG returned
   - Integration: load COVID data CSV → ask aggregation question → assert DataFrame returned
   - Run with: `pytest tests/ -v`

2. **README.md** — portfolio-grade documentation:
   - Hero badge row: Python, LangChain, OpenAI, E2B, Streamlit
   - Demo GIF (60–90 sec): upload → simple question → chart question → self-correction in action
   - **Architecture section** with Mermaid flow diagram:
     ```
     User → Streamlit UI → ReAct Agent Loop → Tool Selection
     → E2B Sandbox Executor → Output Renderer → Streamlit Chat
     ↑________ Self-Correction (up to 3 retries) ___________|
     ```
   - Self-correction loop diagram — explicitly called out (strongest agentic signal)
   - Quick start: `pip install -r requirements.txt` + `streamlit run app.py`
   - Docker quick start
   - "Try it yourself" link (Streamlit Cloud / HuggingFace Spaces)
   - Example questions per dataset (Titanic, Superstore, COVID)

3. **Dockerfile**:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8501
   HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health
   CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
   ```

4. **Record demo GIF** using LICEcap or OBS:
   - Scene 1: Upload Titanic CSV → schema preview appears
   - Scene 2: Ask "What is the survival rate by passenger class?" → table output
   - Scene 3: Ask "Show me a bar chart of that" → chart renders
   - Scene 4: Ask an ambiguous question → self-correction retries visible in UI

### Deliverable
Fully tested, documented, containerized project. README opens with a compelling demo GIF.

---

## Buffer — Polish, Nice-to-Haves & Publish
**Timeline: Day 10**

### Tasks

1. **FR-12 — Query suggestions** (Nice to Have):
   - After file upload, auto-generate 3 suggested questions based on schema
   - Display as clickable `st.button` chips below the schema preview
   - One-shot LLM call with schema → returns JSON list of suggestions

2. **FR-13 — Multi-sheet Excel** (Nice to Have):
   - After `.xlsx` upload: detect multiple sheets → show `st.selectbox` for sheet selection
   - Re-parse on selection change

3. **Performance**:
   - `@st.cache_data` on `load_file()` to avoid re-parsing on Streamlit re-runs
   - Progress bar during file parsing for large files

4. **GitHub publish checklist**:
   - Tags: `#langchain #openai #agentic-ai #data-analysis #streamlit #e2b #python`
   - Topics set in repo settings
   - License: MIT
   - `.gitignore`: exclude `.env`, `__pycache__`, `.pytest_cache`

5. **Deploy**:
   - Streamlit Community Cloud (free) → shareable demo link
   - OR HuggingFace Spaces (Streamlit SDK) — more ML-community visibility

---

## Summary

| Phase | Focus | Days | Key Deliverable |
|---|---|---|---|
| **1** | Foundation + File Parsing | 1–2 | Upload + schema preview UI working |
| **2** | LLM + Custom ReAct Loop | 3–4 | First end-to-end answer + visible agent trace |
| **3** | Chart + Table Rendering | 5 | Inline charts and styled tables in chat |
| **4** | Self-Correction Loop | 6 | Auto-retry on failure — visible in UI |
| **5** | E2B Sandbox + Memory + Exports | 7 | Secure execution, multi-turn, downloads |
| **6** | Testing + README + Docker | 8–9 | Portfolio-ready, documented, containerized |
| **Buffer** | Polish + Deploy + Publish | 10 | Live link + GitHub published |

---

## Portfolio Impact by Feature

| Feature | Portfolio Signal |
|---|---|
| Custom ReAct loop (visible in UI) | Shows deep agentic AI understanding — not just LangChain wrappers |
| Self-correction with retry trace | The single most impressive agentic behavior to demo |
| E2B sandbox integration | Industry-relevant security practice for AI code execution |
| Pydantic structured output | Shows production-quality thinking, not just raw LLM calls |
| Configurable LLM provider | Demonstrates multi-provider API experience |
| Docker + clean folder structure | Shows software engineering discipline |
| 3 real-world datasets tested | Proves robustness, not a one-trick demo |

---

*End of Build Plan — AI Data Analyst Agent v1.0*
