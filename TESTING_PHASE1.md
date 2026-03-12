# TESTING_PHASE1.md — Manual Verification Guide

## Phase 1: Data Ingestion — Manual QA Checklist

Use this guide to verify the output of the scraper **before** moving to Phase 2 (vector embeddings).

---

## Step 1: Run the Scraper

```bash
# From the project root
cd /path/to/mutual-fund-rag-chatbot

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install Playwright Chromium browser
playwright install chromium

# 3. Run the scraper (takes ~5–15 minutes for all 15 URLs)
python -m scrapers.runner
```

Expected output:
- A progress log showing `[01/15]` through `[15/15]`
- ✅ for successful scrapes, ⚠️ for 404 (AMFI pages), ❌ for any unexpected errors
- A final summary table showing all 4 schemes

---

## Step 2: Verify Output Files Exist

```bash
# Should print the file path (not "No such file")
ls -lh data/structured/mutual_funds.json
ls -lh logs/scrape_log.json
ls -lh data/raw/
```

Expected:
- `data/structured/mutual_funds.json` — the main output file
- `logs/scrape_log.json` — per-URL log with timestamps and statuses
- `data/raw/01_scheme_facts.json` through `data/raw/15_general_knowledge.json` — raw per-URL dumps

---

## Step 3: Validate JSON Is Well-Formed

```bash
# Should print: "4 schemes found. JSON is valid."
python3 -c "
import json
with open('data/structured/mutual_funds.json') as f:
    d = json.load(f)
n = len(d.get('schemes', []))
print(f'{n} schemes found. JSON is valid.')
assert n == 4, 'ERROR: Expected 4 schemes!'
"
```

---

## Step 4: Check Each Scheme Has Required Fields

```bash
python3 -c "
import json
REQUIRED = ['expense_ratio','exit_load','min_sip_amount','riskometer',
            'benchmark','fund_manager','lock_in_period']
with open('data/structured/mutual_funds.json') as f:
    d = json.load(f)
for s in d['schemes']:
    na = [f for f in REQUIRED if s.get(f) in ('NA', None, '')]
    status = '❌ MISSING' if na else '✅ OK'
    print(f\"{status} [{s['short_name']}] {s['scheme_name']}\")
    if na: print(f'   NA fields: {na}')
"
```

---

## Step 5: Manual Cross-Check Against Live URLs

Open each URL below in your browser and compare the scraped value in `mutual_funds.json` against what you see on the page.

### PPFCF — Parag Parikh Flexi Cap Fund

| Field | Expected (approx.) | Check URL |
|---|---|---|
| `expense_ratio` | ~0.57% | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229) |
| `exit_load` | 2% ≤365d, 1% 366-730d, Nil >730d | [PPFAS](https://amc.ppfas.com/schemes/parag-parikh-flexi-cap-fund/) |
| `min_sip_amount` | ₹1,000 | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229) |
| `riskometer` | Very High | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229) |
| `benchmark` | NIFTY 500 TRI | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229) |
| `fund_manager` | Rajeev Thakkar (+ others) | [PPFAS](https://amc.ppfas.com/schemes/parag-parikh-flexi-cap-fund/) |
| `lock_in_period` | None | [PPFAS](https://amc.ppfas.com/schemes/parag-parikh-flexi-cap-fund/) |

### PPTSF — Parag Parikh ELSS Tax Saver Fund

| Field | Expected | Check URL |
|---|---|---|
| `expense_ratio` | ~0.7% | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-tax-saver-fund-direct-growth-1002345) |
| `exit_load` | Nil (ELSS lock-in applies) | [PPFAS](https://amc.ppfas.com/schemes/parag-parikh-tax-saver-fund/) |
| `min_sip_amount` | ₹500 | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-tax-saver-fund-direct-growth-1002345) |
| `lock_in_period` | **3 years** | [PPFAS](https://amc.ppfas.com/schemes/parag-parikh-tax-saver-fund/) |
| `riskometer` | Very High | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-tax-saver-fund-direct-growth-1002345) |

### PPCHF — Parag Parikh Conservative Hybrid Fund

| Field | Expected | Check URL |
|---|---|---|
| `expense_ratio` | ~0.9% | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1004652) |
| `riskometer` | Moderately High | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1004652) |
| `benchmark` | CRISIL Hybrid 85+15 | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1004652) |

