# Multi-Agent Supervisor Architecture — PDF Document Analyzer

A multi-agent system that analyzes PDF documents by dynamically routing queries to domain-specific AI agents. Built on the **Multi-Agent Supervisor (Router) Architecture** pattern.

---

## Architecture

```text
                        ┌─────────────────────────────┐
                        │   User Prompt + PDF File     │
                        └──────────────┬──────────────┘
                                       │
                                       ▼
               ┌───────────────────────────────────────────┐
               │         1. PERCEPTION LAYER               │
               │       (PDF Parser & Text Extractor)       │
               │                                           │
               │  • PyPDF text extraction                  │
               │  • Table detection & structure parsing     │
               │  • Metadata extraction (pages, author)     │
               └──────────────────┬────────────────────────┘
                                  │
                                  ▼
               ┌───────────────────────────────────────────┐
               │      2. ROUTER / SUPERVISOR AGENT         │
               │        (Intent Classification)            │
               │                                           │
               │  • Analyzes prompt + document content      │
               │  • Classifies domain (LLM-powered)         │
               │  • Dynamically spawns ONE specialist       │
               │  • Reports confidence & routing reasoning  │
               └──────────────────┬────────────────────────┘
                                  │
                         (single dispatch)
                                  │
                                  ▼
               ┌───────────────────────────────────────────┐
               │      3. DOMAIN AGENT (dynamically spawned)│
               │                                           │
               │  One of:                                  │
               │  Healthcare │ Finance   │ HR              │
               │  Insurance  │ Education │ Political       │
               │                                           │
               │  • Reasons over document via GPT-4o       │
               │  • Up to 5 reasoning iterations           │
               │  • Returns answer + confidence + evidence  │
               │  • Released from memory after execution    │
               └──────────────────┬────────────────────────┘
                                  │
                                  ▼
                        ┌─────────────────────────────┐
                        │     Final Output to User     │
                        └─────────────────────────────┘
```

**Key design choice:** Only one agent is alive at a time. The router classifies the domain, spawns the matching agent, gets the answer, and releases it — no concurrent agents consuming resources.

---

## Quick Start

### Prerequisites

- Python 3.9+
- OpenAI API key (stored via [keyring](SECURE_API_KEY_SETUP.md) or `OPENAI_API_KEY` env var)

### Install

```bash
git clone <repo> && cd pdfAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
# Using the shell wrapper
./run_pdf.sh "/path/to/document.pdf" "What is the carbon footprint for 2018?"

# Or directly
source .venv/bin/activate
python run_on_pdf.py "/path/to/document.pdf" "Your question here"
```

### API Server

```bash
source .venv/bin/activate
python -m src.api_server

# Upload a PDF
curl -X POST http://localhost:8000/analyze-pdf \
  -F "file=@document.pdf" \
  -F "query=What is the carbon footprint for 2018?"

# API docs at http://localhost:8000/docs
```

---

## Project Structure

```
pdfAgent/
├── run_on_pdf.py                      # CLI entry point
├── run_pdf.sh                         # Shell wrapper (uses .venv)
├── requirements.txt                   # Dependencies
├── .env.example                       # Environment variable template
├── pdfs/                              # PDF test documents
│
└── src/
    ├── __init__.py                    # Package (v1.0.0)
    ├── multi_agent_orchestrator.py    # Central orchestrator (ties all layers)
    ├── perception.py                  # Layer 1: PDF parsing & text extraction
    ├── router.py                      # Layer 2: Supervisor / intent router
    ├── api_server.py                  # FastAPI server (REST + WebSocket)
    │
    └── domain_agents/                 # Layer 3: Domain specialists
        ├── base.py                    #   Base class with reasoning loop
        ├── healthcare.py              #   Medical records, prescriptions, lab results
        ├── finance.py                 #   Financial statements, tax docs, ratios
        ├── hr.py                      #   Resumes, contracts, policies
        ├── insurance.py               #   Policies, claims, coverage
        ├── education.py               #   Transcripts, GPAs, credentials
        └── political.py               #   Legislation, voting records, regulations
```

---

## How It Works

### 1. Perception Layer (`perception.py`)

Parses the PDF before any LLM reasoning occurs:

- Extracts text page-by-page using **PyPDF**
- Detects tabular data via heuristic pattern matching
- Extracts metadata (filename, page count, author, title)
- Caches parsed documents for reuse

### 2. Router / Supervisor (`router.py`)

