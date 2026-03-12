# Phase 4 — Backend API & Frontend UI

## 💬 What is this phase doing? (Plain English)

This phase is what you actually **see and use**. It has two parts:

### 🖥️ The Frontend (what the user sees)
A mobile-style chat interface built with **React**. It looks and feels like a WhatsApp/iMessage conversation — you type a question, press send, and a reply appears. It also shows timestamps, source chips (so you know where the answer came from), and suggestion chips to help you get started.

### ⚙️ The Backend (the engine behind the scenes)
A server built with **FastAPI** (Python) that runs on your computer. When the frontend sends a question, the backend:
1. Receives the question
2. Passes it through the RAG pipeline (Phase 3)
3. Returns the answer + sources back to the frontend

Think of it like a restaurant:
- The **frontend** is the dining room — the nice interface the customer interacts with
- The **backend** is the kitchen — where the actual work happens out of sight

## 🔗 API Endpoints

| Method | Endpoint | What it does |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send a question, receive an answer + source URLs |
| `GET` | `/api/status` | Returns the "Data last updated" timestamp shown in the header |
| `GET` | `/health` | Quick check to confirm the server is running |

## ⚙️ Technical Details

### Backend → `backend/`

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app entry point; starts the server on port 8000 |
| `backend/config.py` | Central config: model names, retrieval settings, API key loading |
| `backend/routers/chat.py` | Defines the `/api/chat` and `/api/status` endpoints |
| `backend/models/` | Data shapes for API requests and responses (using Pydantic) |

### Frontend → `frontend/`

| File | Purpose |
|------|---------|
| `frontend/src/components/ChatWindow.tsx` | Main chat interface — handles input, send, and message list |
| `frontend/src/components/MessageBubble.tsx` | Renders individual messages with timestamps and source chips |
| `frontend/src/types/chat.ts` | TypeScript type definition for a `ChatMessage` |
| `frontend/src/index.css` | All styling — INDmoney-inspired dark header design |

## ▶️ How to run this phase

```bash
# Terminal 1 — Start the backend server (port 8000):
python -m backend.main

# Terminal 2 — Start the frontend UI (port 5173):
cd frontend && npm run dev
```

Then open **http://localhost:5173** in your browser.
