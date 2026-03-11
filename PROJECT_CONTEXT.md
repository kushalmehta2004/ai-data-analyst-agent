# PROJECT CONTEXT — AI Data Analyst Agent

> This file provides complete context for any AI assistant or developer working on this project.
> Keep this file updated as the project evolves.

---

## Repository

- **GitHub:** https://github.com/kushalmehta2004/ai-data-analyst-agent.git
- **Owner:** kushalmehta2004
- **Status:** In Development (Phase 1)

---

## Project Summary

A conversational AI agent that allows users to upload structured data files (CSV, Excel, JSON) and interact with them using plain English. The agent autonomously writes, executes, debugs, and self-corrects Python code to perform analysis, generate visualizations, and deliver insights — no coding knowledge required from the user.

**This is a portfolio project** demonstrating: agentic AI design, code generation & execution, sandboxed environments, self-correction loops, and full-stack AI application development.

---

## Source Documents

- `AI_Data_Analyst_Agent_PRD_Design.docx` — Original PRD + System Design Document (v1.0, March 2026)
- `BUILD_PLAN.md` — Phase-wise build plan with all architectural decisions
- `README.md` — Public-facing GitHub README

---

## Tech Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Python | 3.11+ |
| LLM | OpenAI GPT-4o (primary) | Configurable via `.env`; Claude Sonnet also supported |
| Agent Framework | **Custom ReAct loop** | NOT LangChain AgentExecutor — built from scratch for portfolio signal |
| LangChain | Tool definitions + message types only | `langchain>=0.2.0`, `langchain-openai`, `langchain-anthropic` |
| Structured Output | Pydantic v2 + instructor | Ensures clean code block extraction from LLM |
| Data Processing | Pandas, NumPy | |
| Visualization | Matplotlib, Seaborn (primary) + Plotly (optional interactive) | |
| Code Execution | E2B Sandbox (primary) | Falls back to subprocess with 30s timeout if no E2B key |
| Frontend | Streamlit | `>=1.32.0` |
| Testing | pytest | |
| Container | Docker | Python 3.11-slim base |

---

## Architectural Decisions (Final)

### 1. Custom ReAct Loop (NOT LangChain AgentExecutor)
- **Decision:** Build the ReAct loop manually in `agent/core.py`
- **Why:** Explicitly shows `Thought → Action → Observation` cycle in the UI. Strongest portfolio differentiator — signals deep understanding of agentic AI, not just library usage.
- **Visible in UI:** Every response shows an expandable "Agent Thinking" panel with the full trace.

### 2. E2B Sandbox as Primary Executor
- **Decision:** Use E2B for code execution; graceful fallback to local subprocess
- **Why:** Industry-standard security isolation for AI code execution. No host filesystem access.
- **Fallback:** If `E2B_API_KEY` not set in `.env`, automatically uses `local_exec.py` (subprocess with timeout).

### 3. Configurable LLM Provider
- **Decision:** `.env` flag `LLM_PROVIDER=openai|anthropic`
- **Why:** Reviewers can use their own API key. Demonstrates multi-provider thinking.
- **Default:** GPT-4o

### 4. instructor + Pydantic for Structured Output
- **Decision:** Use `instructor` library to extract structured code blocks
- **Why:** Prevents #1 LLM failure mode — malformed/partial code blocks.

### 5. DataFrame Injection Strategy
- **Decision:** Serialize `df` to CSV → upload to E2B sandbox on file upload; pickle for local fallback
- **Why:** Clean, stateless, avoids serialization edge cases.

---

## Folder Structure

```
ai-data-analyst-agent/
├── app.py                      # Streamlit UI entry point
├── agent/
│   ├── __init__.py
│   ├── core.py                 # Custom ReAct loop — the centrepiece
│   ├── tools.py                # execute_python_code(), describe_data()
│   ├── prompt.py               # build_system_prompt(schema) — injects schema at runtime
│   └── memory.py               # SessionMemory class — conversation history
├── executor/
│   ├── __init__.py
│   ├── sandbox.py              # E2B sandbox wrapper
│   └── local_exec.py           # subprocess fallback (30s timeout)
├── parser/
│   ├── __init__.py
│   └── file_parser.py          # load_file(), extract_schema() — CSV/Excel/JSON
├── renderer/
│   ├── __init__.py
│   └── output.py               # render_dataframe(), render_chart(), detect_output_type()
├── tests/
│   └── test_agent.py
├── assets/
│   └── demo.gif                # Demo GIF for README (to be added in Phase 6)
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
├── README.md
├── BUILD_PLAN.md               # Phase-wise build plan
└── PROJECT_CONTEXT.md          # This file
```

---

## Build Phases Summary

| Phase | Focus | Status |
|---|---|---|
| **Phase 1** | Scaffold + file parsing + Streamlit UI shell | ✅ Done |
| **Phase 2** | LLM + custom ReAct loop + local code execution | ⬜ Not Started |
| **Phase 3** | Chart + table rendering inline in chat | ⬜ Not Started |
| **Phase 4** | Self-correction loop (3 retries) | ⬜ Not Started |
| **Phase 5** | E2B sandbox + session memory + export buttons | ⬜ Not Started |
| **Phase 6** | Testing (3 datasets) + README + Docker | ⬜ Not Started |
| **Buffer** | Polish + query suggestions + deploy + publish | ⬜ Not Started |