The intelligent dispatcher — it **never answers directly**, only routes:

- Analyzes the user's prompt alongside parsed PDF content
- Uses GPT-4o to classify intent into one of six domains
- Dynamically spawns a single domain agent (no multi-agent concurrency)
- Reports confidence and routing reasoning

**Supported Domains:**

| Domain | Example Documents |
|--------|-------------------|
| Healthcare | Medical records, prescriptions, lab results, clinical notes |
| Finance | Financial statements, tax returns, annual reports, invoices |
| HR | Resumes, employment contracts, performance reviews, handbooks |
| Insurance | Policies, claims, coverage summaries, premium statements |
| Education | Transcripts, diplomas, academic papers, certifications |
| Political | Government docs, legislation, voting records, regulations |

### 3. Domain Agents (`domain_agents/`)

Each agent is **dynamically spawned** by the router — only one agent runs at a time to conserve resources. Agents use GPT-4o to reason over the document content directly:

```
THINK → reason over document → ANSWER
```

- Decoupled: updating HR logic won't break the Finance agent
- Each has domain-specific system prompts and instructions
- Up to 5 reasoning iterations per query
- Returns structured results with confidence scores and evidence
- Agent is released from memory after execution completes

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check + supported domains |
| `POST` | `/analyze-pdf` | Upload PDF + query (multipart form) |
| `POST` | `/analyze` | Send raw text + query (JSON) |
| `WS` | `/analyze-stream` | WebSocket with step-by-step streaming |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Example Output

```
╔══════════════════════════════════════════════════════════════════╗
║               MULTI-AGENT SUPERVISOR ARCHITECTURE               ║
║                 PDF Document Analysis System                     ║
╚══════════════════════════════════════════════════════════════════╝

  📄 Document: ab20a33bc0bb38bd10a5fd09d4c84de0.pdf
  ❓ Query:    What is the carbon footprint for the year 2018?

================================================================================
📄 STEP 1 │ PERCEPTION LAYER: Parsing PDF
================================================================================
   📂 File: pdfs/ab20a33bc0bb38bd10a5fd09d4c84de0.pdf
   ✓ Parsed 5 pages (12,699 chars)

================================================================================
🧭 STEP 2 │ ROUTER/SUPERVISOR: Analyzing intent
================================================================================
   📋 Document type: Sustainability Impact Statement
   🎯 Primary domain: general
   📊 Confidence: 85%
   💭 Reasoning: Environmental sustainability topic...

================================================================================
⚡ STEP 3 │ DOMAIN AGENT EXECUTION
================================================================================
   🤖 Spawning [GENERAL] agent...
      Agent: FinanceAgent
      ┌─ ReAct Loop Started (max 5 iterations)
      │  Domain: finance | Model: gpt-4o
      ├─── Iteration 1/5
      │    💭 THINK: The document contains carbon footprint data for 2018...
      │    ✅ FINAL ANSWER (after 1 iteration)
      │    📊 Confidence: 90%
      └─ ReAct Loop Complete

────────────────────────────────────────────────────────────────────
ANSWER:
────────────────────────────────────────────────────────────────────
The total carbon footprint for the year 2018 was 2,571.37 tCO2-eq.
────────────────────────────────────────────────────────────────────

💯 Confidence: 90%

📌 Evidence:
   • Total Scope 1, 2, and 3 tCO2-eq emissions: 2,571.37
```

---

## Extending the System

### Add a New Domain Agent

Create `src/domain_agents/legal.py`:

```python
from .base import BaseDomainAgent

class LegalAgent(BaseDomainAgent):
    DOMAIN_NAME = "legal"
    DOMAIN_DESCRIPTION = "contracts, court filings, and legal analysis"

    def _register_tools(self):
        pass

    def get_domain_instructions(self) -> str:
        return "You are a legal analysis specialist..."
```

Then register it in `router.py` (add `LEGAL` to the `Domain` enum) and in `multi_agent_orchestrator.py` (add `Domain.LEGAL: LegalAgent` to `DOMAIN_AGENTS`).

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | GPT-4o for routing and reasoning |
| `pypdf` | PDF text extraction |
| `pydantic` | Data validation (API models) |
| `fastapi` | REST API server |
| `uvicorn` | ASGI server |
| `keyring` | Secure API key storage |
| `python-dotenv` | Environment variable loading |

---

## License

Internal use. All rights reserved.
