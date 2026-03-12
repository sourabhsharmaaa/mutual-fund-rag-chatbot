"""
generator.py
------------
Phase 3 — Gemini RAG generation layer.

Full pipeline for a single user query:
  1. Pre-filter (guardrails.PreFilter)       — block bad queries immediately
  2. Retrieve top-K chunks (retriever.py)    — ChromaDB semantic search
  3. Build prompt (system + context + query) — formatted for Gemini
  4. Call Gemini 1.5 Flash                   — generate raw answer
  5. Post-filter (guardrails.PostFilter)     — sanitise + enforce 3-sentence cap
  6. Inject mandatory citation               — "Last updated from sources: ..."

Returns a GenerationResult containing everything needed by the API layer
and test_sandbox.py.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class GenerationResult:
    """Everything returned from a single RAG call."""
    answer:             str                  # final cleaned response (shown to user)
    raw_llm_response:   str                  # Gemini output before post-filter
    retrieved_chunks:   list[dict]           # [{text, source_url, field_type, ...}]
    source_urls:        list[str]            # deduplicated citation URLs
    guardrail_triggered: bool = False        # True if pre-filter blocked the query
    guardrail_reason:   str  = ""            # e.g. "advice", "performance"
    sentence_count:     int  = 0             # sentences in body (excl. citation)
    elapsed_ms:         float = 0.0


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a factual knowledge assistant for Parag Parikh Mutual Fund (PPFAS).

RULES (non-negotiable):
1. Answer using ONLY the provided context. Never use external knowledge.
2. Limit your answer to a MAXIMUM of 5 sentences.
3. Keep your language professional and objective.
4. Do NOT give investment advice. Do NOT say "you should invest", "this is good for you", or any recommendation language.
5. If the question asks for an opinion, preference, or recommendation (queries that cannot be answered factually using the context), respond ONLY with the following disclaimer and nothing else:
   "I'm INDy, your Parag Parikh Mutual Fund assistant! I can only share factual fund data — not opinions or advice. For investment guidance, please consult a SEBI-registered advisor."
6. Do NOT collect or acknowledge personal details (PAN, folio number, etc.).
7. DOMAIN KNOWLEDGE: 
   - "PPFAS" refers to "Parag Parikh Financial Advisory Services".
   - "PPFAS Mutual Fund" and "Parag Parikh Mutual Fund" are the same entity.
   - Parag Parikh ELSS Tax Saver Fund inherently qualifies for tax deduction under Section 80C.
8. Anti-Hedging & Implicit Context:
   - Answer ONLY the specific question asked. 
   - Never volunteer information about what is missing from your knowledge base.
   - INTEGRATE category context (e.g., "Direct plan") naturally into your data points.
   - NEVER append defensive disclaimers like "This data applies to...", "I don't have verified data on...", or "The context does not mention..." unless the user specifically asks about missing categories.
9. BE EXTREMELY CONCISE: Extract and provide ONLY the specific data requested.
10. Do NOT define financial terms unless explicitly asked 'What is...'.
11. NO INTROS OR FILLERS: Do not use greetings or introductory phrases like "I'm INDy...", "The value is...", or "Based on the context...". Jump straight to the data. Starting with a disclaimer for a factual query is a failure.
12. If the context does not contain relevant information to answer the core question, respond with exactly: NO_DATA.
    However, if ANY relevant data is present (even for just one of many funds), you MUST use it to answer. Partial data is better than no data.
13. PRIORITIZE DATA: Provide direct numerical values or facts. Exclude "Investment Objective", "Fund Manager", etc., unless explicitly asked.
14. NO URLs IN BODY: Never write URLs or markdown links in the answer body. URLs are only allowed in the "Source: [URL]" block at the very end.
15. FUND SCOPE:
    - If an ACTIVE FUND is specified, answer ONLY for that fund.
    - If ACTIVE FUND is "ALL FUNDS (no specific fund filter)", provide data for any of the following 4 primary funds found in the context:
        1. Parag Parikh Flexi Cap Fund
        2. Parag Parikh ELSS Tax Saver Fund
        3. Parag Parikh Conservative Hybrid Fund
        4. Parag Parikh Liquid Fund
    - If only some of these are in the context, answer for those and ignore the rest.
16. NO ABBREVIATIONS: Always use full fund names (e.g., "Parag Parikh Flexi Cap Fund"), never PPFCF, PPTSF, etc.

ACTIVE FUND: {fund_scope}

CONTEXT:
{context}

USER QUESTION: {query}
"""

# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class RAGGenerator:
    """
    End-to-end RAG generator: pre-filter → retrieve → Gemini → post-filter.

    Usage:
        gen = RAGGenerator()
        result = gen.generate("What is the exit load for Flexi Cap Fund?")
        print(result.answer)
    """

    def __init__(self):
        from backend.services.guardrails import PreFilter, PostFilter  # type: ignore
        from backend.services.retriever import get_retriever  # type: ignore
        from backend.config import (  # type: ignore
            RETRIEVAL_TOP_K, RETRIEVAL_CONTEXT_K, GROQ_MODEL,
            LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_TOP_P,
        )

        self._pre  = PreFilter()
        self._post = PostFilter()
        self._retriever = get_retriever()

        self._top_k     = RETRIEVAL_TOP_K
        self._context_k = RETRIEVAL_CONTEXT_K
        self._model_name    = GROQ_MODEL
        self._temperature   = LLM_TEMPERATURE
        self._max_tokens    = LLM_MAX_TOKENS
        self._top_p         = LLM_TOP_P

        self._client = None
        
        # Pre-warm: initialize store and client upfront
        try:
            logger.info("Pre-warming RAG engine (Groq)...")
            self._retriever._get_store()
            self._client = self._init_groq_client()
            logger.info("RAG engine pre-warmed successfully.")
        except Exception as e:
            logger.warning("Pre-warming failed: %s. Will retry on first query.", e)

    # ... (generate method unchanged except for renaming _call_gemini to _call_llm) ...

    def generate(
        self,
        query: str,
        fund_filter: str | None = None,
    ) -> GenerationResult:
        # ... (Stage 1 & 2 unchanged) ...
        t0 = time.monotonic()
        guard = self._pre.check(query)
        if guard.blocked:
            elapsed = (time.monotonic() - t0) * 1000
            return GenerationResult(
                answer=guard.canned_response or "I can only provide factual data about PPFAS funds.",
                raw_llm_response="",
                retrieved_chunks=[],
                source_urls=[],
                guardrail_triggered=True,
                guardrail_reason=guard.reason,
                sentence_count=self._count_sentences(guard.canned_response or ""),
                elapsed_ms=elapsed,
            )
        # Intercept NAV queries
        query_lower = query.lower()
        if "nav" in query_lower or "net asset value" in query_lower:
            from backend.services.nav_fetcher import fetch_live_nav  # type: ignore
            import asyncio
            
            # Mapping for INDmoney links (Verification links) - UPDATED WITH VERIFIED DIRECT GROWTH LINKS
            IND_MONEY_LINKS = {
                "PPFCF": "https://www.indmoney.com/mutual-funds/parag-parikh-flexi-cap-direct-growth-3229",
                "PPTSF": "https://www.indmoney.com/mutual-funds/parag-parikh-elss-tax-saver-fund-direct-growth-1004710",
                "PPCHF": "https://www.indmoney.com/mutual-funds/parag-parikh-conservative-hybrid-fund-direct-growth-1006619",
                "PPLF":  "https://www.indmoney.com/mutual-funds/parag-parikh-liquid-fund-direct-growth-1214"
            }

            # Use provided filter, or guess from the query
            target_fund = fund_filter
            if not target_fund:
                if "ppfcf" in query_lower or "flexi" in query_lower: target_fund = "PPFCF"
                elif "pptsf" in query_lower or "tax" in query_lower: target_fund = "PPTSF"
                elif "ppchf" in query_lower or "conservative" in query_lower or "hybrid" in query_lower: target_fund = "PPCHF"
                elif "pplf" in query_lower or "liquid" in query_lower: target_fund = "PPLF"
                
            if target_fund:
                try:
                    # RAG operates synchronously in this setup, so we run the async fetcher
                    nav_text = asyncio.run(fetch_live_nav(target_fund))
                    if nav_text:
                        elapsed = (time.monotonic() - t0) * 1000
                        sources = []
                        if target_fund in IND_MONEY_LINKS:
                            sources.append(IND_MONEY_LINKS[target_fund])

                        return GenerationResult(
                            answer=nav_text,
                            raw_llm_response="",
                            retrieved_chunks=[],
                            source_urls=sources,
                            sentence_count=1,
                            elapsed_ms=elapsed,
                        )
                except Exception as e:
                    logger.error(f"Error fetching live NAV: {e}")
                    # If it fails, fall through to normal RAG
            else:
                try:
                    # If they asked "What is the NAV" without specifying a fund,
                    # fetch NAV for ALL funds so they get a comprehensive answer.
                    async def fetch_all():
                        nav_futures = [
                            fetch_live_nav("PPFCF"),
                            fetch_live_nav("PPTSF"),
                            fetch_live_nav("PPCHF"),
                            fetch_live_nav("PPLF")
                        ]
                        return await asyncio.gather(*nav_futures)
                    
                    nav_results = asyncio.run(fetch_all())
                    nav_text = "\n".join(r for r in nav_results if r)  # type: ignore
                    
                    if nav_text:
                        elapsed = (time.monotonic() - t0) * 1000
                        sources = list(IND_MONEY_LINKS.values())

                        return GenerationResult(
                            answer=f"Here is the latest live NAV across all PPFAS funds:\n\n{nav_text}",
                            raw_llm_response="",
                            retrieved_chunks=[],
                            source_urls=sources,
                            sentence_count=4,
                            elapsed_ms=elapsed,
                        )
                except Exception as e:
                    logger.error(f"Error fetching all live NAVs: {e}")
                    logger.error(f"Error fetching all live NAVs: {e}")

        # Augment query with fund name for better embedding recall
        # Phase 1 — Retrieval with smarter query augmentation
        import re as pyre
        selected_funds = pyre.split(r'[,·|]', fund_filter) if fund_filter else []
        selected_funds = [f.strip() for f in selected_funds if f.strip()]

        # Only augment the search query with a fund-name prefix if EXACTLY ONE fund is selected.
        # Prefixing with multiple funds (e.g. 'PPCHF · PPTSF: ...') muddies the semantic search results.
        if len(selected_funds) == 1:
            fund_names = {
                "PPFCF": "Parag Parikh Flexi Cap Fund",
                "PPTSF": "PPFAS ELSS Tax Saver Fund",
                "PPCHF": "Parag Parikh Conservative Hybrid Fund",
                "PPLF":  "Parag Parikh Liquid Fund",
            }
            fund_long = fund_names.get(selected_funds[0], selected_funds[0])
            augmented_query = f"{fund_long}: {query}"
        else:
            augmented_query = query

        t_retrieve_start = time.monotonic()
        results = self._retriever.retrieve(augmented_query, top_k=self._top_k, fund_filter=fund_filter)
        t_retrieve = (time.monotonic() - t_retrieve_start) * 1000
        source_urls = self._retriever.collect_source_urls(results[: self._context_k])

        if not results:
            elapsed = (time.monotonic() - t0) * 1000
            return GenerationResult(
                answer="I'm INDy, your Parag Parikh Mutual Fund assistant! I can only help with questions about PPFAS funds — things like NAV, expense ratios, exit loads, fund managers, or how to download your CAS. Try asking me something fund-related!",
                raw_llm_response="",
                retrieved_chunks=[],
                source_urls=[],
                elapsed_ms=elapsed,
            )

        context_chunks = results[: self._context_k]
        context_str = "\n\n".join(f"[{i+1}] {r.format_for_prompt()}" for i, r in enumerate(context_chunks))
        # Force the LLM to respect the fund filter by making it prominent
        if fund_filter:
            import re as pyre
            selected_funds = pyre.split(r'[,·|]', fund_filter)
            display_filter = ", ".join([f.strip() for f in selected_funds if f.strip()])
            fund_scope_str = f"STRICT FILTER: ONLY include data for {display_filter}. ABSOLUTELY DO NOT mention any other funds if they are not in this list."
        else:
            fund_scope_str = "ALL FUNDS (no specific fund filter)"
            
        prompt = SYSTEM_PROMPT.format(context=context_str, query=query, fund_scope=fund_scope_str)

        # Step 4 — Call LLM (Groq)
        t_llm_start = time.monotonic()
        try:
            raw_response = self._call_llm(prompt)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            elapsed = (time.monotonic() - t0) * 1000
            return GenerationResult(
                answer="I encountered a technical issue while processing your request. Please try again in a moment.",
                raw_llm_response=str(exc),
                retrieved_chunks=[r.__dict__ for r in context_chunks],
                source_urls=source_urls,
                elapsed_ms=elapsed,
            )
        t_llm = (time.monotonic() - t_llm_start) * 1000
        logger.info("Time taken for LLM call: %.2fms", t_llm)

        cleaned = self._post.clean(raw_response, source_urls, query)
        sentence_count = self._count_sentences(cleaned)
        elapsed = (time.monotonic() - t0) * 1000

        # Convert NO_DATA sentinel to user-friendly message and clear sources
        FRIENDLY_NO_DATA = (
            "I'm INDy, your Parag Parikh Mutual Fund assistant! "
            "I couldn't find relevant data for this. "
            "Try asking about NAV, expense ratios, exit loads, fund managers, or how to download your CAS."
        )
        if cleaned.strip().upper().startswith("NO_DATA") or "NO_DATA" in cleaned:
            return GenerationResult(
                answer=FRIENDLY_NO_DATA,
                raw_llm_response=raw_response,
                retrieved_chunks=[r.__dict__ for r in context_chunks],
                source_urls=[],
                guardrail_triggered=False,
                sentence_count=self._count_sentences(FRIENDLY_NO_DATA),
                elapsed_ms=elapsed,
            )

        # Only clear sources if this is a hard "No Data" refusal
        is_hard_refusal = any(p in cleaned.lower() for p in ["couldn't find relevant data", "no information available"])
        contains_data = bool(re.search(r'[\d\%₹]|rs\.', cleaned, re.IGNORECASE))
        
        if is_hard_refusal and not contains_data:
            final_source_urls = []
        else:
            # Relaxed filters: Allow schemes and faqs as they are primary fund fact sources
            filtered = source_urls 
            
            # Fund-relevance filter (now with auto-detection from answer text)
            import re as pyre
            FRAGMENTS = {
                "PPFCF": "flexi-cap",
                "PPTSF": "tax-saver",
                "PPCHF": "conservative-hybrid",
                "PPLF":  "liquid-fund"
            }
            
            # Use filters if UI selected them, otherwise look for clues in the answer body
            active_fragments = []
            if fund_filter:
                selected_codes = [t.strip().upper() for t in pyre.split(r'[,·|]', fund_filter) if t.strip()]
                active_fragments = [FRAGMENTS.get(c, c.lower()) for c in selected_codes]
            else:
                # Auto-detect mentioned funds from the actual response body
                for code, frag in FRAGMENTS.items():
                    # Check for code or descriptive slug in the cleaned response
                    slug_readable = frag.replace("-", " ")
                    if f"{code.lower()}" in cleaned.lower() or slug_readable in cleaned.lower():
                        active_fragments.append(frag)

            if active_fragments:
                def is_relevant(url):
                    low_url = url.lower()
                    # Always include non-INDmoney links (AMC links, AMFI links) as context fallback
                    if "indmoney.com" not in low_url: return True
                    # Only include INDmoney links if they match the active/detected funds
                    return any(frag in low_url for frag in active_fragments)

                final_source_urls = [url for url in filtered if is_relevant(url)]
                
                # If we filtered everything out but have potential sources, keep the first one as safety
                if not final_source_urls and filtered:
                    final_source_urls = [filtered[0]]
            else:
                final_source_urls = filtered

        return GenerationResult(
            answer=cleaned,
            raw_llm_response=raw_response,
            retrieved_chunks=[r.__dict__ for r in context_chunks],
            source_urls=final_source_urls,
            guardrail_triggered=False,
            sentence_count=sentence_count,
            elapsed_ms=elapsed,
        )

    def _call_llm(self, prompt: str) -> str:
        if self._client is None:
            self._client = self._init_groq_client()

        chat_completion = self._client.chat.completions.create(  # type: ignore
            messages=[{"role": "user", "content": prompt}],
            model=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            top_p=self._top_p,
        )
        return chat_completion.choices[0].message.content or ""

    def _init_groq_client(self):
        from groq import Groq  # type: ignore
        from backend.config import require_api_key  # type: ignore
        return Groq(api_key=require_api_key())

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _count_sentences(text: str) -> int:
        from backend.services.guardrails import count_sentences  # type: ignore
        return count_sentences(text)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_generator_instance: RAGGenerator | None = None


def get_generator() -> RAGGenerator:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = RAGGenerator()
    return _generator_instance
