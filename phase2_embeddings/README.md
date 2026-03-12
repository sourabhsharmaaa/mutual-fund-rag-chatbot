# Phase 2 — Embeddings & Vector Store

## 🧠 What is this phase doing? (Plain English)

Imagine you have a notebook full of facts. Now you want to be able to **search** through that notebook intelligently — not just by keywords, but by *meaning*. If you search "how much does the Flexi Cap fund charge?", it should find the expense ratio, even if the exact words don't match.

That's what this phase does. It takes the structured data from Phase 1 and converts each fact into a **numerical fingerprint** (called an "embedding") that captures its meaning. These fingerprints are then stored in a special searchable database called **ChromaDB** — like a smart index for our facts.

## 🔢 What are "embeddings"?

An embedding is a list of numbers that represents the *meaning* of a sentence. Sentences with similar meanings get similar numbers. This lets the system find related facts even when the words are different.

For example:
- "What is the TER?" and "What is the expense ratio?" → same meaning → similar numbers → same chunks returned

## 📂 What does it produce?

A folder called `vector_store/` containing ChromaDB's database files — two collections:

| Collection | What's stored |
|------------|--------------|
| `ppfas_scheme_facts` | Fund-specific facts: NAV, exit load, expense ratio, fund managers, etc. |
| `ppfas_general` | FAQs, taxation info, CAS download steps, riskometer definitions |

## ⚙️ Technical Details — Source Code in `embedder/`

| File | Purpose |
|------|---------|
| `embedder/chunker.py` | Breaks each field (exit_load, NAV, etc.) into individual text sentences with metadata tags |
| `embedder/chroma_store.py` | Wrapper around ChromaDB — handles saving and searching the vector database |
| `embedder/pipeline.py` | End-to-end pipeline: loads data → chunks → embeds → saves to ChromaDB. Also contains built-in seed data as a fallback |

## 🤖 Embedding Model

`sentence-transformers/all-MiniLM-L6-v2` — runs fully locally on your machine, no internet or API key needed.

## ▶️ How to run this phase

```bash
# Using built-in seed data (fastest, recommended for first run):
python -m embedder.pipeline --seed --reset

# Or after running Phase 1 scrapers:
python -m embedder.pipeline --reset
```
