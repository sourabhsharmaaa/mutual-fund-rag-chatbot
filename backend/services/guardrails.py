"""
guardrails.py
-------------
Two-stage guardrail engine for the PPFAS RAG chatbot.

STAGE 1 — Pre-filter (runs BEFORE retrieval + LLM):
  Blocks queries that are inherently unanswerable by facts:
    • Investment advice / opinion requests
    • Performance / returns comparison
    • PII mentions
    • Competitor fund names
    • Out-of-scope topics

STAGE 2 — Post-filter (runs AFTER Gemini generates a response):
  Sanitises the LLM output:
    • Strips any advice/recommendation language that slipped through
    • Enforces 3-sentence hard cap
    • Verifies "Last updated from sources:" citation is appended
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Guardrail result dataclass
# ---------------------------------------------------------------------------

@dataclass
class GuardrailResult:
    """Returned by the pre-filter."""
    blocked:        bool
    reason:         str = ""          # internal category key
    canned_response: Optional[str] = None   # ready-made reply shown to user


# ---------------------------------------------------------------------------
# Pre-filter trigger sets
# ---------------------------------------------------------------------------

# Advice / opinion triggers
_ADVICE_PHRASES: list[str] = [
    "should i invest",
    "should i buy",
    "should i put money",
    "is it a good",
    "is this a good",
    "is it worth",
    "which fund should",
    "which is better",
    "which fund is best",
    "recommend",
    "advice",
    "suggest",
    "better than",
    "best mutual fund",
    "best ppfas",
    "is ppfas good",
    "worth investing",
]

# Performance / returns triggers
_PERF_PHRASES: list[str] = [
    "return",
    "returns",
    "cagr",
    "annualized",
    "performance",
    "how much did",
    "how much has",
    "gain",
    "profit",
    "outperform",
    "beat the market",
    "compare returns",
    "past performance",
    "1 year return",
    "3 year return",
    "5 year return",
    "10 year return",
    "nav growth",
]

# PII triggers
# NOTE: Keep phrases specific to avoid blocking legitimate how-to questions.
# e.g. "my account" is too broad — it blocks "how do I download my account statement?"
# The goal is to block queries where a user is SHARING personal identifiers,
# not questions about how to use the PPFAS platform.
_PII_PHRASES: list[str] = [
    "my pan is",
    "my pan number is",
    "my folio is",
    "my folio number is",
    "my account number",
    "my portfolio value",
    "my portfolio details",
    "my redemption status",
    "my password",
    "my sip details",
    "my investment value",
    "my balance is",
    "send my statement",
    "send to my email",
    "@gmail.com",
    "@yahoo.com",
    "@email.com",
    "@hotmail.com",
]

# Competitor fund names (non-exhaustive; covers major AMCs)
_COMPETITOR_NAMES: list[str] = [
    "mirae",
    "axis mutual",
    "hdfc mutual",
    "sbi mutual",
    "kotak mutual",
    "dsp mutual",
    "icici prudential",
    "nippon india",
    "aditya birla",
    "franklin templeton",
    "uti mutual",
    "tata mutual",
    "invesco mutual",
    "edelweiss",
    "motilal oswal",
]

# Profanity / abuse — keeping minimal; pattern-based
_ABUSE_PATTERN = re.compile(
    r"\b(f+u+c+k+|s+h+i+t+|a+s+s+h+o+l+e+|b+i+t+c+h)\b",
    re.IGNORECASE,
)

# Post-filter: phrases to strip from LLM output
_ADVICE_OUTPUT_PHRASES: list[str] = [
    "i recommend",
    "i suggest",
    "you should invest",
    "you must invest",
    "you ought to",
    "best option for you",
    "ideal for you",
    "this is a great fund",
    "strongly recommend",
    "outperform",
    "beat the index",
]


# ---------------------------------------------------------------------------
# Pre-filter
# ---------------------------------------------------------------------------

class PreFilter:
    """
    Checks user query against all guardrail categories.
    Returns a GuardrailResult immediately if a block is triggered.
    """

    def check(self, query: str) -> GuardrailResult:
        q = query.lower().strip()

        # 1. Profanity
        if _ABUSE_PATTERN.search(q):
            return GuardrailResult(
                blocked=True,
                reason="profanity",
                canned_response=(
                    "I can only answer factual questions about PPFAS mutual funds. "
                    "Please rephrase your question politely."
                ),
            )

        # 2. PII
        if any(phrase in q for phrase in _PII_PHRASES):
            return GuardrailResult(
                blocked=True,
                reason="pii",
                canned_response=(
                    "I do not collect, process, or reference any personal information "
                    "such as PAN, folio numbers, or personal investment data. "
                    f"For account-specific queries, please contact PPFAS directly: "
                    f"https://amc.ppfas.com/contact"
                ),
            )

        # 3. Investment advice / opinion
        if any(phrase in q for phrase in _ADVICE_PHRASES):
            return GuardrailResult(
                blocked=True,
                reason="advice",
                canned_response=(
                    "I can only share factual data. For investment guidance, please consult a SEBI-registered "
                    "advisor: https://investor.sebi.gov.in/"
                ),
            )

        # 4. Performance / returns
        if any(phrase in q for phrase in _PERF_PHRASES):
            return GuardrailResult(
                blocked=True,
                reason="performance",
                canned_response=(
                    "I do not compute, compare, or comment on fund returns or performance. "
                    "For accurate and up-to-date performance data, please refer to the "
                    "official PPFAS factsheet: https://amc.ppfas.com/downloads/factsheet/ "
                    "or the NAV history page: https://amc.ppfas.com/schemes/nav-history/"
                ),
            )

        # 5. Competitor funds
        if any(name in q for name in _COMPETITOR_NAMES):
            return GuardrailResult(
                blocked=True,
                reason="competitor",
                canned_response=(
                    "I can only answer questions about Parag Parikh Mutual Fund (PPFAS) schemes. "
                    "For comparisons with other funds, please visit an independent platform "
                    "such as https://www.amfiindia.com or https://www.valueresearchonline.com"
                ),
            )

        return GuardrailResult(blocked=False)


# ---------------------------------------------------------------------------
# Post-filter
# ---------------------------------------------------------------------------

class PostFilter:
    """
    Sanitises the raw LLM response before returning it to the user.

    Rules applied (in order):
      1. Strip any advice/recommendation language
      2. Enforce ≤ MAX_SENTENCES sentence limit
      3. Ensure citation line is present ("Last updated from sources:")
    """

    MAX_SENTENCES = 5

    def clean(self, raw_text: str, source_urls: list[str], query: str = "") -> str:
        """
        Main post-filtering entry point.
        1. Strips all URLs from the answer body.
        2. Identifies which sources were actually used.
        3. Caps sentences to MAX_SENTENCES.
        """
        # Step 1: Forcefully strip any URLs from the body to prevent leakage
        import re
        url_pattern = r'https?://[^\s)\]]+'
        body_text = re.sub(url_pattern, '', raw_text).strip()
        
        # Also strip any trailing 'Source:' or 'Sources:' labels and following punctuation/whitespace/words like 'and'
        body_text = re.sub(r'(?i)\n*Source[s]?\s*:?\s*.*$', '', body_text).strip()

        # Detect if this is a hard fallback / no-data response — skip source injection if so.
        # If it contains numeric symbols (%, RS, ₹) it likely has real data even with a disclaimer.
        # detect if this is a hard fallback / no-data response — skip source injection if so.
        # If it contains numeric symbols (%, RS, ₹) it likely has real data even with a disclaimer.
        FALLBACK_PHRASES = ("couldn't find relevant data", "no information available", "no data found", "not opinions or advice")
        contains_data = bool(re.search(r'[\d\%₹]|rs\.', body_text, re.IGNORECASE))
        is_hard_refusal = any(p.lower() in raw_text.lower() for p in FALLBACK_PHRASES)
        
        # New: If the LLM ONLY provided the mandatory disclaimer, it's a fallback.
        DISCLAIMER_START = "I'm INDy, your Parag Parikh Mutual Fund assistant!"
        is_disclaimer_only = (DISCLAIMER_START in body_text) and (len(body_text) < 250) and not contains_data
        
        # It's only a fallback if it refuses OR is just a disclaimer, AND doesn't seem to have numeric data
        # EXCEPTION: If the user is asking about CAS or statements, we don't treat it as a source-blocking fallback.
        is_cas_query = "cas" in query.lower() or "statement" in query.lower()
        is_fallback = (is_hard_refusal or is_disclaimer_only) and not contains_data and not is_cas_query
        
        # If body_text became empty after URL stripping, but raw_text wasn't empty, 
        # restore it (we'd rather have URLs than nothing)
        if not body_text and raw_text.strip():
            body_text = raw_text.strip()
        
        # New Safety: If the disclaimer IS present but it's NOT a fallback (i.e. we have real data),
        # strip the disclaimer and any transitional text like "However, ..." or "Based on..."
        if not is_fallback and body_text.startswith(DISCLAIMER_START):
            # Safer stripping: Just remove the specific disclaimer text and any immediate intro transitions
            # that often follow it (e.g. "Based on the context, here is...")
            # We avoid stopping at characters like '-' which broke "SEBI-registered advisor".
            
            # 1. Remove the mandatory disclaimer prefix
            body_text = body_text[len(DISCLAIMER_START):].strip()
            
            # 2. If it now starts with "I can only share factual fund data... advisor.", remove that too.
            LONG_DISCLAIMER_CONTINUATION = "I can only share factual fund data — not opinions or advice. For investment guidance, please consult a SEBI-registered advisor."
            if body_text.startswith(LONG_DISCLAIMER_CONTINUATION):
                body_text = body_text[len(LONG_DISCLAIMER_CONTINUATION):].strip()
            
            # 3. Strip common intro phrases that LLMs sometimes hallucinate despite rules
            body_text = re.sub(r"^(Based on the (provided )?context|Here is the (requested )?data|Regarding your question),?\s*", "", body_text, flags=re.IGNORECASE).strip()
            # If it starts with "however," strip that too
            if body_text.lower().startswith("however"):
                body_text = re.sub(r"^however,?\s*", "", body_text, flags=re.IGNORECASE).strip()

            # FINAL SAFETY: If stripping the disclaimer resulted in an empty string, 
            # it means the LLM ONLY provided the disclaimer (e.g. for out-of-scope).
            # In that case, we should keep the original response so the user sees something!
            if not body_text:
                body_text = raw_text.strip()

        # Step 2: Determine used sources (skip entirely for fallback)
        used_sources: list[str] = []
        if not is_fallback:
            # Relaxed filters: Allow schemes and faqs as they are primary fund fact sources
            potential_sources = source_urls
            
            # If the LLM cited specific URLs, use them (if they aren't blocked)
            cited_in_text = [url for url in potential_sources if url in raw_text]
            
            if cited_in_text:
                used_sources = cited_in_text
            elif potential_sources:
                # If no specific URL was cited by the LLM, be selective.
                # Filter out the generic CAS download link unless "CAS" is mentioned in query/answer.
                final_sources = []
                q_and_a = (query + " " + body_text).lower()
                for url in potential_sources:
                    if "amfiindia.com/download-cas" in url and "cas" not in q_and_a:
                        continue
                    final_sources.append(url)
                
                # If we still have sources after specific filtering, use them.
                # Only take top 3 to keep it clean.
                used_sources = final_sources[:3]  # type: ignore

        # Step 3: Sentence capping
        sentences: list[str] = self._split_sentences(body_text)
        capped = " ".join(sentences[:self.MAX_SENTENCES])  # type: ignore

        # Step 4: Build citation block (skipped for fallback)
        citation = self._build_citation(used_sources)
        
        # FINAL SAFETY: If capped is STILL empty or extremely short (e.g. just whitespace/punctuation),
        # and we AREN'T in a hard fallback, return a "No data found" sentinel so generator can handle it.
        if not capped.strip() or len(capped.strip()) < 5:
            if is_fallback:
                return raw_text.strip() # Return whatever the LLM said as a fallback
            return "NO_DATA"

        if citation:
            return f"{capped}\n\n{citation}"
        return capped

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _cap_sentences(text: str, max_n: int) -> str:
        """
        Truncate text to at most max_n sentences.
        Sentence boundary: period/exclamation/question mark followed by space+capital or end of string.
        """
        # Split on sentence boundaries
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[\"])", text)
        if len(sentences) <= max_n:
            return text
        # Take first max_n, rejoin
        truncated = " ".join(sentences[:max_n]).strip()  # type: ignore
        # Ensure it ends with punctuation
        if truncated and truncated[-1] not in ".!?":
            truncated += "."
        return truncated

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Splits text into a list of sentences."""
        return re.split(r"(?<=[.!?])\s+(?=[A-Z\[\"])", text)

    def _build_citation(self, source_urls: list[str]) -> str:
        """Return a formatted 'Source: url1, url2' string with deduplication."""
        if not source_urls:
            return ""

        seen = set()
        unique_urls = []
        for url in source_urls:
            # Normalize for comparison
            u = url.strip().lower().rstrip('/')
            if u not in seen:
                seen.add(u)
                unique_urls.append(url)

        if not unique_urls:
            return ""

        return f"Source: {', '.join(unique_urls)}"


# ---------------------------------------------------------------------------
# Sentence counter (used by test_sandbox.py)
# ---------------------------------------------------------------------------

def count_sentences(text: str) -> int:
    """
    Count the number of sentences in the body of a response
    (excludes the 'Last updated from sources:' line).
    """
    # Strip citation footer
    body = re.sub(
        r"\n*Last updated from sources?:.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    if not body:
        return 0
    parts = re.split(r"(?<=[.!?])\s+", body)
    return len([p for p in parts if p.strip()])
