# Phase 5 — Scheduler (Auto-Refresh)

## ⏰ What is this phase doing? (Plain English)

Mutual fund data changes over time — NAV prices update every day, expense ratios can change, and new FAQs may appear. If we never refresh our data, the chatbot will gradually give stale, outdated answers.

This phase is like setting an **alarm clock** for the chatbot. Every day at **10:00 AM IST**, the scheduler automatically:

1. Visits all 15 websites again (Phase 1 — scraping)
2. Fetches the latest NAV from the AMFI API
3. Rebuilds the vector store with fresh data (Phase 2 — embeddings)
4. Updates the "Data last updated" timestamp shown in the chat header

No manual action needed — it just runs in the background while you sleep.

## 🤔 Do I need this running all the time?

- **For development/demos:** No. The seed data in the vector store is good enough for demos
- **For a live deployment:** Yes. Run `python scheduler.py` on a machine that stays on (like a server or always-on PC)
- Without the scheduler running, the data only refreshes when you manually re-run the pipeline

## 🌐 What about GitHub Actions?

GitHub Actions is a cloud version of this same idea — it can trigger the scheduler on a server even when your laptop is off. For this homework project, the local scheduler is sufficient.

## ⚙️ Technical Details — Source Code: `scheduler.py`

| Feature | Detail |
|---------|--------|
| Scheduling library | APScheduler |
| Trigger | Cron — fires at exactly 10:00 AM IST every day |
| Timezone | `Asia/Kolkata` (IST) |
| On startup | Runs the pipeline **immediately** so data is fresh right away |
| On each run | Scrape → fetch NAV → re-embed → update `data/metadata.json` |

## Configure the schedule

To change the time, edit `scheduler.py`:
```python
scheduler.add_job(
    ...,
    trigger="cron",
    hour=10,    # ← change this (24-hour format)
    minute=0,   # ← change this
)
```

## ▶️ How to run this phase

```bash
python scheduler.py
```

Press `Ctrl+C` to stop it.
