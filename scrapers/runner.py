"""
runner.py
---------
Master orchestrator for Phase 1 — Data Ingestion.

Usage:
    python -m scrapers.runner

Reads all 15 URLs, dispatches the right scraper for each,
merges per-scheme data from multiple sources, and writes:
  - data/structured/mutual_funds.json   (final merged output)
  - data/raw/{url_id:02d}_*.json        (per-URL raw dumps)
  - logs/scrape_log.json                (per-URL status log)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .indmoney_scraper import IndMoneySchemeScraper, IndMoneyAmcScraper
from .ppfas_scraper import PPFASSchemeScraper, PPFASFaqScraper, PPFASSIDScraper
from .amfi_scraper import AMFIKnowledgeScraper
from .general_scraper import TaxationArticleScraper
from .nav_fetcher import fetch_latest_navs

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
DATA_STRUCTURED = ROOT / "data" / "structured"
DATA_RAW = ROOT / "data" / "raw"
LOGS_DIR = ROOT / "logs"

for d in (DATA_STRUCTURED, DATA_RAW, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# IST timezone
# ---------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> str:
    return datetime.now(IST).isoformat()


# ---------------------------------------------------------------------------
# Source registry — all 15 URLs
# ---------------------------------------------------------------------------
SOURCE_REGISTRY: list[dict] = [
    # ── PPFAS official scheme pages (URLs 5–8) ───────────────────────────
    {
        "id": 5,
        "url": "https://amc.ppfas.com/schemes/parag-parikh-flexi-cap-fund/",
        "scraper_class": PPFASSchemeScraper,
        "scheme": "PPFCF",
        "type": "scheme_facts",
        "description": "PPFAS — PPFCF official scheme page",
    },
    {
        "id": 6,
        "url": "https://amc.ppfas.com/schemes/parag-parikh-tax-saver-fund/",
        "scraper_class": PPFASSchemeScraper,
        "scheme": "PPTSF",
        "type": "scheme_facts",
        "description": "PPFAS — PPTSF official scheme page",
    },
    {
        "id": 7,
        "url": "https://amc.ppfas.com/schemes/parag-parikh-conservative-hybrid-fund/",
        "scraper_class": PPFASSchemeScraper,
        "scheme": "PPCHF",
        "type": "scheme_facts",
        "description": "PPFAS — PPCHF official scheme page",
    },
    {
        "id": 8,
        "url": "https://amc.ppfas.com/schemes/parag-parikh-liquid-fund/",
        "scraper_class": PPFASSchemeScraper,
        "scheme": "PPLF",
        "type": "scheme_facts",
        "description": "PPFAS — PPLF official scheme page",
    },
    # ── IndMoney scheme pages (URLs 1–4) ─────────────────────────────────
    {
        "id": 1,
        "url": "https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229",
        "scraper_class": IndMoneySchemeScraper,
        "scheme": "PPFCF",
        "type": "scheme_facts",
        "description": "IndMoney — PPFCF scheme page",
    },
    {
        "id": 2,
        "url": "https://www.indmoney.com/mutual-funds/parag-parikh-tax-saver-fund-direct-growth-1002345",
        "scraper_class": IndMoneySchemeScraper,
        "scheme": "PPTSF",
        "type": "scheme_facts",
        "description": "IndMoney — PPTSF scheme page",
    },
    {
        "id": 3,
        "url": "https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1006619",
        "scraper_class": IndMoneySchemeScraper,
        "scheme": "PPCHF",
        "type": "scheme_facts",
        "description": "IndMoney — PPCHF scheme page",
    },
    {
        "id": 4,
        "url": "https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-3180",
        "scraper_class": IndMoneySchemeScraper,
        "scheme": "PPLF",
        "type": "scheme_facts",
        "description": "IndMoney — PPLF scheme page",
    },
    # ── PPFAS Scheme-Specific FAQs (URL 9) ───────────────────────────────
    {
        "id": 9,
        "url": "https://amc.ppfas.com/faqs/scheme-specific-faqs/index.php",
        "scraper_class": PPFASFaqScraper,
        "scheme": "ALL",
        "type": "faqs",
        "description": "PPFAS — Scheme-specific FAQs (all schemes, incl. statement download)",
    },
    # ── PPFAS SID downloads page (URL 10) ────────────────────────────────
    {
        "id": 10,
        "url": "https://amc.ppfas.com/downloads/kim-sid-and-sai/",
        "scraper_class": PPFASSIDScraper,
        "scheme": "ALL",
        "type": "sid_links",
        "description": "PPFAS — SID/KIM document download page",
    },
    # ── AMFI pages (URLs 11–12) ───────────────────────────────────────────
    {
        "id": 11,
        "url": "https://www.amfiindia.com/online-center/download-cas",
        "scraper_class": AMFIKnowledgeScraper,
        "scheme": "ALL",
        "type": "general_knowledge",
        "description": "AMFI — Download CAS (CAMS / KFintech / MFCentral procedure)",
    },
    {
        "id": 12,
        "url": "https://www.amfiindia.com/online-center/risk-o-meter",
        "scraper_class": AMFIKnowledgeScraper,
        "scheme": "ALL",
        "type": "general_knowledge",
        "description": "AMFI — Risk-o-Meter definitions",
    },
    # ── IndMoney AMC overview (URL 13) ────────────────────────────────────
    {
        "id": 13,
        "url": "https://www.indmoney.com/mutual-funds/amc/parag-parikh-mutual-fund",
        "scraper_class": IndMoneyAmcScraper,
        "scheme": "ALL",
        "type": "amc_overview",
        "description": "IndMoney — PPFAS AMC overview page",
    },
    # ── IndMoney taxation article (URL 14) ───────────────────────────────
    {
        "id": 14,
        "url": "https://www.indmoney.com/articles/mutual-fund-taxation",
        "scraper_class": TaxationArticleScraper,
        "scheme": "ALL",
        "type": "taxation",
        "description": "IndMoney — Mutual Fund taxation article",
    },
    # ── AMFI expense ratio / TER page (URL 15) ───────────────────────────
    {
        "id": 15,
        "url": "https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio",
        "scraper_class": AMFIKnowledgeScraper,
        "scheme": "ALL",
        "type": "general_knowledge",
        "description": "AMFI — Expense Ratio / TER regulation definitions",
    },
]


# ---------------------------------------------------------------------------
# SCHEME METADATA — static facts to seed / fill gaps from scraping
# ---------------------------------------------------------------------------
SCHEME_META: dict[str, dict] = {
    "PPFCF": {
        "scheme_name":  "Parag Parikh Flexi Cap Fund",
        "short_name":   "PPFCF",
        "category":     "Flexi Cap",
        "lock_in_period": "None",
        "riskometer":   "Very High",
        "exit_load":    "2% if redeemed within 365 days; 1% if redeemed between 365 and 730 days; Nil after 730 days",
        "benchmark":    "NIFTY 500 TRI (Primary); NIFTY 50 TRI (Additional)",
        "fund_manager": "Rajeev Thakkar, Raunak Onkar, Raj Mehta",
        "min_lumpsum_amount": "₹1,000",
        "min_sip_amount": "₹1,000",
        "expense_ratio": "0.63%",
        "source_urls":  [],
    },
    "PPTSF": {
        "scheme_name":  "Parag Parikh ELSS Tax Saver Fund",
        "short_name":   "PPTSF",
        "category":     "ELSS",
        "lock_in_period": "3 years (mandatory ELSS lock-in)",
        "riskometer":   "Very High",
        "exit_load":    "Nil (ELSS — mandatory 3-year lock-in, redemption not permitted before that)",
        "benchmark":    "NIFTY 500 TRI (Primary); NIFTY 50 TRI (Additional)",
        "fund_manager": "Rajeev Thakkar, Raunak Onkar, Raj Mehta",
        "min_lumpsum_amount": "₹500",
        "min_sip_amount": "₹500",
        "expense_ratio": "0.62%",
        "source_urls":  [],
    },
    "PPCHF": {
        "scheme_name":  "Parag Parikh Conservative Hybrid Fund",
        "short_name":   "PPCHF",
        "category":     "Conservative Hybrid",
        "lock_in_period": "None",
        "riskometer":   "Moderately High",
        "exit_load":    "2% if redeemed within 365 days; 1% if redeemed between 365 and 730 days; Nil after 730 days",
        "benchmark":    "CRISIL Hybrid 85+15 Conservative Index",
        "fund_manager": "Rajeev Thakkar, Raunak Onkar, Raj Mehta, Rukun Tarachandani",
        "min_lumpsum_amount": "₹1,000",
        "min_sip_amount": "₹1,000",
        "expense_ratio": "0.34%",
        "source_urls":  [],
    },
    "PPLF": {
        "scheme_name":  "Parag Parikh Liquid Fund",
        "short_name":   "PPLF",
        "category":     "Liquid",
        "lock_in_period": "None",
        "riskometer":   "Low to Moderate",
        "exit_load":    "Graded exit load: 0.0070% on Day 1 down to 0.0045% on Day 6; Nil from Day 7 onwards",
        "benchmark":    "NIFTY Liquid Fund Index",
        "fund_manager": "Raj Mehta, Raunak Onkar",
        "min_lumpsum_amount": "₹5,000",
        "min_sip_amount": "₹1,000",
        "expense_ratio": "0.11%",
        "source_urls":  [],
    },
}

# Fields that get merged — later sources preferred over "NA"
SCHEME_FIELDS = [
    "expense_ratio", "exit_load", "min_sip_amount",
    "riskometer", "benchmark", "fund_manager",
    "fund_size_aum", "category", "lock_in_period",
    "date_of_allotment", "investment_objective", "sid_link",
    "nav", "nav_as_of",
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class ScraperRunner:

    def __init__(self):
        self.scrape_log: list[dict] = []
        self.raw_results: list[dict] = []

    async def run_all(self) -> dict[str, Any]:
        """
        Run all 15 scrapers sequentially (to respect rate limits),
        merge results, and return the final consolidated data dict.
        """
        print(f"\n{'='*60}")
        print(f"  PPFAS RAG Chatbot — Phase 1 Data Ingestion")
        print(f"  Started: {now_ist()}")
        print(f"{'='*60}\n")

        raw_by_id: dict[int, dict] = {}

        for entry in SOURCE_REGISTRY:
            url_id = entry["id"]
            url = entry["url"]
            description = entry["description"]
            scraper_cls = entry["scraper_class"]

            print(f"[{url_id:02d}/15] Scraping: {description}")
            print(f"        URL: {url}")

            scraper = scraper_cls()
            result = await scraper.scrape(url)

            # Save raw result
            raw_by_id[url_id] = result.to_dict()
            self.raw_results.append(result.to_dict())

            # Write individual raw dump
            raw_filename = DATA_RAW / f"{url_id:02d}_{entry['type']}.json"
            raw_filename.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # Build log entry
            log_entry = {
                "id": url_id,
                "url": url,
                "description": description,
                "status": result.status,
                "elapsed_ms": result.elapsed_ms,
                "field_count": result.field_count,
                "error": result.error_message or None,
                "scraped_at": now_ist(),
            }
            self.scrape_log.append(log_entry)

            status_icon = "✅" if result.status == "ok" else "⚠️ " if result.status == "404" else "❌"
            print(
                f"        {status_icon} Status: {result.status} | "
                f"{result.field_count} fields | {result.elapsed_ms:.0f}ms\n"
            )

            # Small delay between requests to be a good citizen
            await asyncio.sleep(2)

        # Merge all results into final output
        final_output = self._merge_results(raw_by_id)

        # Write outputs
        self._write_outputs(final_output)
        self._print_summary(final_output)

        return final_output

    def _merge_results(self, raw_by_id: dict[int, dict]) -> dict[str, Any]:
        """
        Merge per-URL raw results into the consolidated output schema.
        Rules:
          - Start each scheme with SCHEME_META defaults
          - For each field, prefer the first non-"NA" value found
          - PPFAS official pages preferred over IndMoney for structural fields
          - Source URLs always accumulated
        """
        schemes_data: dict[str, dict] = {}
        for key, meta in SCHEME_META.items():
            schemes_data[key] = {
                **meta,
                **{f: "NA" for f in SCHEME_FIELDS},
                # Restore curated values from meta (don't overwrite with NA)
                "lock_in_period": meta["lock_in_period"],
                "category": meta["category"],
                "riskometer": meta.get("riskometer", "NA"),
                "exit_load": meta.get("exit_load", "NA"),
                "benchmark": meta.get("benchmark", "NA"),
                "fund_manager": meta.get("fund_manager", "NA"),
                "min_lumpsum_amount": meta.get("min_lumpsum_amount", "NA"),
                "min_sip_amount": meta.get("min_sip_amount", "NA"),
                "expense_ratio": meta.get("expense_ratio", "NA"),
            }

        faqs_combined: list[dict] = []
        general_knowledge: dict[str, Any] = {
            "riskometer_definition": "NA",
            "expense_ratio_definition": "NA",
            "cas_download_procedure": "NA",
            "risk_levels": [],
            "source_urls": [],
        }
        taxation_data: dict[str, Any] = {
            "ltcg_rate": "NA",
            "ltcg_details": "NA",
            "stcg_rate": "NA",
            "stcg_details": "NA",
            "elss_tax_benefit": "NA",
            "summary": "NA",
            "source_url": "NA",
        }
        amc_overview: dict[str, Any] = {}
        sid_links: dict[str, str] = {}

        # Process results in order — PPFAS pages (5-8) after IndMoney (1-4)
        # so PPFAS data can fill gaps
        for entry in SOURCE_REGISTRY:
            url_id = entry["id"]
            if url_id not in raw_by_id:
                continue

            raw = raw_by_id[url_id]
            if raw["status"] not in ("ok",):
                continue  # skip failed / 404 URLs

            url = raw["source_url"]
            data = raw.get("data", {})
            scheme_key = entry.get("scheme", "ALL")
            entry_type = entry.get("type", "")

            # ── Scheme facts (URLs 1–8) ───────────────────────────────
            if entry_type == "scheme_facts" and scheme_key in schemes_data:
                sd = schemes_data[scheme_key]

                # Accumulate source URL
                if url not in sd["source_urls"]:
                    sd["source_urls"].append(url)

                # Merge fields — only overwrite "NA"
                field_map = {
                    "expense_ratio":     "expense_ratio",
                    "exit_load":         "exit_load",
                    "min_sip_amount":    "min_sip_amount",
                    "fund_size_aum":     "fund_size_aum",
                    "riskometer":        "riskometer",
                    "benchmark":         "benchmark",
                    "fund_manager":      "fund_manager",
                    "lock_in_period":    "lock_in_period",
                    "date_of_allotment": "date_of_allotment",
                    "investment_objective": "investment_objective",
                    "sid_link":          "sid_link",
                }
                for data_key, scheme_field in field_map.items():
                    val = data.get(data_key)
                    if val and val != "NA" and sd.get(scheme_field) in ("NA", None, ""):
                        # Special handling: avoid overwriting valid numbers with "Refer TER page" placeholders
                        if scheme_field == "expense_ratio":
                            if "Refer" in val or "visit" in val.lower() or "ratio" in val.lower():
                                continue
                        # Special lock_in handling — don't overwrite curated value
                        if scheme_field == "lock_in_period" and sd["lock_in_period"] != "NA":
                            continue
                        sd[scheme_field] = val

            # ── FAQs (URL 9) ──────────────────────────────────────────
            elif entry_type == "faqs":
                raw_faqs = data.get("faqs", [])
                for faq in raw_faqs:
                    faqs_combined.append({**faq, "source_url": url})
                # Statement-specific FAQs highlighted
                for sfaq in data.get("statement_faqs", []):
                    sfaq_with_url = {**sfaq, "source_url": url}
                    if sfaq_with_url not in faqs_combined:
                        faqs_combined.append(sfaq_with_url)

            # ── SID links (URL 10) ────────────────────────────────────
            elif entry_type == "sid_links":
                sid_links = data.get("sid_links", {})

            # ── General knowledge (URLs 11, 12, 15) ───────────────────
            elif entry_type == "general_knowledge":
                if url not in general_knowledge["source_urls"]:
                    general_knowledge["source_urls"].append(url)

                if data.get("cas_procedure") and general_knowledge["cas_download_procedure"] == "NA":
                    general_knowledge["cas_download_procedure"] = data["cas_procedure"]

                if data.get("risk_levels") and not general_knowledge["risk_levels"]:
                    general_knowledge["risk_levels"] = data["risk_levels"]

                if data.get("expense_ratio_definition") and general_knowledge["expense_ratio_definition"] == "NA":
                    general_knowledge["expense_ratio_definition"] = data["expense_ratio_definition"]

                if data.get("main_content") and general_knowledge["riskometer_definition"] == "NA":
                    if "riskometer" in url.lower():
                        general_knowledge["riskometer_definition"] = data["main_content"][:1000]

            # ── AMC overview (URL 13) ──────────────────────────────────
            elif entry_type == "amc_overview":
                amc_overview = {**data, "source_url": url}

            # ── Taxation (URL 14) ──────────────────────────────────────
            elif entry_type == "taxation":
                for field in ["ltcg_rate", "ltcg_details", "stcg_rate", "stcg_details",
                               "elss_tax_benefit"]:
                    if data.get(field) and data[field] != "NA":
                        taxation_data[field] = data[field]
                if data.get("article_summary"):
                    taxation_data["summary"] = data["article_summary"]
                taxation_data["source_url"] = url

        # Attach SID links to scheme records
        for scheme_key, sid_url in sid_links.items():
            if scheme_key in schemes_data and sid_url != "NA":
                if schemes_data[scheme_key].get("sid_link") == "NA":
                    schemes_data[scheme_key]["sid_link"] = sid_url

        # Fetch live NAVs from AMFI API and inject into scheme records
        print("\n>>> Fetching live NAVs from mfapi.in...")
        nav_data = fetch_latest_navs()
        for scheme_key, nav_info in nav_data.items():
            if scheme_key in schemes_data and nav_info["nav"] != "NA":
                schemes_data[scheme_key]["nav"] = nav_info["nav"]
                schemes_data[scheme_key]["nav_as_of"] = nav_info["as_of"]
                print(f"  {scheme_key}: ₹{nav_info['nav']} (as of {nav_info['as_of']})")
        print()

        return {
            "scraped_at": now_ist(),
            "total_urls_attempted": len(SOURCE_REGISTRY),
            "total_urls_ok": sum(1 for e in self.scrape_log if e["status"] == "ok"),
            "schemes": list(schemes_data.values()),
            "faqs": faqs_combined,
            "general_knowledge": general_knowledge,
            "taxation": taxation_data,
            "amc_overview": amc_overview,
        }

    def _write_outputs(self, final_output: dict[str, Any]) -> None:
        # Final merged JSON
        out_path = DATA_STRUCTURED / "mutual_funds.json"
        out_path.write_text(
            json.dumps(final_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✅ Written: {out_path}")

        # Scrape log
        log_path = LOGS_DIR / "scrape_log.json"
        log_payload = {
            "run_at": now_ist(),
            "entries": self.scrape_log,
        }
        log_path.write_text(
            json.dumps(log_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✅ Written: {log_path}")

    def _print_summary(self, output: dict[str, Any]) -> None:
        ok = output["total_urls_ok"]
        total = output["total_urls_attempted"]
        schemes = output["schemes"]
        faqs = output["faqs"]

        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}")
        print(f"  URLs scraped successfully : {ok}/{total}")
        print(f"  Schemes in output        : {len(schemes)}")
        print(f"  FAQs collected           : {len(faqs)}")
        print()

        for s in schemes:
            na_fields = [f for f in SCHEME_FIELDS if s.get(f) in ("NA", None)]
            print(f"  [{s['short_name']}] {s['scheme_name']}")
            print(f"    ├─ expense_ratio  : {s.get('expense_ratio', 'NA')}")
            print(f"    ├─ exit_load      : {s.get('exit_load', 'NA')[:60]}")
            print(f"    ├─ min_sip_amount : {s.get('min_sip_amount', 'NA')}")
            print(f"    ├─ riskometer     : {s.get('riskometer', 'NA')}")
            print(f"    ├─ benchmark      : {s.get('benchmark', 'NA')}")
            print(f"    ├─ fund_manager   : {s.get('fund_manager', 'NA')}")
            print(f"    ├─ lock_in_period : {s.get('lock_in_period', 'NA')}")
            print(f"    └─ NA fields      : {na_fields or 'none'}")
            print()

        print(f"  Completed: {now_ist()}")
        print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    runner = ScraperRunner()
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