### PPLF — Parag Parikh Liquid Fund

| Field | Expected | Check URL |
|---|---|---|
| `exit_load` | Nil | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-3180) |
| `riskometer` | Low to Moderate | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-3180) |
| `benchmark` | NIFTY Liquid Index | [IndMoney](https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-3180) |

---

## Step 6: Check the Scrape Log for Errors

```bash
python3 -c "
import json
with open('logs/scrape_log.json') as f:
    log = json.load(f)
for e in log['entries']:
    icon = '✅' if e['status'] == 'ok' else '⚠️ ' if e['status'] == '404' else '❌'
    print(f\"{icon} [{e['id']:02d}] {e['status']:8s} | {e.get('elapsed_ms',0):.0f}ms | {e['description']}\")
"
```

Expected:
- All 15 URLs should show `ok`
- No URLs with status `error` or `timeout` (if any, check your internet and retry)

---

## Step 7: Verify FAQs Were Collected

```bash
python3 -c "
import json
with open('data/structured/mutual_funds.json') as f:
    d = json.load(f)
faqs = d.get('faqs', [])
print(f'Total FAQs collected: {len(faqs)}')
# Find statement/CAS related FAQs
cas_faqs = [f for f in faqs if any(
    kw in (f.get('question','') + f.get('answer','')).lower()
    for kw in ['statement','download','cas','cams']
)]
print(f'Statement/CAS FAQs: {len(cas_faqs)}')
for faq in cas_faqs[:3]:
    print(f\"  Q: {faq['question'][:80]}\")
    print(f\"  A: {faq.get('answer','')[:100]}\")
    print()
"
```

---

## Step 8: Check Taxation Data

```bash
python3 -c "
import json
with open('data/structured/mutual_funds.json') as f:
    d = json.load(f)
tax = d.get('taxation', {})
print('LTCG rate:', tax.get('ltcg_rate', 'NA'))
print('STCG rate:', tax.get('stcg_rate', 'NA'))
print('ELSS benefit (first 200 chars):', str(tax.get('elss_tax_benefit','NA'))[:200])
"
```

---

## Step 9: source_url Present on Every Entry

```bash
python3 -c "
import json
with open('data/structured/mutual_funds.json') as f:
    d = json.load(f)
missing = 0
for s in d['schemes']:
    if not s.get('source_urls'):
        print(f\"  ❌ [{s['short_name']}] has no source_urls!\")
        missing += 1
for faq in d.get('faqs', []):
    if not faq.get('source_url'):
        missing += 1
if missing == 0:
    print('✅ All entries have source URLs.')
else:
    print(f'❌ {missing} entries are missing source URLs.')
"
```

---

## Step 10: Decision Gate — Ready for Phase 2?

| Check | Criterion | Pass? |
|---|---|---|
| All 4 schemes present | `len(schemes) == 4` | ☐ |
| Each scheme has ≤2 NA fields from REQUIRED set | — | ☐ |
| At least 1 FAQ found | `len(faqs) > 0` | ☐ |
| Taxation LTCG/STCG rates found | Not "NA" | ☐ |
| All entries have `source_url` | — | ☐ |
| No unexpected `error` statuses in scrape log | — | ☐ |

**If all checks pass → proceed to Phase 2 (ChromaDB vector embeddings).**

If any scheme has more than 2 NA fields, you can:
1. Re-run the scraper: `python -m scrapers.runner`
2. Or manually patch the JSON by editing `data/structured/mutual_funds.json`
   (add the correct value with the source URL noted in the `source_urls` array)

---

## Known Expected Behaviours (Not Bugs)

| Behaviour | Reason |
|---|---|
| `expense_ratio` may show a TER page link for PPFAS | PPFAS links to a separate TER disclosure page instead of an inline value |
| `fund_size_aum` may be "NA" | IndMoney may require login for AUM on some scheme views |
| AMFI pages (11, 12, 15) show React/CSS in raw dump | New AMFI site is React-rendered; Playwright handles it, but raw text may include inline CSS strings |