> Update status to 🔄 In Progress / ✅ Done as phases complete.

---

## Functional Requirements Reference

| ID | Requirement | Priority | Phase |
|---|---|---|---|
| FR-01 | File upload: CSV, Excel (.xlsx), JSON | Must Have | 1 |
| FR-02 | Data preview table after upload | Must Have | 1 |
| FR-03 | Natural language query input | Must Have | 2 |
| FR-04 | LLM-powered Python code generation | Must Have | 2 |
| FR-05 | Sandboxed code execution (E2B / subprocess) | Must Have | 2 (local), 5 (E2B) |
| FR-06 | Chart rendering (bar, line, pie, scatter, heatmap) | Must Have | 3 |
| FR-07 | Tabular output rendering in UI | Must Have | 3 |
| FR-08 | Self-correction loop on code failure (max 3 retries) | Must Have | 4 |
| FR-09 | Conversation memory within session | Must Have | 5 |
| FR-10 | Export chart as PNG | Should Have | 5 |
| FR-11 | Export table as CSV | Should Have | 5 |
| FR-12 | Query suggestions based on dataset schema | Nice to Have | Buffer |
| FR-13 | Multi-sheet Excel support | Nice to Have | Buffer |

---

## Agent Flow (Step by Step)

1. **File Upload**: User uploads file → Pandas parses it → schema extracted (columns, dtypes, row count, 5 sample rows)
2. **System Prompt Built**: Schema injected into system prompt at runtime via `agent/prompt.py`
3. **User Query**: Enters chat → ReAct loop begins
4. **ReAct Iteration**:
   - `Thought`: LLM reasons about what code to write
   - `Action`: calls `execute_python_code(code)` or `describe_data()`
   - `Observation`: executor result returned to LLM
5. **Self-Correction**: If executor returns `stderr`, error is appended to history, LLM regenerates code — up to 3 times
6. **Output**: DataFrame → styled HTML table; Matplotlib figure → base64 PNG; text → markdown
7. **Memory**: Every turn stored in `SessionMemory` → passed to LLM on next query

---

## System Prompt Template

```
You are an expert data analyst AI. The user has uploaded a dataset with the following schema:

Columns and types:
{column_names_and_types}

Row count: {row_count}

Sample rows:
{sample_5_rows_as_markdown_table}

Rules:
- The dataframe is pre-loaded as `df`
- Use Pandas for all data operations
- For charts, use Matplotlib or Seaborn; save with plt.savefig() or assign to `result`
- Assign your final tabular result to the variable `result`
- Do not use df.head() or df.sample() in your output — work with the full dataset
- Column names are case-sensitive — use exactly as shown above
```

---

## Self-Correction Logic (Pseudocode)

```python
for attempt in range(1, 4):
    result = executor.run(code, df)
    if result["stderr"]:
        history.add("tool", f"Error on attempt {attempt}:\n{result['stderr']}")
        code = llm.regenerate(history)   # re-prompt with error context
    else:
        break
else:
    return {"error": "Analysis failed after 3 attempts. Please rephrase your question."}
```

---

## Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates column names | Pass exact column names in system prompt; validate before execution |
| Malformed code blocks from LLM | Pydantic + instructor structured extraction |
| Code execution security | E2B sandbox — no host filesystem access |
| Large files slowing analysis | 50MB cap; `@st.cache_data` on file parsing |
| API cost during demos | Cache repeated queries; GPT-3.5 fallback option for simple questions |

---

## Environment Variables

```env
# Required
LLM_PROVIDER=openai            # or anthropic
OPENAI_API_KEY=sk-...

# Optional
ANTHROPIC_API_KEY=sk-ant-...
E2B_API_KEY=...                # if not set, uses local subprocess executor
```

---

## Test Datasets (Phase 6)

1. **Titanic** — `train.csv` from [Kaggle Titanic Competition](https://www.kaggle.com/c/titanic)
2. **Superstore Sales** — `superstore.csv` (common public BI dataset)
3. **COVID-19** — daily cases CSV from Our World in Data

---

## Portfolio Showcase Notes

- The **self-correction loop** is the most impressive agentic feature — highlight in README and demo GIF
- The **visible ReAct trace** ("Agent Thinking" panel) differentiates this from basic LLM chat apps
- Demo GIF should show: upload → simple question → chart question → self-correction in action (60-90 sec)
- Mention in README: "Built from scratch — not a LangChain wrapper"
- GitHub tags: `#langchain #openai #agentic-ai #data-analysis #streamlit #e2b #python #pandas`

---

## Commands Reference

```bash
# Run locally
streamlit run app.py

# Run tests
pytest tests/ -v

# Build Docker image
docker build -t ai-data-analyst-agent .

# Run Docker container
docker run -p 8501:8501 --env-file .env ai-data-analyst-agent
```

---

*Last updated: March 2026 | Phase: Phase 1 complete*
