# Phase 1 — Data Ingestion (Scraping)

## 🌐 What is this phase doing? (Plain English)

Think of this phase like a **research assistant** who goes to the internet, visits 15 different websites, reads all the page content about Parag Parikh Mutual Funds, and brings it back to save in a structured notebook.

This is the very first step. Without this data, the chatbot would have nothing to answer from.

## 🔍 Which websites are visited?

The assistant visits 3 types of websites:
- **PPFAS official website** (`amc.ppfas.com`) — the fund house's own pages for each scheme
- **INDmoney** (`indmoney.com`) — a third-party platform that shows fund details
- **AMFI India** (`amfiindia.com`) — the official mutual fund regulator's website

Across these sites, it collects info like: exit loads, expense ratios, fund managers, SIP minimums, risk levels, FAQs, and taxation rules.

## 📦 What does it produce?

After visiting all 15 pages, it creates a clean file:
```
data/structured/mutual_funds.json
```
This is a single, organized file containing everything the chatbot needs to know — like a curated fact sheet for all 4 PPFAS funds.

## ⚙️ Technical Details — Source Code in `scrapers/`

| File | Purpose |
|------|---------|
| `scrapers/base_scraper.py` | Shared browser utilities (opens pages, waits for content to load) |
| `scrapers/ppfas_scraper.py` | Scrapes `amc.ppfas.com` — exit load, expense ratio, fund manager, etc. |
| `scrapers/indmoney_scraper.py` | Scrapes `indmoney.com` — SIP minimums, riskometer, lumpsum amounts |
| `scrapers/amfi_scraper.py` | Scrapes `amfiindia.com` — riskometer definitions, CAS download info |
| `scrapers/general_scraper.py` | Scrapes general MF knowledge pages and FAQs |
| `scrapers/nav_fetcher.py` | Fetches the latest NAV (daily price) of each fund from the AMFI public API |
| `scrapers/runner.py` | The master controller — runs all scrapers in order and saves the final output |

## ▶️ How to run this phase

```bash
python -m scrapers.runner
```
