"""
chroma_store.py
---------------
ChromaDB collection manager for Phase 2.

Manages a persistent local ChromaDB instance at vector_store/.
Exposes two collections:
  - ppfas_scheme_facts : scheme-level field chunks
  - ppfas_general      : FAQs, taxation, general knowledge chunks

Both share the same embedding function so queries can target
individual collections or all at once.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb # type: ignore
from chromadb import Settings# type: ignore
from chromadb.utils.embedding_functions import EmbeddingFunction # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
VECTOR_STORE_DIR = ROOT / "vector_store"


# ---------------------------------------------------------------------------
# Routing: chunk field_type → collection name
# ---------------------------------------------------------------------------
SCHEME_FIELD_TYPES = {
    "expense_ratio", "exit_load", "min_sip", "lock_in",
    "riskometer", "benchmark", "fund_manager", "aum",
    "category", "date_of_allotment", "investment_objective",
}

GENERAL_FIELD_TYPES = {
    "faq", "taxation_ltcg", "taxation_stcg", "taxation_elss",
    "taxation_summary", "riskometer_definition", "expense_ratio_definition",
    "cas_procedure", "riskometer_level",
}

COLLECTION_SCHEME  = "ppfas_scheme_facts"
COLLECTION_GENERAL = "ppfas_general"


def _route_to_collection(field_type: str) -> str:
    if field_type in SCHEME_FIELD_TYPES:
        return COLLECTION_SCHEME
    return COLLECTION_GENERAL


# ---------------------------------------------------------------------------
# ChromaStore
# ---------------------------------------------------------------------------

class ChromaStore:
    """
    Manages two persistent ChromaDB collections.

    Usage:
        store = ChromaStore(embedding_fn=my_fn)
        store.upsert(chunks)                    # add/update chunks
        results = store.query("exit load?", n=3)  # query across both
    """

    def __init__(self, embedding_fn: EmbeddingFunction | None = None):
        VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(VECTOR_STORE_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

        if embedding_fn is None:
            # Use the central embedding factory so HF / Gemini API is used
            # instead of auto-loading the local all-MiniLM-L6-v2 model.
            from embedder.pipeline import _build_embedding_function  # type: ignore
            embedding_fn = _build_embedding_function()

        ef_kwargs = {"embedding_function": embedding_fn}

        self._col_scheme = self._client.get_or_create_collection(
            name=COLLECTION_SCHEME,
            metadata={"hnsw:space": "cosine"},
            **ef_kwargs,
        )
        self._col_general = self._client.get_or_create_collection(
            name=COLLECTION_GENERAL,
            metadata={"hnsw:space": "cosine"},
            **ef_kwargs,
        )

        logger.info(
            "ChromaStore ready | scheme_facts=%d docs | general=%d docs",
            self._col_scheme.count(),
            self._col_general.count(),
        )

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def upsert(self, chunks: list[dict[str, Any]]) -> dict[str, int]:
        """
        Upsert a list of chunk dicts (from chunker.py).
        Returns count added per collection.
        """
        scheme_ids, scheme_docs, scheme_meta = [], [], []
        general_ids, general_docs, general_meta = [], [], []

        for chunk in chunks:
            cid = chunk["chunk_id"]
            text = chunk["text"]
            meta = {
                "source_url":      chunk.get("source_url", "NA"),
                "all_source_urls": chunk.get("all_source_urls", "NA"),
                "fund_name":       chunk.get("fund_name", "GENERAL"),
                "short_name":      chunk.get("short_name", "ALL"),
                "field_type":      chunk.get("field_type", "unknown"),
            }

            if _route_to_collection(chunk.get("field_type", "")) == COLLECTION_SCHEME:
                scheme_ids.append(cid)
                scheme_docs.append(text)
                scheme_meta.append(meta)
            else:
                general_ids.append(cid)
                general_docs.append(text)
                general_meta.append(meta)

        counts = {}

        if scheme_ids:
            self._col_scheme.upsert(
                ids=scheme_ids,
                documents=scheme_docs,
                metadatas=scheme_meta,
            )
            counts[COLLECTION_SCHEME] = len(scheme_ids)
            logger.info("Upserted %d chunks → %s", len(scheme_ids), COLLECTION_SCHEME)

        if general_ids:
            self._col_general.upsert(
                ids=general_ids,
                documents=general_docs,
                metadatas=general_meta,
            )
            counts[COLLECTION_GENERAL] = len(general_ids)
            logger.info("Upserted %d chunks → %s", len(general_ids), COLLECTION_GENERAL)

        return counts

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        fund_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query collections and return merged, re-ranked results.

        When fund_filter is provided we use a TWO-PHASE approach:
          Phase 1: Strict fund-only WHERE on ppfas_scheme_facts.
                   This guarantees PPTSF data is retrieved for PPTSF questions.
          Phase 2: General knowledge (ppfas_general) WITHOUT a fund filter,
                   but only appended if Phase 1 returns fewer than n_results.
          Final slice: only the top n_results by cosine distance are returned.

        When no fund_filter is provided we query both collections with no filter.
        """
        per_col = max(n_results, 3)
        all_results: list[dict] = []

        if fund_filter:
            # ── Phase 1: strict fund-specific scheme facts ──
            # Support both single string and list of strings for multi-fund cleanup
            if isinstance(fund_filter, list):
                if len(fund_filter) == 1:
                    strict_where = {"short_name": fund_filter[0]}
                else:
                    strict_where = {"short_name": {"$in": fund_filter}}
            else:
                # If there's a delimiter (· or ,), split it into a list
                import re as pyre
                parts = [p.strip() for p in pyre.split(r'[,·|]', fund_filter) if p.strip()]
                if len(parts) > 1:
                    strict_where = {"short_name": {"$in": parts}}
                else:
                    strict_where = {"short_name": parts[0] if parts else fund_filter}
            try:
                count = self._col_scheme.count()
                if count > 0:
                    result = self._col_scheme.query(
                        query_texts=[query_text],
                        n_results=min(per_col, count),
                        where=strict_where,
                        include=["documents", "metadatas", "distances"],
                    )
                    docs  = result["documents"][0]
                    metas = result["metadatas"][0]
                    dists = result["distances"][0]
                    for doc, meta, dist in zip(docs, metas, dists):
                        all_results.append({
                            "text":       doc,
                            "source_url": meta.get("source_url", "NA"),
                            "fund_name":  meta.get("fund_name", "NA"),
                            "short_name": meta.get("short_name", "NA"),
                            "field_type": meta.get("field_type", "NA"),
                            "distance":   dist,
                        })
            except Exception as exc:
                logger.warning("Phase-1 query failed: %s", exc)

            # ── Phase 2: general collection (no fund filter) only as supplement ──
            # Only query if we need more results to fill n_results
            if len(all_results) < n_results:
                needed = n_results - len(all_results)
                try:
                    count = self._col_general.count()
                    if count > 0:
                        result = self._col_general.query(
                            query_texts=[query_text],
                            n_results=min(needed + 2, count),
                            include=["documents", "metadatas", "distances"],
                        )
                        docs  = result["documents"][0]
                        metas = result["metadatas"][0]
                        dists = result["distances"][0]
                        for doc, meta, dist in zip(docs, metas, dists):
                            all_results.append({
                                "text":       doc,
                                "source_url": meta.get("source_url", "NA"),
                                "fund_name":  meta.get("fund_name", "NA"),
                                "short_name": meta.get("short_name", "NA"),
                                "field_type": meta.get("field_type", "NA"),
                                "distance":   dist,
                            })
                except Exception as exc:
                    logger.warning("Phase-2 general query failed: %s", exc)

        else:
            # ── No fund filter: query both collections ──
            # This allows the LLM to see scheme facts for ALL funds 
            # if the user asks a general question like "What are the expense ratios?"
            # Increase n_results significantly to ensure chunks from ALL funds reach the LLM.
            n_all_funds = max(n_results, 20)
            for col in (self._col_scheme, self._col_general):
                try:
                    count = col.count()
                    if count == 0:
                        continue
                    result = col.query(
                        query_texts=[query_text],
                        n_results=min(n_all_funds, count),
                        include=["documents", "metadatas", "distances"],
                    )
                    docs  = result["documents"][0]
                    metas = result["metadatas"][0]
                    dists = result["distances"][0]
                    for doc, meta, dist in zip(docs, metas, dists):
                        all_results.append({
                            "text":       doc,
                            "source_url": meta.get("source_url", "NA"),
                            "fund_name":  meta.get("fund_name", "NA"),
                            "short_name": meta.get("short_name", "NA"),
                            "field_type": meta.get("field_type", "NA"),
                            "distance":   dist,
                        })
                except Exception as exc:
                    logger.warning("Query failed on collection %s: %s", col.name, exc)

        # Sort by cosine distance (lower = more similar) and return top n
        all_results.sort(key=lambda r: r["distance"])
        return all_results[:n_results] # type: ignore

    # -----------------------------------------------------------------------
    # Info
    # -----------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            COLLECTION_SCHEME:  self._col_scheme.count(),
            COLLECTION_GENERAL: self._col_general.count(),
        }

    def reset(self) -> None:
        """Delete and recreate both collections (use for re-indexing)."""
        self._client.delete_collection(COLLECTION_SCHEME)
        self._client.delete_collection(COLLECTION_GENERAL)
        self._col_scheme  = self._client.get_or_create_collection(
            COLLECTION_SCHEME,  metadata={"hnsw:space": "cosine"})
        self._col_general = self._client.get_or_create_collection(
            COLLECTION_GENERAL, metadata={"hnsw:space": "cosine"})
        logger.info("Collections reset.")
