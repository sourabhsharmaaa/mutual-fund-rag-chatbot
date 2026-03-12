# Phase 3 — RAG Core & Guardrails

## 🤖 What is this phase doing? (Plain English)

This is the **brain** of the chatbot. When a user asks a question, this phase does 3 things:

1. **Find** — searches the vector store (built in Phase 2) to find the most relevant fund facts
2. **Think** — passes those facts to an AI language model (Llama via Groq) and asks it to form an answer *using only those facts*
3. **Filter** — before and after the AI responds, it runs safety checks (called guardrails) to ensure the answer is appropriate, honest, and within scope

This pattern — "Retrieve, then Generate" — is called **RAG (Retrieval-Augmented Generation)**. It stops the AI from making things up, because it can only answer using the data we give it.

## 🚦 What are Guardrails?

Guardrails are rules that protect the chatbot from giving harmful or incorrect answers. Think of them like a bouncer at the door:

| Guardrail | What it blocks |
|-----------|---------------|
| Pre-filter (before AI) | Investment advice, personal info requests (PAN, name), competitor questions |
| Post-filter (after AI) | Answers that are too long (capped at 5 sentences), leaking source URLs into the text |

If guardrails are triggered, the chatbot returns a safe, pre-written response instead of the AI's answer.

## ⚙️ Technical Details — Source Code in `backend/services/`

| File | Purpose |
|------|---------|
| `backend/services/retriever.py` | Queries ChromaDB and returns ranked, relevant fact chunks |
| `backend/services/generator.py` | Full RAG pipeline: pre-filter → retrieve → build prompt → call Groq LLM → post-filter |
| `backend/services/guardrails.py` | Implements pre-filter (block unsafe queries) and post-filter (clean up responses) |

## 🔑 LLM Used

- **Model:** `llama-3.1-8b-instant` via [Groq Cloud](https://console.groq.com)
- **Requires:** `GROQ_API_KEY` set in your `.env` file

## ▶️ How to manually test this phase

```bash
python tests/test_sandbox.py
```
This opens an interactive prompt where you can type questions and see what the RAG engine retrieves and returns.
