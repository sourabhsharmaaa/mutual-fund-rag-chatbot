"""
pipeline.py
-----------
Phase 2 — Embedding Pipeline entry point.

Usage:
    python -m embedder.pipeline                     # uses data/structured/mutual_funds.json
    python -m embedder.pipeline --seed              # uses built-in seed data (no scraper needed)
    python -m embedder.pipeline --reset             # wipes ChromaDB before indexing
    python -m embedder.pipeline --seed --reset      # fresh index from seed data

Embedding model strategy (in priority order):
  1. Google text-embedding-004  — if GEMINI_API_KEY env var is set
  2. ChromaDB default           — sentence-transformers/all-MiniLM-L6-v2 (local, no key)

The pipeline will print which model is active so you know exactly what's running.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
DATA_JSON = ROOT / "data" / "structured" / "mutual_funds.json"
SEED_JSON = ROOT / "data" / "structured" / "mutual_funds_seed.json"
VECTOR_STORE_DIR = ROOT / "vector_store"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


# ---------------------------------------------------------------------------
# HuggingFace Inference API Embedding Function
# ---------------------------------------------------------------------------

class HuggingFaceInferenceEmbeddingFunction:
    """
    Uses HuggingFace Inference API for embeddings — no local model download needed.
    Model: sentence-transformers/all-MiniLM-L6-v2 (same as before, but via API)

    Requires HF_API_TOKEN environment variable.
    Get a free token at: https://huggingface.co/settings/tokens
    """

    def __init__(self, api_token: str, model_id: str = "sentence-transformers/all-MiniLM-L6-v2"):
        import requests as req
        self._requests = req
        self._api_token = api_token
        self._url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_id}"
        self._headers = {"Authorization": f"Bearer {api_token}"}

    def __call__(self, input: list) -> list:  # type: ignore
        """Embed a list of strings via HF Inference API."""
        response = self._requests.post(
            self._url,
            headers=self._headers,
            json={"inputs": input, "options": {"wait_for_model": True}},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Embedding function factory
# ---------------------------------------------------------------------------

def _build_embedding_function():
    """
    Returns the best available ChromaDB-compatible embedding function.

    Priority:
      1. HuggingFace Inference API (if HF_API_TOKEN set) — lightweight, no local download
      2. Google text-embedding-004 (if GEMINI_API_KEY set) — fallback
      3. None — ChromaDB uses dummy (search won't work; for dev/testing only)
    """
    # 1. Try HuggingFace Inference API
    hf_token = os.environ.get("HF_API_TOKEN", "").strip()
    if hf_token:
        try:
            ef = HuggingFaceInferenceEmbeddingFunction(api_token=hf_token)
            logger.info("✅ Embedding model: HuggingFace all-MiniLM-L6-v2 (via Inference API)")
            return ef
        except Exception as exc:
            logger.warning("HuggingFace EF init failed (%s). Trying Gemini.", exc)

    # 2. Try Google Gemini API
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction  # type: ignore
            ef = GoogleGenerativeAiEmbeddingFunction(
                api_key=api_key,
                model_name="models/text-embedding-004",
            )
            logger.info("✅ Embedding model: Google text-embedding-004")
            return ef
        except Exception as exc:
            logger.warning("Google embedding init failed (%s). Using None.", exc)

    # 3. No API key — warn loudly
    logger.warning(
        "⚠️  No HF_API_TOKEN or GEMINI_API_KEY found! "
        "Semantic search will NOT work. Set HF_API_TOKEN in your environment."
    )
    return None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class EmbeddingPipeline:

    def __init__(self, use_seed: bool = False, reset: bool = False):
        self.use_seed = use_seed
        self.reset = reset

    def run(self) -> dict[str, Any]:
        print(f"\n{'='*60}")
        print(f"  PPFAS RAG Chatbot — Phase 2 Embedding Pipeline")
        print(f"  Started: {_now()}")
        print(f"{'='*60}\n")

        # 1. Load data
        data = self._load_data()

        # 2. Chunk
        from .chunker import MutualFundChunker
        chunker = MutualFundChunker()
        chunks = chunker.chunk_all(data)
        logger.info("Chunker produced %d chunks.", len(chunks))
        self._print_chunk_distribution(chunks)

        # 3. Build embedding function
        ef = _build_embedding_function()

        # 4. Init ChromaDB store
        from .chroma_store import ChromaStore
        store = ChromaStore(embedding_fn=ef)

        if self.reset:
            logger.info("--reset flag: wiping existing collections...")
            store.reset()

        # 5. Upsert chunks
        logger.info("Upserting %d chunks into ChromaDB...", len(chunks))
        counts = store.upsert(chunks)

        # 6. Verify
        stats = store.stats()
        logger.info("ChromaDB stats after upsert: %s", stats)

        # 7. Summary
        result = {
            "completed_at": _now(),
            "chunks_produced": len(chunks),
            "upserted": counts,
            "chroma_stats": stats,
            "vector_store_path": str(VECTOR_STORE_DIR),
        }
        self._print_summary(result)
        return result

    # -----------------------------------------------------------------------
    # Data loading
    # -----------------------------------------------------------------------

    def _load_data(self) -> dict[str, Any]:
        # User-specified seed flag
        if self.use_seed:
            if SEED_JSON.exists():
                logger.info("Loading seed data from %s", SEED_JSON)
                return json.loads(SEED_JSON.read_text(encoding="utf-8"))
            else:
                logger.warning("Seed JSON not found at %s. Using built-in minimal seed.", SEED_JSON)
                return _BUILTIN_SEED

        # Primary: live scraped JSON
        if DATA_JSON.exists():
            logger.info("Loading scraped data from %s", DATA_JSON)
            return json.loads(DATA_JSON.read_text(encoding="utf-8"))

        # Auto-fallback to seed
        logger.warning(
            "mutual_funds.json not found (scraper not yet run). "
            "Using seed data for indexing. Run `python -m scrapers.runner` first for full data."
        )
        if SEED_JSON.exists():
            return json.loads(SEED_JSON.read_text(encoding="utf-8"))
        return _BUILTIN_SEED

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _print_chunk_distribution(chunks: list[dict]) -> None:
        from collections import Counter
        dist = Counter(c["field_type"] for c in chunks)
        by_fund = Counter(c["short_name"] for c in chunks)
        print("\n  Chunk distribution by field_type:")
        for ft, count in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"    {ft:<35} {count:>4} chunks")
        print("\n  Chunk distribution by fund:")
        for fund, count in sorted(by_fund.items(), key=lambda x: -x[1]):
            print(f"    {fund:<10} {count:>4} chunks")
        print()

    @staticmethod
    def _print_summary(result: dict) -> None:
        print(f"\n{'='*60}")
        print(f"  PHASE 2 COMPLETE")
        print(f"{'='*60}")
        print(f"  Chunks produced  : {result['chunks_produced']}")
        print(f"  Upserted         : {result['upserted']}")
        print(f"  ChromaDB stats   : {result['chroma_stats']}")
        print(f"  Vector store     : {result['vector_store_path']}")
        print(f"  Completed at     : {result['completed_at']}")
        print(f"{'='*60}\n")
        print("  ✅ Ready for Phase 3. Run test_retrieval.py to validate.\n")


# ---------------------------------------------------------------------------
# Built-in minimal seed data (used when no JSON & no seed file exist)
# ---------------------------------------------------------------------------
# This ensures the pipeline runs immediately even before running the scraper.

_BUILTIN_SEED: dict[str, Any] = {
    "scraped_at": "2026-03-03T00:29:00+05:30",
    "schemes": [
        {
            "scheme_name":    "Parag Parikh Flexi Cap Fund",
            "short_name":     "PPFCF",
            "category":       "Flexi Cap",
            "lock_in_period": "None",
            "expense_ratio":  "0.63%",
            "exit_load":      "2% if redeemed within 365 days; 1% if redeemed between 365–730 days; Nil if redeemed after 730 days.",
            "min_sip_amount": "₹1,000",
            "min_lumpsum_amount": "₹1,000 (New) / ₹1,000 (Additional)",
            "riskometer":     "Very High",
            "benchmark":      "NIFTY 500 TRI",
            "fund_manager":   ["Rajeev Thakkar", "Rukun Tarachandani", "Raunak Onkar"],
            "fund_size_aum":  "NA",
            "nav":            "89.77",
            "nav_as_of":      "09-Mar-2026",
            "source_urls":    [
                "https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229",
            ],
        },
        {
            "scheme_name":    "Parag Parikh ELSS Tax Saver Fund",
            "short_name":     "PPTSF",
            "category":       "ELSS",
            "lock_in_period": "3 years (mandatory ELSS lock-in)",
            "expense_ratio":  "0.70%",
            "exit_load":      "Nil (units are locked in for 3 years; no exit load applicable)",
            "min_sip_amount": "₹500",
            "min_lumpsum_amount": "₹500",
            "riskometer":     "Very High",
            "benchmark":      "NIFTY 500 TRI",
            "fund_manager":   ["Rajeev Thakkar", "Rukun Tarachandani", "Raunak Onkar"],
            "fund_size_aum":  "NA",
            "nav":            "31.85",
            "nav_as_of":      "09-Mar-2026",
            "source_urls":    [
                "https://www.indmoney.com/mutual-funds/parag-parikh-elss-tax-saver-fund-direct-growth-1004710",
            ],
        },
        {
            "scheme_name":    "Parag Parikh Conservative Hybrid Fund",
            "short_name":     "PPCHF",
            "category":       "Conservative Hybrid",
            "lock_in_period": "None",
            "expense_ratio":  "0.98%",
            "exit_load":      "1% if redeemed within 365 days; Nil after 365 days.",
            "min_sip_amount": "₹1,000",
            "min_lumpsum_amount": "₹5,000 (New) / ₹1,000 (Additional)",
            "riskometer":     "Moderately High",
            "benchmark":      "CRISIL Hybrid 85+15 - Conservative Index",
            "fund_manager":   ["Rajeev Thakkar", "Rukun Tarachandani", "Raunak Onkar"],
            "fund_size_aum":  "NA",
            "nav":            "15.80",
            "nav_as_of":      "09-Mar-2026",
            "source_urls":    [
                "https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1006619",
            ],
        },
        {
            "scheme_name":    "Parag Parikh Liquid Fund",
            "short_name":     "PPLF",
            "category":       "Liquid",
            "lock_in_period": "None",
            "expense_ratio":  "0.18%",
            "exit_load":      "Graded exit load: 0.0070% on Day 1 down to 0.0045% on Day 6; Nil from Day 7 onwards",
            "min_sip_amount": "₹1,000",
            "min_lumpsum_amount": "₹5,000 (New) / ₹1,000 (Additional)",
            "riskometer":     "Low to Moderate",
            "benchmark":      "NIFTY Liquid Index B-I",
            "fund_manager":   ["Rajeev Thakkar", "Rukun Tarachandani"],
            "fund_size_aum":  "NA",
            "nav":            "1517.90",
            "nav_as_of":      "09-Mar-2026",
            "source_urls":    [
                "https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-1214",
            ],
        },
        {
            "scheme_name":    "Parag Parikh Dynamic Asset Allocation Fund",
            "short_name":     "PPDAAF",
            "category":       "Dynamic Asset Allocation",
            "lock_in_period": "None",
            "expense_ratio":  "0.31% (Direct)",
            "exit_load":      "Nil",
            "min_sip_amount": "₹1,000",
            "min_lumpsum_amount": "₹5,000 (New) / ₹1,000 (Additional)",
            "riskometer":     "Moderate",
            "benchmark":      "CRISIL Hybrid 50+50 - Moderate Index",
            "fund_manager":   ["Rajeev Thakkar", "Raunak Onkar"],
            "fund_size_aum":  "NA",
            "source_urls":    [
                "https://amc.ppfas.com/schemes/parag-parikh-dynamic-asset-allocation-fund/",
            ],
        },
    ],
    "faqs": [
        {
            "question": "How can I download my account statement / CAS for PPFAS funds?",
            "answer": (
                "You can download your Consolidated Account Statement (CAS) through two RTAs: "
                "CAMS at https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement "
                "or KFintech at https://mfs.kfintech.com/investor/General/ConsolidatedAccountStatement. "
                "You can also use MFCentral at https://www.mfcentral.com to view and download a Summary CAS "
                "or Detailed CAS. Register on MFCentral with your email and choose the desired period."
            ),
            "source_url": "https://www.amfiindia.com/online-center/download-cas",
        },
        {
            "question": "What is the minimum investment amount for Parag Parikh Flexi Cap Fund?",
            "answer": "The minimum new purchase amount for PPFCF is ₹1,000. Additional purchases also require a minimum of ₹1,000. The minimum monthly SIP amount is ₹1,000 and the minimum quarterly SIP is ₹3,000.",
            "source_url": "https://amc.ppfas.com/faqs/scheme-specific-faqs/index.php",
        },
        {
            "question": "What is the tax benefit for investing in PPFAS ELSS Tax Saver Fund?",
            "answer": "Investments in Parag Parikh ELSS Tax Saver Fund qualify for tax deduction under Section 80C of the Income Tax Act up to ₹1.5 lakh per financial year. The fund has a mandatory 3-year lock-in period.",
            "source_url": "https://amc.ppfas.com/faqs/scheme-specific-faqs/index.php",
        },
        {
            "question": "Who can invest in Parag Parikh Flexi Cap Fund?",
            "answer": (
                "Resident adult individuals (singly or jointly), HUF Kartas, minors through guardian, "
                "partnership firms, companies, NRIs/PIOs, FIIs registered with SEBI, banks, and other "
                "categories as permitted by SEBI regulations can invest in PPFCF."
            ),
            "source_url": "https://amc.ppfas.com/faqs/scheme-specific-faqs/index.php",
        },
    ],
    "general_knowledge": {
        "riskometer_definition": (
            "SEBI's Riskometer measures the risk level of a mutual fund scheme on a scale of 6 levels: "
            "Low, Low to Moderate, Moderate, Moderately High, High, and Very High. "
            "The riskometer helps investors understand the potential risk before investing."
        ),
        "expense_ratio_definition": (
            "The Total Expense Ratio (TER) or expense ratio is the annual fee charged by a mutual fund "
            "as a percentage of its average daily Net Asset Value (NAV). It covers fund management fees, "
            "administrative costs, and distribution expenses. A lower expense ratio means more returns "
            "pass through to investors. SEBI mandates daily disclosure of TER by AMCs."
        ),
        "cas_download_procedure": (
            "To download your Consolidated Account Statement (CAS): "
            "Option 1 — CAMS: Visit https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement, "
            "enter your registered email and PAN. "
            "Option 2 — KFintech: Visit https://mfs.kfintech.com and request CAS by email. "
            "Option 3 — MFCentral: Register at https://www.mfcentral.com, choose Summary CAS or Detailed CAS, "
            "and select your preferred period."
        ),
        "risk_levels": [
            "Low — Principal at low risk, e.g., overnight funds",
            "Low to Moderate — Principal at low to moderate risk, e.g., liquid funds",
            "Moderate — Principal at moderate risk, e.g., hybrid funds",
            "Moderately High — Principal at moderately high risk, e.g., large cap equity",
            "High — Principal at high risk, e.g., mid cap / small cap equity",
            "Very High — Principal at very high risk, e.g., flexi cap, ELSS funds",
        ],
        "source_urls": [
            "https://www.amfiindia.com/online-center/download-cas",
            "https://www.amfiindia.com/online-center/risk-o-meter",
            "https://www.amfiindia.com/investor/knowledge-center-info?zoneName=expenseRatio",
        ],
    },
    "taxation": {
        "ltcg_rate": "12.5%",
        "ltcg_details": (
            "Long-Term Capital Gains (LTCG) on equity mutual funds (held > 1 year) are taxed at 12.5% "
            "on gains exceeding ₹1.25 lakh per financial year. Gains up to ₹1.25 lakh are tax-free."
        ),
        "stcg_rate": "20%",
        "stcg_details": (
            "Short-Term Capital Gains (STCG) on equity mutual funds (held ≤ 1 year) are taxed at 20% "
            "flat, regardless of the investor's income tax slab."
        ),
        "elss_tax_benefit": (
            "Investments in ELSS (Equity Linked Savings Scheme) funds like PPTSF qualify for deduction "
            "under Section 80C of the Income Tax Act, up to ₹1.5 lakh per financial year. "
            "ELSS has a mandatory 3-year lock-in period."
        ),
        "summary": "Mutual fund taxation in India varies by fund type (equity vs debt) and holding period.",
        "source_url": "https://www.indmoney.com/articles/mutual-funds/mutual-fund-taxation",
    },
    "amc_overview": {},
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2 — PPFAS Embedding Pipeline"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Use seed JSON instead of scraped mutual_funds.json",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the ChromaDB collections before indexing",
    )
    args = parser.parse_args()

    pipeline = EmbeddingPipeline(use_seed=args.seed, reset=args.reset)
    pipeline.run()


if __name__ == "__main__":
    main()
