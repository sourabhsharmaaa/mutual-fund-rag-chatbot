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
import os
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

{fund_scope}

RULES (non-negotiable):
1. Answer using ONLY the provided context. Never use external knowledge.
2. Limit your answer to a MAXIMUM of 5 sentences.
3. Keep your language professional and objective.
4. If the query is plural ("funds", "all funds"), provide data for all 4 schemes (Flexi Cap, Tax Saver, Conservative Hybrid, Liquid) if available in the context.
5. Do NOT give investment advice. Do NOT say "you should invest", "this is good for you", or any recommendation language.
6. If the question asks for an opinion, preference, or recommendation (queries that cannot be answered factually using the context), respond ONLY with the following disclaimer and nothing else:
   "I'm INDy, your Parag Parikh Mutual Fund assistant! I can only share factual fund data — not opinions or advice. For investment guidance, please consult a SEBI-registered advisor."
7. Do NOT collect or acknowledge personal details (PAN, folio number, etc.).
8. DOMAIN KNOWLEDGE: 
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
        
        # Render-specific context boost: fetch more to avoid DummyEmbedding search failure.
        # Now used in tandem with keyword re-ranking in retriever.py.
        if os.environ.get("RENDER"):
            logger.info("Adjusted retrieval context for Render (top_k=15, context_k=20)")
            self._top_k = 15
            self._context_k = 20 # Increased from 15

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

    async def generate(
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
            target_funds_list = []
            if fund_filter:
                import re as pyre
                target_funds_list = [f.strip().upper() for f in pyre.split(r'[,·|]', fund_filter) if f.strip().upper() in IND_MONEY_LINKS]
            
            if not target_funds_list:
                if "ppfcf" in query_lower or "flexi" in query_lower: target_funds_list = ["PPFCF"]
                elif "pptsf" in query_lower or "tax" in query_lower: target_funds_list = ["PPTSF"]
                elif "ppchf" in query_lower or "conservative" in query_lower or "hybrid" in query_lower: target_funds_list = ["PPCHF"]
                elif "pplf" in query_lower or "liquid" in query_lower: target_funds_list = ["PPLF"]
                
            if target_funds_list:
                try:
                    # Async await for all target funds
                    nav_futures = [fetch_live_nav(f) for f in target_funds_list]
                    nav_results = await asyncio.gather(*nav_futures)
                    nav_text = "\n".join(r for r in nav_results if r)
                    
                    if nav_text:
                        elapsed = (time.monotonic() - t0) * 1000
                        sources = [IND_MONEY_LINKS[f] for f in target_funds_list if f in IND_MONEY_LINKS]

                        prefix = "Here is the latest live NAV for the selected funds:\n\n" if len(target_funds_list) > 1 else ""
                        return GenerationResult(
                            answer=f"{prefix}{nav_text}",
                            raw_llm_response="",
                            retrieved_chunks=[],
                            source_urls=sources,
                            sentence_count=len(target_funds_list),
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
                        nav_futures_all = [
                            fetch_live_nav("PPFCF"),
                            fetch_live_nav("PPTSF"),
                            fetch_live_nav("PPCHF"),
                            fetch_live_nav("PPLF")
                        ]
                        return await asyncio.gather(*nav_futures_all)
                    
                    nav_results = await fetch_all()
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
        selected_codes = selected_funds # Ensure this name is available for source logic later

        # Only augment the search query with a fund-name prefix if EXACTLY ONE fund is selected.
        # Prefixing with multiple funds (e.g. 'PPCHF · PPTSF: ...') muddies the semantic search results.
        if "cas" in query_lower or "statement" in query_lower:
            augmented_query = "Consolidated Account Statement CAS download " + query
        elif len(selected_funds) == 1:
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
        
        is_plural_query = "funds" in query_lower or "all fund" in query_lower
        
        # If user asks a general question (expense ratio, exit load) with NO filter, treat it as plural to get all 4 funs
        if not fund_filter and not any(f in query_lower for f in ["flexi", "tax", "liquid", "conservative", "hybrid", "ppfcf", "pptsf", "ppchf", "pplf"]):
            if any(k in query_lower for k in ["expense", "exit load", "aum", "minimum", "manage"]):
                is_plural_query = True
        
        results = []
        if is_plural_query and not fund_filter:
            # Emergency Fix: Perform separate retrievals for each fund to guarantee coverage
            fund_names = ["Parag Parikh Flexi Cap Fund", "Parag Parikh ELSS Tax Saver Fund", 
                          "Parag Parikh Conservative Hybrid Fund", "Parag Parikh Liquid Fund"]
            for fname in fund_names:
                fund_results = self._retriever.retrieve(f"{fname}: {query}", top_k=4) # Increased for better factual coverage
                results.extend(fund_results)
            # Add general query results too
            general_results = self._retriever.retrieve(query, top_k=4)
            results.extend(general_results)
        elif len(selected_funds) > 1:
            # Perform separate retrievals for EACH selected fund to guarantee EVEN coverage!
            fund_names = {
                "PPFCF": "Parag Parikh Flexi Cap Fund",
                "PPTSF": "PPFAS ELSS Tax Saver Fund",
                "PPCHF": "Parag Parikh Conservative Hybrid Fund",
                "PPLF":  "Parag Parikh Liquid Fund",
            }
            for code in selected_funds:
                fname = fund_names.get(code, code)
                fund_results = self._retriever.retrieve(f"{fname}: {query}", top_k=4, fund_filter=code)
                results.extend(fund_results)
            # Add general query results too
            general_results = self._retriever.retrieve(query, top_k=4, fund_filter=fund_filter)
            results.extend(general_results)
        else:
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
        
        # Restore original prompt structure for stability
        if fund_filter:
            import re as pyre
            selected_funds = pyre.split(r'[,·|]', fund_filter)
            display_filter = ", ".join([f.strip() for f in selected_funds if f.strip()])
            fund_scope_str = f"STRICT FILTER: ONLY include data for {display_filter}."
        else:
            fund_scope_str = "ALL FUNDS (no specific fund filter)"
            
        prompt = SYSTEM_PROMPT.format(context=context_str, query=query, fund_scope=fund_scope_str)

        # Step 4 — Call LLM (Groq)
        t_llm_start = time.monotonic()
        try:
            raw_response = await self._call_llm(prompt)
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
        if cleaned.strip().upper().startswith("NO_DATA") or "NO_DATA" in cleaned or not cleaned.strip() or len(cleaned.strip()) < 5:
            return GenerationResult(
                answer=FRIENDLY_NO_DATA,
                raw_llm_response=raw_response,
                retrieved_chunks=[r.__dict__ for r in context_chunks],
                source_urls=[],
                guardrail_triggered=False,
                sentence_count=self._count_sentences(FRIENDLY_NO_DATA),
                elapsed_ms=elapsed,
            )

        # Final source selection refined
        final_source_urls = []
        FRAGMENTS = {
            "PPFCF": "parag-parikh-flexi-cap",
            "PPTSF": "parag-parikh-tax-saver",
            "PPCHF": "parag-parikh-conservative-hybrid",
            "PPLF":  "parag-parikh-liquid"
        }
        # IndMoney mapping
        FUND_SLUG_MAP = {
            "parag-parikh-flexi-cap": "parag-parikh-flexi-cap-direct-growth-3229",
            "parag-parikh-tax-saver": "parag-parikh-tax-saver-fund-direct-growth-1004710",
            "parag-parikh-conservative-hybrid": "parag-parikh-conservative-hybrid-fund-direct-growth-1006619",
            "parag-parikh-liquid": "parag-parikh-liquid-fund-direct-growth-1214"
        }

        # Auto-detect mentioned funds
        query_fragments = []
        answer_fragments = []
        low_query = query.lower()
        low_answer = cleaned.lower()
        
        # 1. Check if user filtered explicitly in UI
        if fund_filter:
            for c in selected_codes:
                if c in FRAGMENTS: query_fragments.append(FRAGMENTS[c])
        
        # 2. Check query (highest relevance) + plurals
        # CRITICAL: Only trigger 'is_plural' source behavior if NO fund filter is applied in UI.
        is_plural = not fund_filter and any(k in low_query for k in ["funds", "all fund", "expense ratio", "fund managers", "exit load", "aum", "each", "both"])
        
        for code, slug in FRAGMENTS.items():
            readable = slug.replace("-", " ")
            # Better matching for PPTSF (ELSS)
            is_match = (code.lower() in low_query or readable in low_query)
            if code == "PPTSF" and not is_match:
                is_match = "elss" in low_query or "tax saver" in low_query

            if is_plural or is_match:
                if slug not in query_fragments: query_fragments.append(slug)
        
        # 3. Check answer (secondary relevance, but ignore trailing canned disclaimer)
        # Expansion: Check first 1000 chars of answer to ensure 4th fund isn't missed in long responses.
        answer_body = low_answer[:1000]
        for code, slug in FRAGMENTS.items():
            readable = slug.replace("-", " ")
            if code.lower() in answer_body or readable in answer_body:
                if slug not in query_fragments and slug not in answer_fragments: 
                    answer_fragments.append(slug)

        # SEVERE SAFETY: If this is a disclaimer / fallback, clear ALL sources
        # EXCEPTION: If the user specifically asked for CAS, do NOT clear sources.
        DISCLAIMER_PHRASE = "I'm INDy, your Parag Parikh Mutual Fund assistant!"
        is_fallback = (DISCLAIMER_PHRASE in cleaned) and (len(cleaned) < 300) and not bool(re.search(r'[\d\%₹]|rs\.', cleaned, re.IGNORECASE))
        
        # Restore sources for CAS even if filtered
        is_cas_query = "cas" in low_query or "statement" in low_query
        
        if is_fallback and not is_cas_query:
            final_source_urls = []
        else:
            # Seed specific URLs
            active_frags = query_fragments + answer_fragments
            seeded_urls = []
            for frag in active_frags:
                seeded_urls.append(f"https://amc.ppfas.com/schemes/{frag}/")
                if frag in FUND_SLUG_MAP:
                    seeded_urls.append(f"https://www.indmoney.com/mutual-funds/{FUND_SLUG_MAP[frag]}")

            all_candidates = list(source_urls) + seeded_urls

            def is_relevant(url: str) -> bool:
                low_url = url.lower()
                if any(f in low_url for f in active_frags): return True
                if "/faqs/" in low_url or "sid" in low_url: return True
                if "download-cas" in low_url: 
                    return "cas" in low_query or "statement" in low_query
                # Tighten general links: only if no frags detected
                if not active_frags and ("amc.ppfas.com" in low_url or "amfiindia.com" in low_url): return True
                return False

            def sort_key(url: str) -> int:
                low_url = url.lower()
                # Priority 0: IndMoney for Query Fund (User Preference)
                if "indmoney.com" in low_url and any(f in low_url for f in query_fragments): return 0
                # Priority 1: PPFAS Scheme for Query Fund
                if "amc.ppfas.com/schemes/" in low_url and any(f in low_url for f in query_fragments): return 1
                # Priority 2: IndMoney for Answer Fund
                if "indmoney.com" in low_url and any(f in low_url for f in answer_fragments): return 2
                # Priority 3: PPFAS Scheme for Answer Fund
                if "amc.ppfas.com/schemes/" in low_url and any(f in low_url for f in answer_fragments): return 3
                # Priority 4: General FAQs
                if "/faqs/" in low_url or "sid" in low_url: return 4
                return 5

            all_raw_sources = sorted([u for u in all_candidates if is_relevant(u)], key=sort_key)
            
            # Deduplicate and Cap with AMC suppression
            seen_norms = set()
            seen_fund_slugs = set() # Track fund slugs that have IndMoney links
            
            # 1. Identify which funds have IndMoney links available
            for u in all_raw_sources:
                if "indmoney.com" in u.lower():
                    for slug in FRAGMENTS.values():
                        if slug in u.lower(): seen_fund_slugs.add(slug)

            final_source_urls = []
            for u in all_raw_sources:
                norm = u.lower().rstrip("/").replace("http://", "").replace("https://", "").replace("www.", "")
                if norm in seen_norms: continue
                
                # AMC Suppression: skip amc.ppfas.com links if an IndMoney link for the SAME fund exists
                is_amc_scheme = "amc.ppfas.com/schemes/" in u.lower()
                if is_amc_scheme:
                    fund_match = next((slug for slug in FRAGMENTS.values() if slug in u.lower()), None)
                    if fund_match and fund_match in seen_fund_slugs:
                        continue # Suppress AMC link
                
                seen_norms.add(norm)
                final_source_urls.append(u)
            
            # Cap at 4 for multi-fund queries, 3 otherwise (Dynamic based on detected funds)
            num_detected = len(set(active_frags))
            cap = max(3, num_detected)
            if is_plural or len(selected_codes) > 1:
                cap = max(cap, 4)
            final_source_urls = final_source_urls[:cap]

        return GenerationResult(
            answer=cleaned,
            raw_llm_response=raw_response,
            retrieved_chunks=[r.__dict__ for r in context_chunks],
            source_urls=final_source_urls,
            guardrail_triggered=False,
            sentence_count=sentence_count,
            elapsed_ms=elapsed,
        )

    async def _call_llm(self, prompt: str) -> str:
        if self._client is None:
            self._client = self._init_groq_client()

        # The groq client .create is blocking if not using AsyncGroq, 
        # but the user requested native async httpx for nav. 
        # For LLM, we should ideally use AsyncGroq.
        
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
