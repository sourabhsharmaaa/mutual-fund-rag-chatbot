"""
test_retrieval.py
-----------------
Phase 2 manual verification script.

Runs a set of hardcoded test queries against the ChromaDB vector store
and prints the top-3 retrieved chunks to the terminal so you can
manually judge retrieval quality.

Usage:
    # First, build the index:
    python -m embedder.pipeline --seed

    # Then run this:
    python tests/test_retrieval.py

    # With Google embeddings (set your key first):
    GEMINI_API_KEY=your_key python tests/test_retrieval.py
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

# Make sure project root is on sys.path when run directly
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from embedder.chroma_store import ChromaStore # type: ignore


# ---------------------------------------------------------------------------
# Test queries — covering all 4 schemes + FAQs + guardrail edge cases
# ---------------------------------------------------------------------------

TEST_QUERIES: list[dict] = [
    # ── Scheme facts ──────────────────────────────────────────────────────
    {
        "query":       "What is the exit load for Parag Parikh Flexi Cap?",
        "fund_filter": "PPFCF",
        "expect_field": "exit_load",
    },
    {
        "query":       "What is the expense ratio of Parag Parikh ELSS Tax Saver Fund?",
        "fund_filter": "PPTSF",
        "expect_field": "expense_ratio",
    },
    {
        "query":       "What is the minimum SIP for the Conservative Hybrid Fund?",
        "fund_filter": "PPCHF",
        "expect_field": "min_sip",
    },
    {
        "query":       "What is the riskometer rating of Parag Parikh Liquid Fund?",
        "fund_filter": "PPLF",
        "expect_field": "riskometer",
    },
    {
        "query":       "Who are the fund managers of Parag Parikh Flexi Cap Fund?",
        "fund_filter": "PPFCF",
        "expect_field": "fund_manager",
    },
    {
        "query":       "What is the lock-in period for the PPFAS tax saver fund?",
        "fund_filter": "PPTSF",
        "expect_field": "lock_in",
    },
    # ── Cross-scheme queries (no fund filter) ─────────────────────────────
    {
        "query":       "Which PPFAS fund has a 3-year lock-in?",
        "fund_filter": None,
        "expect_field": "lock_in",
    },
    {
        "query":       "benchmark index for all PPFAS schemes",
        "fund_filter": None,
        "expect_field": "benchmark",
    },
    # ── FAQs ──────────────────────────────────────────────────────────────
    {
        "query":       "How do I download my mutual fund account statement?",
        "fund_filter": None,
        "expect_field": "faq",
    },
    {
        "query":       "How to get CAS from CAMS or KFintech?",
        "fund_filter": None,
        "expect_field": "faq",
    },
    # ── Taxation ──────────────────────────────────────────────────────────
    {
        "query":       "What is the LTCG tax rate on equity mutual funds?",
        "fund_filter": None,
        "expect_field": "taxation_ltcg",
    },
    {
        "query":       "How much is STCG tax on short term equity mutual fund redemption?",
        "fund_filter": None,
        "expect_field": "taxation_stcg",
    },
    {
        "query":       "Section 80C tax benefit ELSS",
        "fund_filter": None,
        "expect_field": "taxation_elss",
    },
    # ── General knowledge ─────────────────────────────────────────────────
    {
        "query":       "What does a 'Very High' riskometer rating mean?",
        "fund_filter": None,
        "expect_field": "riskometer_definition",
    },
    {
        "query":       "What is Total Expense Ratio TER?",
        "fund_filter": None,
        "expect_field": "expense_ratio_definition",
    },
]


# ---------------------------------------------------------------------------
# Embedding function (same factory as in pipeline.py)
# ---------------------------------------------------------------------------

def _build_embedding_function():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction # type: ignore
            return GoogleGenerativeAiEmbeddingFunction(
                api_key=api_key,
                model_name="models/text-embedding-004",
            )
        except Exception:
            pass
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction # type: ignore
        return SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

SEP  = "─" * 70
SEP2 = "═" * 70

def _print_result(rank: int, result: dict, expected_field: str) -> None:
    hit = "✅" if result["field_type"] == expected_field else "⚠️ "
    print(f"  {hit} Rank {rank} | field={result['field_type']} | "
          f"fund={result['short_name']} | dist={result['distance']:.4f}")
    # Wrap text nicely
    wrapped = textwrap.fill(result["text"], width=66,
                            initial_indent="     ", subsequent_indent="     ")
    print(wrapped)
    print(f"     source: {result['source_url']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_tests(n_results: int = 3) -> None:
    print(f"\n{SEP2}")
    print("  PPFAS RAG — Phase 2 Retrieval Verification")
    print(f"  ChromaDB path: {ROOT / 'vector_store'}")
    print(f"{SEP2}\n")

    ef = _build_embedding_function()
    store = ChromaStore(embedding_fn=ef)
    stats = store.stats()

    print(f"  ChromaDB stats: {stats}")
    total = sum(stats.values())
    if total == 0:
        print("\n  ❌ ChromaDB is empty! Run the pipeline first:")
        print("     python -m embedder.pipeline --seed")
        sys.exit(1)
    print(f"  Total indexed chunks: {total}\n")

    passed = 0
    warned = 0

    for i, test in enumerate(TEST_QUERIES, 1):
        query       = test["query"]
        fund_filter = test.get("fund_filter")
        expect      = test.get("expect_field", "")

        print(f"{SEP}")
        ff_label = f" [filter={fund_filter}]" if fund_filter else ""
        print(f"  Query {i:02d}{ff_label}: {query}")
        print(SEP)

        results = store.query(query, n_results=n_results, fund_filter=fund_filter)

        if not results:
            print("  ⚠️  No results returned (collection may be empty for this filter).")
            warned += 1
            print()
            continue

        top_field = results[0]["field_type"]
        if top_field == expect:
            passed += 1 # type: ignore
        else:
            warned += 1

        for rank, r in enumerate(results, 1):
            _print_result(rank, r, expect)
            if rank < len(results):
                print()
        print()

    # Final score
    print(SEP2)
    total_q = len(TEST_QUERIES)
    print(f"  RESULT: Top-1 field match: {passed}/{total_q} queries ✅")
    print(f"  ({warned} queries returned unexpected field_type — check manually)")
    print(SEP2)
    print()
    print("  Manual check guide:")
    print("  ✅ = retrieved chunk field_type matches expected field for that query")
    print("  ⚠️  = top result has different field_type — not necessarily wrong,")
    print("       check if the chunk text itself answers the question correctly.")
    print()


if __name__ == "__main__":
    run_tests()
