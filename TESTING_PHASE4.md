# Phase 4 Testing Guide: FastAPI Backend & React Frontend

This guide explains how to boot up both the new FastAPI backend server and the React frontend to test the Chat UI. It uses the `mutual_funds_seed.json` data, so no prior scraping is strictly required.

---

## 🏗️ Step 1: Ensure Vector Store is Initialised

If you haven't run the embedding indexer yet, you must do so. It will load the built-in seed data into ChromaDB.

```bash
# In the project root (mutual-fund-rag-chatbot)
python -m embedder.pipeline --seed
```

---

## 🧠 Step 2: Start the FastAPI Backend

The backend needs the Gemini API key to generate answers.

1. Open a terminal in the project root.
2. Export your API key:
   ```bash
   export GEMINI_API_KEY="AIzaSy...your_gemini_key..."
   ```
3. Start the FastAPI server using `uvicorn`:
   ```bash
   python -m backend.main
   ```
   *You should see output indicating `Uvicorn running on http://0.0.0.0:8000`*

---

## 🎨 Step 3: Start the React Frontend

1. Open a **new, separate terminal tab** in the project root.
2. Change into the `frontend` directory:
   ```bash
   cd frontend
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *You should see output indicating `Local: http://localhost:5173/`*

---

## 🧪 Step 4: UI Testing Instructions

Open `http://localhost:5173/` in your browser. You will see a mobile-styled chat interface matching the INDmoney mockup.

### Things to test:

1. **Initial State & Layout:**
   - Verify the top bar reads **"PPFAS Assistant"** with a green icon.
   - Verify the persistent disclaimer **"Facts-only. Not investment advice."** sits above the quick-action pills.
   - Ensure the UI looks like a clean mobile container.

2. **Quick Action Pills:**
   - Click the **"Check Exit Load"** pill.
   - The question should immediately appear as a user message.
   - The typing indicator (bouncing dots) should appear while waiting for the backend.
   - The bot should reply with the exit load information (max 3 sentences) and a clickable green citation link below it.

3. **Guardrails Check:**
   - Click the **"Should I Invest?"** pill, or manually type *"Which fund should I buy?"*.
   - A quick reply should appear stating that it only provides facts and recommending a SEBI advisor, with AMFI links. The backend pre-filter blocks this before hitting Gemini.

4. **Empty Database / Error Handling:**
   - If you stop the FastAPI server and try to send a message, the UI should gracefully display: `"Sorry, I am unable to connect to the server right now."`

5. **Scroll Behaviour:**
   - Ask 4-5 questions in succession.
   - The chat window should automatically scroll to the bottom as new messages arrive.
