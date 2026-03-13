# PPFAS Mutual Fund RAG Chatbot

An LLM-powered RAG (Retrieval-Augmented Generation) chatbot designed specifically for Parag Parikh Mutual Funds (PPFAS). It provides factual, cite-backed data about fund schemes, tax implications, and operational procedures.

## 🧐 What is this project?
This project is an **AI-driven Knowledge Assistant** that specializes in the Parag Parikh Mutual Fund (PPFAS) ecosystem. Unlike general-purpose chatbots, this system is grounded in the actual scheme documents, FAQs, and factual data of PPFAS. It can answer specific questions about exit loads, expense ratios, fund managers, and tax treatments with high precision and verifiable sources.

## 🎯 Why we made this?
Navigating mutual fund documents (SIDs, KIMs, and Factsheets) can be overwhelming for the average investor. We built this to:
1.  **Simplify Information**: Transform complex PDF/Web data into instant, conversational answers.
2.  **Ensure Safety**: Implement strict guardrails to prevent AI from giving unsolicited "investment advice" or opinions, ensuring only factual data is shared.
3.  **Enhance Efficiency**: Provide a "Multi-Fund Planner" that allows investors to compare and analyze multiple schemes simultaneously without digging through separate pages.

## 🛠️ How it works & What we used
We used a **Retrieval-Augmented Generation (RAG)** architecture to build this, ensuring the AI only talks about what it can "read" in the official documents.

### 1. The Data Pipeline (Scrapers & Embedder)
- **Scraping**: We use **Playwright** to crawl the official PPFAS AMC website and fetch structured data.
- **Vector Storage**: Extracted text is broken into chunks and stored in **ChromaDB**.
- **Semantic Search**: We use the `all-MiniLM-L6-v2` transformer model to create "embeddings" so the bot understands the *meaning* of your question, not just keywords.

### 2. The Intelligence Layer (LLM & Groq)
- **Inference**: We use **Gemini 1.5 Flash** via **Groq** for lightning-fast response times.
- **Reasoning**: The LLM receives the relevant chunks of data and synthesizes a concise, factual answer.

### 3. The Safety Engine (Guardrails)
- **Hybrid Hub**: A custom dual-stage guardrail system.
- **Pre-Filter**: Blocks queries asking for advice or PII before they even reach the AI.
- **Post-Filter**: Sanitizes the output to ensure no hallucinations or links leak into the response.

## 📺 Demo

![Project Demo Video](assets/demo.mov)

## ✨ Key Features

- **🎯 Context-Aware RAG**: Uses semantic search over PPFAS scheme documents and FAQs to provide accurate, factual answers.
- **📊 Multi-Fund Planner**: Select multiple funds in the sidebar to trigger a specialized comparison interface with pre-built analysis chips.
- **🛡️ Hybrid Guardrails**: Dual-stage filtering (Pre and Post) ensures the bot strictly follows domain constraints, avoids investment advice, and maintains PII safety.
- **🔗 Automatic Citations**: Every factual answer includes verified source links from the official AMC website or independent platforms like INDmoney.
- **⚡ Fast Inference**: Powered by Gemini 1.5 Flash via Groq for near-instant responses.

## 🏗️ Tech Stack

- **Frontend**: React (Vite), TypeScript, Vanilla CSS
- **Backend**: FastAPI (Python)
- **Vector Database**: ChromaDB
- **Embeddings**: Sentence-Transformers (`all-MiniLM-L6-v2`)
- **LLM**: Gemini 1.5 Flash (via Groq)

## 📁 Project Structure

- `/backend`: FastAPI service handling chat, retrieval, and guardrails.
- `/frontend`: Modern React UI with real-time streaming and interactive sidebar.
- `/embedder`: Data ingestion pipeline and ChromaDB integration.
- `/scrapers`: Playwright-based web scrapers for AMC data.

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.9+
- Node.js & npm
- Groq API Key
- Playwright Chromium

### 1. Install Backend Dependencies
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Environment Variables
```bash
export GROQ_API_KEY="your-groq-key"
```

### 3. Initialize the Vector Store
```bash
python -m embedder.pipeline --seed --reset
```

### 4. Run the Backend API
```bash
python -m backend.main
```
Runs on `http://localhost:8000`.

### 5. Run the Frontend UI
```bash
cd frontend
npm run dev
```
Access the UI at `http://localhost:5173`.
