"""
test_sandbox.py
---------------
Phase 3 — Interactive CLI test sandbox.

Starts an interactive loop. For each query you type, it prints:
  1. The retrieved text chunks (top-K from ChromaDB)
  2. The Gemini response (after post-filter and citation injection)
  3. The sentence count of the response body
  4. Whether a guardrail was triggered and why

Usage:
    # Make sure Phase 2 index is built first:
    python -m embedder.pipeline --seed

    # Set your Gemini API key:
    export GEMINI_API_KEY="your_key_here"

    # Run the sandbox:
    python tests/test_sandbox.py

    # Optional: pre-filter a specific fund
    python tests/test_sandbox.py --fund PPFCF

Special commands (type in the prompt):
    :quit / :exit / :q     — exit the sandbox
    :guardrails            — show a summary of all guardrail trigger lists
    :clear                 — clear the terminal
    :fund PPFCF            — set a fund filter for all subsequent queries
    :fund none             — remove the fund filter
    :help                  — show this help again
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# ANSI colour helpers (no external libs)
# ---------------------------------------------------------------------------

def _c(code: str, text: str) -> str:
    """Wrap text in ANSI colour code (skipped on Windows without ANSI support)."""
    if sys.platform == "win32" and not os.environ.get("ANSICON"):
        return text
    return f"\033[{code}m{text}\033[0m"


BOLD    = lambda t: _c("1", t)
DIM     = lambda t: _c("2", t)
GREEN   = lambda t: _c("32", t)
YELLOW  = lambda t: _c("33", t)
CYAN    = lambda t: _c("36", t)
RED     = lambda t: _c("31", t)
MAGENTA = lambda t: _c("35", t)

SEP  = DIM("─" * 72)
SEP2 = BOLD("═" * 72)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap(text: str, width: int = 70, indent: str = "    ") -> str:
    return textwrap.fill(text, width=width,
                         initial_indent=indent,
                         subsequent_indent=indent)


def _print_banner() -> None:
    print(f"\n{SEP2}")
    print(BOLD("  🤖  PPFAS RAG Chatbot — Phase 3 Test Sandbox"))
    print(DIM("  Powered by ChromaDB + Gemini 1.5 Flash"))
    print(f"{SEP2}")
    print(DIM("  Type your question and press Enter."))
    print(DIM("  Commands: :quit  :fund PPFCF  :fund none  :guardrails  :help"))
    print(f"{SEP2}\n")


def _print_help() -> None:
    print(f"\n{SEP}")
    print(CYAN("  Commands:"))
    print("    :quit / :exit / :q   — Exit")
    print("    :fund PPFCF          — Filter results to a specific fund")
    print("    :fund none           — Remove fund filter")
    print("    :guardrails          — Show guardrail trigger list summary")
    print("    :clear               — Clear screen")
    print("    :help                — Show this message")
    print(f"{SEP}\n")


def _print_guardrail_summary() -> None:
    print(f"\n{SEP}")
    print(YELLOW("  Active Guardrail Triggers:"))
    from backend.services.guardrails import ( # type: ignore
        _ADVICE_PHRASES, _PERF_PHRASES, _PII_PHRASES, _COMPETITOR_NAMES
    )
    print(f"\n  {BOLD('Advice/Opinion')} ({len(_ADVICE_PHRASES)} phrases):")
    print("    " + ", ".join(_ADVICE_PHRASES[:6]) + " ...")
    print(f"\n  {BOLD('Performance/Returns')} ({len(_PERF_PHRASES)} phrases):")
    print("    " + ", ".join(_PERF_PHRASES[:6]) + " ...")
    print(f"\n  {BOLD('PII')} ({len(_PII_PHRASES)} phrases):")
    print("    " + ", ".join(_PII_PHRASES[:4]) + " ...")
    print(f"\n  {BOLD('Competitor Names')} ({len(_COMPETITOR_NAMES)} names):")
    print("    " + ", ".join(_COMPETITOR_NAMES[:5]) + " ...")
    print(f"{SEP}\n")


def _print_chunks(chunks: list[dict], top_k: int = 3) -> None:
    print(f"\n{SEP}")
    print(CYAN(f"  RETRIEVED CHUNKS (top {min(top_k, len(chunks))} of {len(chunks)}):"))
    for i, chunk in enumerate(chunks[:top_k], 1): # type: ignore
        field = chunk.get("field_type", "?")
        fund  = chunk.get("short_name", "?")
        dist  = chunk.get("distance", 0)
        src   = chunk.get("source_url", "NA")
        text  = chunk.get("text", "")
        # Strip the [Source: ...] footer from displayed text (it's shown separately)
        import re
        clean_text = re.sub(r"\n\[Source:.*?\]$", "", text, flags=re.DOTALL).strip()

        print(f"\n  {BOLD(f'[{i}]')} {GREEN(field)} | {MAGENTA(fund)} | dist={dist:.4f}")
        print(_wrap(clean_text, width=68))
        print(DIM(f"    Source: {src}"))
    print(f"{SEP}\n")


def _print_response(result, fund_filter: str | None) -> None:
    from backend.services.guardrails import count_sentences # type: ignore

    print(SEP)
    if result.guardrail_triggered:
        print(YELLOW(f"  ⚠️  GUARDRAIL TRIGGERED [{result.guardrail_reason.upper()}]"))
        print()
        print(_wrap(result.answer, width=68))
    else:
        # Print retrieved chunks
        if result.retrieved_chunks:
            _print_chunks(result.retrieved_chunks, top_k=3)

        # Gemini response
        print(CYAN("  GEMINI RESPONSE:"))
        print()
        # Split on citation line for cleaner display
        parts = result.answer.split("\n\nLast updated from sources:")
        body = parts[0].strip()
        citation = "Last updated from sources:" + parts[1] if len(parts) > 1 else ""

        print(_wrap(body, width=68))
        if citation:
            print()
            print(DIM(f"    {citation.strip()}"))

    # Metadata line
    sc = count_sentences(result.answer)
    elapsed = result.elapsed_ms
    filter_note = f" | fund_filter={fund_filter}" if fund_filter else ""
    print()
    print(DIM(f"  ── sentences={sc}/3  elapsed={elapsed:.0f}ms{filter_note}"))
    print(f"{SEP}\n")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_sandbox(initial_fund_filter: str | None = None) -> None:
    _print_banner()

    # Check Gemini API key
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(RED("  ⚠️  GEMINI_API_KEY is not set."))
        print(DIM("  The pipeline will still run using ChromaDB retrieval only,"))
        print(DIM("  but Gemini generation will fail. Set the key with:"))
        print(DIM("      export GEMINI_API_KEY='your_key_here'"))
        print()

    # Check ChromaDB is populated
    try:
        from embedder.chroma_store import ChromaStore # type: ignore
        store = ChromaStore()
        stats = store.stats()
        total = sum(stats.values())
        if total == 0:
            print(RED("  ❌ ChromaDB is empty. Run the pipeline first:"))
            print(DIM("      python -m embedder.pipeline --seed"))
            print()
        else:
            print(GREEN(f"  ✅ ChromaDB ready: {stats}"))
            print()
    except Exception as e:
        print(RED(f"  ❌ Could not connect to ChromaDB: {e}"))
        print(DIM("  Run: python -m embedder.pipeline --seed"))
        return

    # Lazy-import generator
    from backend.services.generator import get_generator # type: ignore
    generator = get_generator()

    fund_filter = initial_fund_filter
    if fund_filter:
        print(GREEN(f"  Fund filter active: {fund_filter}"))
        print()

    # Interactive loop
    while True:
        try:
            prompt = input(BOLD("You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM('  Goodbye!')}\n")
            break

        if not prompt:
            continue

        # Handle special commands
        if prompt.lower() in (":quit", ":exit", ":q"):
            print(DIM("\n  Goodbye!\n"))
            break
        elif prompt.lower() == ":help":
            _print_help()
            continue
        elif prompt.lower() == ":guardrails":
            _print_guardrail_summary()
            continue
        elif prompt.lower() == ":clear":
            os.system("clear" if os.name != "nt" else "cls")
            _print_banner()
            continue
        elif prompt.lower().startswith(":fund "):
            arg = prompt[6:].strip().upper() # type: ignore
            if arg == "NONE":
                fund_filter = None
                print(DIM("  Fund filter removed.\n"))
            elif arg in ("PPFCF", "PPTSF", "PPCHF", "PPLF"):
                fund_filter = arg
                print(GREEN(f"  Fund filter set to: {fund_filter}\n"))
            else:
                print(YELLOW(f"  Unknown fund: {arg}. Choose from PPFCF, PPTSF, PPCHF, PPLF or none.\n"))
            continue

        # Generate response
        print(DIM("\n  Thinking..."))
        try:
            result = generator.generate(query=prompt, fund_filter=fund_filter)
            _print_response(result, fund_filter)
        except Exception as exc:
            print(RED(f"\n  Error: {exc}\n"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PPFAS RAG Chatbot — Phase 3 Interactive Sandbox"
    )
    parser.add_argument(
        "--fund",
        choices=["PPFCF", "PPTSF", "PPCHF", "PPLF"],
        default=None,
        help="Pre-set a fund filter for all queries",
    )
    args = parser.parse_args()
    run_sandbox(initial_fund_filter=args.fund)


if __name__ == "__main__":
    main()
