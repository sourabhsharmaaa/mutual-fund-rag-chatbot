"""
chunker.py
----------
Converts mutual_funds.json (Phase 1 output) into a flat list of
text chunks, each paired with rich metadata.

Chunking strategy (per architecture):
  - FIELD-LEVEL chunks: one sentence per structured field (expense ratio,
    exit load, AUM, etc.) → guarantees factual atomicity, no semantic bleed.
  - PARAGRAPH chunks: free-text content (FAQs, taxation, general knowledge)
    split at ≤300 tokens with 50-token overlap.

Every chunk carries:
  {
    "text":        str,           # the text to embed
    "source_url":  str,           # primary source URL for citation
    "fund_name":   str,           # e.g. "Parag Parikh Flexi Cap Fund" or "GENERAL"
    "short_name":  str,           # e.g. "PPFCF"
    "field_type":  str,           # e.g. "expense_ratio", "faq", "taxation"
    "chunk_id":    str,           # deterministic ID for upsert-safety
  }
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PARAGRAPH_TOKENS = 300          # ~300 words ≈ 400 tokens; keeps chunks tight
OVERLAP_TOKENS = 50                 # ~50-word overlap between paragraph chunks

# Field definitions: (json_key, human_label, sentence_template)
SCHEME_FIELD_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "expense_ratio",
        "expense_ratio",
        "The expense ratio (Total Expense Ratio / TER) of {scheme_name} (Direct Plan) is {value}.",
    ),
    (
        "exit_load",
        "exit_load",
        "The exit load of {scheme_name} is: {value}.",
    ),
    (
        "min_sip_amount",
        "min_sip",
        "The minimum SIP amount for {scheme_name} is {value}.",
    ),
    (
        "min_lumpsum_amount",
        "min_lumpsum",
        "The minimum lumpsum (one-time) investment amount for {scheme_name} is {value}.",
    ),
    (
        "lock_in_period",
        "lock_in",
        "The lock-in period for {scheme_name} is {value}.",
    ),
    (
        "riskometer",
        "riskometer",
        "The SEBI riskometer rating of {scheme_name} is '{value}'.",
    ),
    (
        "benchmark",
        "benchmark",
        "The benchmark index for {scheme_name} is {value}.",
    ),
    (
        "fund_manager",
        "fund_manager",
        "The fund manager(s) of {scheme_name} are: {value}.",
    ),
    (
        "fund_size_aum",
        "aum",
        "The Assets Under Management (AUM / fund size) of {scheme_name} is {value}.",
    ),
    (
        "category",
        "category",
        "{scheme_name} belongs to the '{value}' category of mutual funds.",
    ),
    (
        "date_of_allotment",
        "date_of_allotment",
        "{scheme_name} was allotted (launched) on {value}.",
    ),
    (
        "investment_objective",
        "investment_objective",
        "The investment objective of {scheme_name} is: {value}.",
    ),
    (
        "nav",
        "nav",
        "The current NAV (Net Asset Value) of {scheme_name} (Direct Plan) is ₹{value}.",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk_id(text: str, source_url: str, field_type: str) -> str:
    """Deterministic SHA-256 chunk ID — safe for ChromaDB upserts."""
    raw = f"{field_type}|{source_url}|{text[:120]}" # type: ignore
    return hashlib.sha256(raw.encode()).hexdigest()[:32] # type: ignore


def _format_manager(value: Any) -> str:
    """Normalise fund_manager which may be a list or a string."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if str(v) != "NA")
    return str(value)


