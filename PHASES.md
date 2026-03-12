# Project Phases — PPFAS Mutual Fund RAG Chatbot

This document defines the 5 phases of the project and the scope of each.

---

## Phase 1 — Data Ingestion (Scraping)

**Goal:** Collect raw mutual fund data from PPFAS and third-party sources.

**Components:**
- `scrapers/ppfas_scraper.py` — Scrapes `amc.ppfas.com` scheme pages (exit load, expense ratio, fund manager, etc.)
- `scrapers/indmoney_scraper.py` — Scrapes `indmoney.com` for additional fields (SIP minimums, riskometer, etc.)
- `scrapers/amfi_scraper.py` — Scrapes `amfiindia.com` for general MF knowledge and riskometer definitions
- `scrapers/general_scraper.py` — Scrapes FAQs and general knowledge pages
- `scrapers/base_scraper.py` — Shared Playwright-based scraping utilities
- `scrapers/runner.py` — Orchestrates all scrapers, writes `data/raw/*.json` and `data/structured/mutual_funds.json`

**Output:** `data/structured/mutual_funds.json` — single structured JSON with 4 schemes, FAQs, taxation, and general knowledge.

---

## Phase 2 — Embeddings & Vector Store

**Goal:** Convert structured data into semantic vector embeddings stored in ChromaDB.

**Components:**
- `embedder/chunker.py` — Breaks scheme fields (exit_load, expense_ratio, etc.) into individual text chunks with metadata
- `embedder/chroma_store.py` — ChromaDB wrapper with two collections: `ppfas_scheme_facts` and `ppfas_general`
- `embedder/pipeline.py` — End-to-end pipeline: loads data → chunks → embeds → upserts into ChromaDB
  - `--seed` flag: uses built-in seed data instead of `mutual_funds.json`
  - `--reset` flag: wipes + rebuilds the vector store from scratch

**Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (local, no API key needed)

**Output:** `vector_store/` — ChromaDB persistent storage directory.

---

## Phase 3 — RAG Core & Guardrails

**Goal:** Retrieve relevant chunks and generate grounded, safe answers using an LLM.

**Components:**
- `backend/services/retriever.py` — Wraps ChromaDB; semantic search returning `RetrievalResult` objects
- `backend/services/generator.py` — Full RAG pipeline: pre-filter → retrieve → build prompt → call Groq LLM → post-filter
- `backend/services/guardrails.py` — Pre-filter (blocks investment advice, PII, competitor mentions) and post-filter (sentence cap, citation injection)
- `tests/test_sandbox.py` — Interactive CLI test tool to manually test retrieval + generation

**LLM:** Groq (`llama-3.1-8b-instant`) — requires `GROQ_API_KEY` env variable.

---

## Phase 4 — Backend API & Frontend UI

**Goal:** Expose the RAG engine as a REST API and build a mobile-style chat UI.

**Components:**
- `backend/main.py` — FastAPI app entry point; starts uvicorn on port 8000
- `backend/routers/chat.py` — `POST /api/chat` and `GET /api/status` endpoints
- `backend/models/` — Pydantic request/response models
- `frontend/` — Vite + React + TypeScript single-page chat application
  - `frontend/src/components/ChatWindow.tsx` — Main chat interface, handles send/receive
  - `frontend/src/components/MessageBubble.tsx` — Renders individual messages with timestamps and source chips
  - `frontend/src/index.css` — All styling (mobile-first, INDmoney-inspired design)

**Running locally:**
```bash
# Backend (port 8000)
export GROQ_API_KEY="your_key_here"
python -m backend.main

# Frontend (port 5173)
cd frontend && npm run dev
```

---

## Phase 5 — Scheduler (Auto-refresh)

**Goal:** Keep the vector store up-to-date by automatically re-scraping and re-embedding on a schedule.

**Components:**
- `scheduler.py` — APScheduler-based job that runs the full scrape → embed pipeline at configurable intervals

**Default schedule:** Daily refresh of all data sources.

**Running:**
```bash
python scheduler.py
```
