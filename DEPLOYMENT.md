# Deployment Guide

This project is split into two deployed services:
- **Backend** (FastAPI) → [Render](https://render.com) (free tier)  
- **Frontend** (React/Vite) → [Vercel](https://vercel.com) (free tier)

---

## Step 1 — Deploy Backend to Render

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo: `sourabhsharmaaa/mutual-fund-rag-chatbot`
3. Render will auto-detect `render.yaml` — click **Apply**.
4. In the **Environment** section, add these secrets:
   | Key | Value |
   |---|---|
   | `GROQ_API_KEY` | your Groq key |
   | `GEMINI_API_KEY` | your Gemini key |
   | `FRONTEND_URL` | your Vercel URL (e.g. `https://your-app.vercel.app`) |
5. Click **Deploy**.
6. Once deployed, copy your Render URL: `https://ppfas-rag-backend.onrender.com`

> **Note**: Free Render instances spin down after 15 min of inactivity. The first request each day may take ~30 seconds to "wake up".

---

## Step 2 — Set API URL in Vercel

1. Go to your project in [vercel.com](https://vercel.com)
2. **Settings** → **Environment Variables**
3. Add:
   | Key | Value |
   |---|---|
   | `VITE_API_URL` | `https://ppfas-rag-backend.onrender.com/api/chat` |
4. **Redeploy** the frontend (Deployments → Redeploy latest).

---

## Step 3 — Seed the vector store (first time only)

Since the `vector_store/` directory is committed to Git, Render will use the pre-built ChromaDB on startup. No action needed unless you want a fresh re-index.

To re-index on Render, run in the Render Shell:
```bash
python -m embedder.pipeline --seed --reset
```

---

## GitHub Actions — Daily Data Refresh

The workflow in `.github/workflows/daily_update.yml` runs daily at **10:00 AM IST** (4:30 AM UTC) to:
1. Re-scrape all 15 data sources
2. Re-index ChromaDB
3. Commit updated `data/` and `vector_store/` back to the repo

Render auto-deploys on every push, so the data is always fresh.

To trigger manually: GitHub → **Actions** → **Daily RAG Data Update** → **Run workflow**.
