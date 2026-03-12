# Ask INDy — Parag Parikh Mutual Fund RAG Chatbot

> A conversational AI chatbot that answers factual questions about Parag Parikh Mutual Fund (PPFAS) schemes — built using Retrieval-Augmented Generation (RAG).

---

## 🤔 What does this project do?

**Ask INDy** is a chat interface where you can ask natural-language questions about 4 Parag Parikh Mutual Fund schemes and get accurate, cited answers — powered by a local AI pipeline.

**Example questions it can answer:**
- *"What is the NAV of Parag Parikh Flexi Cap Fund?"*
- *"What is the exit load for the Conservative Hybrid Fund?"*
- *"Who manages the Liquid Fund?"*
- *"How do I download my account statement?"*
- *"What is the expense ratio of the Tax Saver Fund?"*

**What it won't do:**
- Give investment advice ("Should I invest?")  ← blocked by guardrails
- Tell you your portfolio value or returns  ← no personal data
- Answer questions unrelated to PPFAS funds  ← out of scope

---

## 🏗️ How it Works — System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│              Phase 1 — Data Ingestion (Scraping)             │
│  15 websites → Playwright scraper → data/structured/*.json   │
│  + mfapi.in  → Daily NAV fetcher  → injected into JSON       │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│           Phase 2 — Embeddings & Vector Store                │
│  Chunker → sentence-transformers (local) → ChromaDB          │
│  2 collections: ppfas_scheme_facts (36) + ppfas_general (26) │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Phase 3 — RAG Core & Guardrails                 │
│  Query → Pre-filter → ChromaDB Retrieval → Groq Llama LLM   │
│       → Post-filter → Cited Answer                           │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│           Phase 4 — FastAPI Backend + React Frontend         │
│  POST /api/chat  •  GET /api/status  •  GET /health          │
│  React UI (Vite) on :5173  ←→  Backend (Uvicorn) on :8000   │
└──────────────────────────────────────────────────────────────┘
                            │ (background)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Phase 5 — Auto-Refresh Scheduler                │
│  APScheduler → daily at 10:00 AM IST                         │
│  Re-scrapes all 15 URLs + fetches NAV → rebuilds ChromaDB    │
│  → updates "Data last updated" timestamp in header           │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 Scope

| Scheme | Short Code | Category |
|--------|-----------|----------|
| Parag Parikh Flexi Cap Fund (Direct-Growth) | PPFCF | Flexi Cap |
| Parag Parikh ELSS Tax Saver Fund (Direct-Growth) | PPTSF | ELSS |
| Parag Parikh Conservative Hybrid Fund (Direct-Growth) | PPCHF | Conservative Hybrid |
| Parag Parikh Liquid Fund (Direct-Growth) | PPLF | Liquid |

---

## 🛠️ Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Scraping** | Playwright (async, headless Chromium) | Handles React/JavaScript-heavy pages like INDmoney |
| **NAV Fetching** | `mfapi.in` (AMFI public API) | Official daily NAV data, no scraping needed |
| **Embedding Model** | `sentence-transformers/all-MiniLM-L6-v2` | Runs fully locally — no API key required |
| **Vector Database** | ChromaDB (local, persistent) | Fast semantic search, zero infrastructure |
| **LLM** | `llama-3.1-8b-instant` via [Groq](https://console.groq.com) | Fast inference, free tier available |
| **Backend** | FastAPI + Uvicorn | Lightweight Python REST API |
| **Frontend** | React 18 + TypeScript + Vite | Mobile-style chat UI |
| **Scheduler** | APScheduler (cron) | Daily 10 AM IST auto-refresh |

---

## 📁 Project Structure

```
mutual-fund-rag-chatbot/
│
├── phase1_ingestion/       ← 📖 Beginner-friendly guide to Phase 1 code
├── phase2_embeddings/      ← 📖 Beginner-friendly guide to Phase 2 code
├── phase3_rag_core/        ← 📖 Beginner-friendly guide to Phase 3 code
├── phase4_api_frontend/    ← 📖 Beginner-friendly guide to Phase 4 code
├── phase5_scheduler/       ← 📖 Beginner-friendly guide to Phase 5 code
│
├── scrapers/               ← Phase 1: Playwright scrapers + NAV fetcher
│   ├── runner.py           ← Master scraper orchestrator
│   ├── nav_fetcher.py      ← Fetches daily NAV from mfapi.in
│   ├── ppfas_scraper.py
│   ├── indmoney_scraper.py
│   ├── amfi_scraper.py
│   └── general_scraper.py
│
├── embedder/               ← Phase 2: Chunking + ChromaDB
│   ├── pipeline.py         ← Runs full embed pipeline (seed data built-in)
│   ├── chunker.py          ← Splits facts into atomic text chunks
│   └── chroma_store.py     ← ChromaDB wrapper
│
├── backend/                ← Phase 3 + 4: RAG logic + API server
│   ├── main.py             ← FastAPI app entrypoint (port 8000)
│   ├── config.py           ← Central config (API keys, settings)
│   ├── routers/chat.py     ← POST /api/chat, GET /api/status
│   ├── services/
│   │   ├── retriever.py    ← ChromaDB semantic search
│   │   ├── generator.py    ← RAG pipeline: retrieve → LLM → respond
│   │   └── guardrails.py   ← Pre/post filters (blocks advice, PII, etc.)
│   └── models/             ← Pydantic request/response types
│
├── frontend/               ← Phase 4: React chat UI (port 5173)
│   └── src/
│       ├── components/
│       │   ├── ChatWindow.tsx   ← Main chat interface
│       │   └── MessageBubble.tsx ← Message + timestamp + source chips
│       ├── types/chat.ts
│       └── index.css
│
├── scheduler.py            ← Phase 5: Daily 10 AM IST refresh
├── data/
│   ├── structured/         ← mutual_funds.json (scraper output)
│   └── metadata.json       ← "Data last updated" timestamp
├── vector_store/           ← ChromaDB persistent files (auto-generated)
├── logs/                   ← scrape_log.json, scheduler.log
│
├── .env                    ← Your API keys (never commit this!)
├── .env.example            ← Template showing required keys
├── .gitignore
├── requirements.txt
├── README.md               ← Setup guide
├── sources.md              ← All 15 source URLs
└── sample_qa.txt           ← 5 example queries
```

---

## ⚙️ How to Run Locally

### Prerequisites

- Python 3.9+
- Node.js & npm (to install and run the React development server)
- A free [Groq API Key](https://console.groq.com)

### Step 1 — Clone and install Python dependencies

```bash
git clone https://github.com/your-username/mutual-fund-rag-chatbot.git
cd mutual-fund-rag-chatbot
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

### Step 2 — Set up your API key

```bash
cp .env.example .env
# Edit .env and add your Groq key:
# GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

### Step 3 — Initialize the vector store

This uses the built-in seed data (fastest, no scraping required):

```bash
python -m embedder.pipeline --seed --reset
```

> Alternatively, to scrape live data from all 15 URLs first, run `python -m scrapers.runner`, then `python -m embedder.pipeline --reset`.

### Step 4 — Start the backend

```bash
python -m backend.main
# → Runs on http://0.0.0.0:8000
```

### Step 5 — Start the frontend

In a **separate terminal**:

```bash
cd frontend
npm install
npm run dev
# → Open http://localhost:5173 in your browser
```

### (Optional) Step 6 — Start the daily refresh scheduler

```bash
python scheduler.py
# → Refreshes data every day at 10:00 AM IST
# → Press Ctrl+C to stop
```

---

## 🔌 API Reference

### `POST /api/chat`

Send a question and receive an answer with source citations.

**Request:**
```json
{
  "message": "What is the NAV of Parag Parikh Flexi Cap Fund?"
}
```

**Response:**
```json
{
  "answer": "The current NAV (Net Asset Value) of Parag Parikh Flexi Cap Fund (Direct Plan) is ₹89.77.",
  "source_urls": ["https://www.indmoney.com/mutual-funds/..."]
}
```

### `GET /api/status`

Returns the last time the data was refreshed (shown in the chat header).

```json
{
  "last_updated": "10 Mar 2026, 10:00 AM",
  "status": "success",
  "version": "1.0.0"
}
```

---

## 🛡️ Guardrail Behaviour

The chatbot enforces strict rules to keep answers safe and factual:

| Query Type | What Happens |
|-----------|-------------|
| Factual question (NAV, exit load, etc.) | ✅ Answered with source citation |
| Investment advice ("Should I invest?") | ❌ Blocked — redirects to SEBI advisor |
| Personal info (PAN, folio, returns) | ❌ Blocked — PII refusal |
| Out of scope (random questions) | ℹ️ Friendly redirect to fund-related topics |
| No data found in vector store | ℹ️ "I'm INDy... I couldn't find relevant data for this." |

---

## 📊 Data Dictionary — All 4 Schemes

| Field | PPFCF | PPTSF | PPCHF | PPLF |
|-------|-------|-------|-------|------|
| Category | Flexi Cap | ELSS | Conservative Hybrid | Liquid |
| Lock-in | None | 3 years | None | None |
| Riskometer | Very High | Very High | Moderately High | Low to Moderate |
| Min SIP | ₹1,000 | ₹500 | ₹1,000 | ₹1,000 |
| Exit Load | 2% (≤365d), 1% (365-730d), Nil | Nil (ELSS lock-in) | 1% (≤365d), Nil after | Graded (Day 1–6), Nil from Day 7 |
| Expense Ratio | 0.63% | 0.70% | 0.98% | 0.18% |
| NAV (09-Mar-2026) | ₹89.77 | ₹31.85 | ₹15.80 | ₹1517.90 |
| Benchmark | NIFTY 500 TRI | NIFTY 500 TRI | CRISIL Hybrid 85+15 | NIFTY Liquid Index |

> NAV values are updated daily by the scheduler at 10 AM IST from AMFI's public API. Values shown above reflect the last recorded update.

---

## ⚠️ Known Limitations

- **Facts only** — no live return computations, no portfolio tracking
- **No investment advice** — guardrails will block any such queries
- **NAV is T-1** — daily NAV becomes available overnight; the scheduler fetches it each morning at 10 AM
- **Scope is limited** to the 4 PPFAS schemes listed above
- **Scheduler requires your machine to be on** — for cloud deployment, use GitHub Actions or a server cron job

---

*Project by Sourabh Sharma | Built with Groq, ChromaDB, React, and FastAPI | March 2026*
