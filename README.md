<div align="center">

# 🤖 AI Data Analyst Agent

**A conversational AI agent that reads your data files and answers questions in plain English — autonomously writing, executing, and self-correcting Python code to deliver charts, tables, and insights.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangChain](https://img.shields.io/badge/LangChain-0.2+-1C3C3C?style=for-the-badge&logo=chainlink&logoColor=white)](https://langchain.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![E2B](https://img.shields.io/badge/E2B-Sandbox-FF6B35?style=for-the-badge)](https://e2b.dev)

![Demo](assets/demo.gif)

</div>

---

## What It Does

Upload any CSV, Excel, or JSON file and start asking questions in plain English:

- *"What is the average revenue by category?"* → styled table
- *"Show me a bar chart of sales by region over time"* → rendered chart
- *"Find correlations and flag any anomalies"* → statistical analysis
- *"Now break that down by month"* → follow-up with conversation memory

The agent **writes Python code**, **executes it in a secure sandbox**, and **self-corrects if it fails** — all without you writing a single line of code.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                             │
│          File Upload │ Chat Interface │ Output Display          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ User Query + Schema
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Custom ReAct Agent Loop                       │
│                                                                 │
│  Thought → "I need to group by region and sum revenue"         │
│  Action  → execute_python_code(code)                           │
│  Obs.    → [Error: KeyError 'Revenue']                         │
│  Thought → "Column is named 'revenue' (lowercase), fix it"     │
│  Action  → execute_python_code(corrected_code)                 │
│  Obs.    → DataFrame / Chart returned                          │
│  Answer  → Summarize and display                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌─────────────────────┐     ┌────────────────────────┐
│  execute_python_code│     │     describe_data()     │
│       tool          │     │         tool            │
└──────────┬──────────┘     └────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     E2B Sandbox Executor                        │
│         Isolated cloud environment — no host filesystem        │
│         Fallback: subprocess with 30s timeout (local)          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Output Renderer                            │
│        Tables → styled HTML  │  Charts → base64 PNG           │
└─────────────────────────────────────────────────────────────────┘
```

### Self-Correction Loop

```
Code Generated
      │
      ▼
Execute in Sandbox
      │
   Error? ──── Yes ──→ Append error trace to history
      │                        │
      No                       ▼
      │              Re-prompt LLM: "Fix this error"
      ▼                        │
   Return Output     Attempt 2 / 3 ──→ (repeat)
                               │
                          3 failures?
                               │
                               ▼
                    "Could not complete analysis.
                     Please rephrase your question."
```

---

## Key Features

| Feature | Detail |
|---|---|
| **Custom ReAct Loop** | Explicit `Thought → Action → Observation` trace visible in UI — not a black-box LangChain wrapper |
| **Self-Correction** | Up to 3 automatic retries with error context fed back to LLM |
| **E2B Sandbox** | Code runs in isolated cloud environment — zero host filesystem access |
| **Multi-turn Memory** | Follow-up questions understand prior context within the session |
| **Structured Output** | Pydantic + instructor library ensures clean code extraction every time |
| **Multi-provider LLM** | Switch between GPT-4o and Claude Sonnet via `.env` |
| **Export** | Download charts as PNG, tables as CSV |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | OpenAI GPT-4o (default) / Anthropic Claude Sonnet |
| **Agent Framework** | Custom ReAct loop + LangChain tool definitions |
| **Structured Output** | Pydantic v2 + instructor |
| **Data Processing** | Pandas, NumPy |
| **Visualization** | Matplotlib, Seaborn, Plotly |
| **Code Execution** | E2B Sandbox (cloud) / subprocess fallback (local) |
| **Frontend** | Streamlit |
| **Environment** | Python 3.11+, Docker |

---

## Project Structure

```
ai-data-analyst-agent/
├── app.py                      # Streamlit UI entry point
├── agent/
│   ├── core.py                 # Custom ReAct loop implementation
│   ├── tools.py                # Tool definitions (execute_code, describe_data)
│   ├── prompt.py               # Dynamic system prompt builder with schema injection
│   └── memory.py               # Session conversation history
├── executor/
│   ├── sandbox.py              # E2B sandbox wrapper
│   └── local_exec.py           # Subprocess fallback executor
├── parser/
│   └── file_parser.py          # CSV / Excel / JSON ingestion + schema extraction
├── renderer/
│   └── output.py               # Table + chart rendering utilities
├── tests/
│   └── test_agent.py           # Unit + integration tests
├── .env.example
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/kushalmehta2004/ai-data-analyst-agent.git
cd ai-data-analyst-agent
```

### 2. Set up environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API keys

```bash
cp .env.example .env
# Edit .env with your keys
```

```env
LLM_PROVIDER=openai            # or anthropic
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # optional
E2B_API_KEY=...                # optional — uses local subprocess if not set
```

### 4. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501)

---

## Docker

```bash
docker build -t ai-data-analyst-agent .
docker run -p 8501:8501 --env-file .env ai-data-analyst-agent
```

---

## Try These Example Questions

Load the **Titanic dataset** (`train.csv`) and try:
- *"What is the survival rate by passenger class?"*
- *"Show me the age distribution of survivors vs non-survivors as a histogram"*
- *"Which features have the strongest correlation with survival?"*

Load the **Superstore Sales dataset** and try:
- *"What are the top 5 products by profit margin?"*
- *"Show monthly sales trend as a line chart"*
- *"Which region is underperforming? Show me a breakdown"*

Load any **COVID dataset** and try:
- *"Plot the 7-day rolling average of new cases"*
- *"Which countries had the fastest growth rate in week 3?"*

---

## How the Agent Thinks (ReAct Trace)

Every response shows an expandable **"Agent Thinking"** panel:

```
💭 Thought: The user wants sales grouped by region. I'll use groupby on the 'Region'
            column and sum 'Sales'. Then I'll create a bar chart.

⚡ Action: execute_python_code
   Input:  result = df.groupby('Region')['Sales'].sum().reset_index()
           result = result.sort_values('Sales', ascending=False)
           plt.figure(figsize=(10, 6))
           plt.bar(result['Region'], result['Sales'])
           plt.title('Total Sales by Region')
           plt.xlabel('Region')
           plt.ylabel('Sales ($)')

👁 Observation: Chart generated successfully. DataFrame with 4 rows returned.

✅ Final Answer: Here's the sales breakdown by region. The West leads with $725K,
                followed by East at $678K...
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover:
- File parsing (CSV, Excel, JSON, malformed files)
- Self-correction loop (mock failures → recovery)
- Column name validation (hallucination guard)
- End-to-end integration with Titanic, Superstore, COVID datasets

---

## Why This Project

This project demonstrates:

1. **Agentic AI design** — building a stateful, multi-step reasoning loop from scratch
2. **Code generation + execution** — LLM writes runnable Python, not just descriptions
3. **Sandboxed environments** — secure execution with E2B, a real production pattern
4. **Self-correcting systems** — error recovery without human intervention
5. **Full-stack AI development** — from LLM API calls to a polished, usable UI

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

Built with Python 3.11 · LangChain · OpenAI GPT-4o · E2B · Streamlit

**[⭐ Star this repo](https://github.com/kushalmehta2004/ai-data-analyst-agent)** if you found it useful

</div>