def _paragraph_split(text: str, max_words: int = MAX_PARAGRAPH_TOKENS,
                     overlap: int = OVERLAP_TOKENS) -> list[str]:
    """
    Split free-text into overlapping word-window chunks.
    Tries to break at sentence boundaries first.
    """
    if not text or text.strip() == "NA":
        return []

    # Split into sentences first
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current_words: list[str] = []

    for sentence in sentences:
        words = sentence.split()
        if len(current_words) + len(words) > max_words and current_words:
            chunks.append(" ".join(current_words))
            # Keep overlap
            current_words = current_words[-overlap:] + words # type: ignore
        else:
            current_words.extend(words) # type: ignore

    if current_words:
        chunks.append(" ".join(current_words))

    return [c for c in chunks if len(c.strip()) > 20]


# ---------------------------------------------------------------------------
# Main Chunker
# ---------------------------------------------------------------------------

class MutualFundChunker:
    """
    Converts mutual_funds.json into a flat list of chunk dicts.
    Call `chunker.chunk_all(data)` with the parsed JSON.
    """

    def chunk_all(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Entry point — returns all chunks from the full JSON."""
        chunks: list[dict] = []

        # 1. Scheme field-level chunks (one sentence per field per scheme)
        for scheme in data.get("schemes", []):
            chunks.extend(self._chunk_scheme(scheme))

        # 2. FAQ chunks
        for faq in data.get("faqs", []):
            chunks.extend(self._chunk_faq(faq))

        # 3. Taxation chunks
        taxation = data.get("taxation", {})
        if taxation:
            chunks.extend(self._chunk_taxation(taxation))

        # 4. General knowledge chunks (riskometer, expense ratio def, CAS)
        gk = data.get("general_knowledge", {})
        if gk:
            chunks.extend(self._chunk_general_knowledge(gk))

        return chunks

    # -----------------------------------------------------------------------
    # Scheme field-level chunks
    # -----------------------------------------------------------------------

    def _chunk_scheme(self, scheme: dict) -> list[dict]:
        chunks = []
        scheme_name = scheme.get("scheme_name", "Unknown Fund")
        short_name = scheme.get("short_name", "UNKNOWN")
        source_urls = scheme.get("source_urls", [])
        primary_url = source_urls[0] if source_urls else "https://amc.ppfas.com"
        all_urls_str = " | ".join(source_urls) if source_urls else primary_url

        for json_key, field_type, template in SCHEME_FIELD_TEMPLATES:
            raw_value = scheme.get(json_key)
            if not raw_value or str(raw_value) in ("NA", "", "None"):
                continue

            value_str = _format_manager(raw_value)

            sentence = template.format(scheme_name=scheme_name, value=value_str)

            # Append source annotation in the chunk text itself so LLM sees it
            text = f"{sentence}\n[Source: {primary_url}]"

            chunks.append({
                "text": text,
                "source_url": primary_url,
                "all_source_urls": all_urls_str,
                "fund_name": scheme_name,
                "short_name": short_name,
                "field_type": field_type,
                "chunk_id": _make_chunk_id(text, primary_url, field_type),
            })

        return chunks

    # -----------------------------------------------------------------------
    # FAQ chunks
    # -----------------------------------------------------------------------

    def _chunk_faq(self, faq: dict) -> list[dict]:
        question = faq.get("question", "").strip()
        answer = faq.get("answer", "NA").strip()
        source_url = faq.get("source_url", "https://amc.ppfas.com")

        if not question or answer == "NA" or not answer:
            return []

        # Build full Q+A text
        text = f"Q: {question}\nA: {answer}\n[Source: {source_url}]"

        # If very long answer, split into paragraph chunks
        chunks = []
        if len(answer.split()) > MAX_PARAGRAPH_TOKENS:
            parts = _paragraph_split(answer)
            for i, part in enumerate(parts):
                chunk_text = f"Q: {question}\nA (part {i+1}): {part}\n[Source: {source_url}]"
                chunks.append({
                    "text": chunk_text,
                    "source_url": source_url,
                    "all_source_urls": source_url,
                    "fund_name": "GENERAL",
                    "short_name": "ALL",
                    "field_type": "faq",
                    "chunk_id": _make_chunk_id(chunk_text, source_url, f"faq_p{i}"),
                })
        else:
            chunks.append({
                "text": text,
                "source_url": source_url,
                "all_source_urls": source_url,
                "fund_name": "GENERAL",
                "short_name": "ALL",
                "field_type": "faq",
                "chunk_id": _make_chunk_id(text, source_url, "faq"),
            })

        return chunks

    # -----------------------------------------------------------------------
    # Taxation chunks
    # -----------------------------------------------------------------------

    def _chunk_taxation(self, taxation: dict) -> list[dict]:
        chunks = []
        source_url = taxation.get("source_url", "https://www.indmoney.com/articles/mutual-funds/mutual-fund-taxation")

        tax_fields = [
            ("ltcg_details", "taxation_ltcg"),
            ("stcg_details", "taxation_stcg"),
            ("elss_tax_benefit", "taxation_elss"),
        ]

        for key, field_type in tax_fields:
            val = taxation.get(key, "").strip()
            if not val or val == "NA":
                # Fall back to just the rate if details not available
                rate_key = key.replace("_details", "_rate").replace("_benefit", "")
                rate = taxation.get(rate_key, "")
                if rate and rate != "NA":
                    val = f"Tax rate: {rate}"
                else:
                    continue

            text = f"{val}\n[Source: {source_url}]"
            chunks.append({
                "text": text,
                "source_url": source_url,
                "all_source_urls": source_url,
                "fund_name": "GENERAL",
                "short_name": "ALL",
                "field_type": field_type,
                "chunk_id": _make_chunk_id(text, source_url, field_type),
            })

        # Also chunk the article summary if available
        summary = taxation.get("summary", "")
        if summary and summary != "NA" and len(summary) > 50:
            for i, part in enumerate(_paragraph_split(summary)):
                text = f"{part}\n[Source: {source_url}]"
                chunks.append({
                    "text": text,
                    "source_url": source_url,
                    "all_source_urls": source_url,
                    "fund_name": "GENERAL",
                    "short_name": "ALL",
                    "field_type": "taxation_summary",
                    "chunk_id": _make_chunk_id(text, source_url, f"tax_summary_{i}"),
                })

        return chunks

    # -----------------------------------------------------------------------
    # General knowledge chunks
    # -----------------------------------------------------------------------

    def _chunk_general_knowledge(self, gk: dict) -> list[dict]:
        chunks = []
        source_urls = gk.get("source_urls", ["https://amc.ppfas.com"])
        primary_url = source_urls[0] if source_urls else "https://amc.ppfas.com"

        gk_fields = [
            ("riskometer_definition", "riskometer_definition"),
            ("expense_ratio_definition", "expense_ratio_definition"),
            ("cas_download_procedure", "cas_procedure"),
        ]

        for key, field_type in gk_fields:
            val = gk.get(key, "")
            if not val or val == "NA":
                continue
            for i, part in enumerate(_paragraph_split(str(val), max_words=200)):
                text = f"{part}\n[Source: {primary_url}]"
                chunks.append({
                    "text": text,
                    "source_url": primary_url,
                    "all_source_urls": " | ".join(source_urls),
                    "fund_name": "GENERAL",
                    "short_name": "ALL",
                    "field_type": field_type,
                    "chunk_id": _make_chunk_id(text, primary_url, f"{field_type}_{i}"),
                })

        # Risk levels list
        for i, level_text in enumerate(gk.get("risk_levels", [])):
            if not level_text or level_text == "NA":
                continue
            text = f"Riskometer level: {level_text}\n[Source: {primary_url}]"
            chunks.append({
                "text": text,
                "source_url": primary_url,
                "all_source_urls": " | ".join(source_urls),
                "fund_name": "GENERAL",
                "short_name": "ALL",
                "field_type": "riskometer_level",
                "chunk_id": _make_chunk_id(text, primary_url, f"risk_level_{i}"),
            })

        return chunks
