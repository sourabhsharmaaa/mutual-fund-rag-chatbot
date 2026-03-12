"""
retriever.py
------------
ChromaDB retrieval wrapper for Phase 3.

Wraps the embedder.ChromaStore to:
  - Build the embedding function using the same model-selection logic
  - Expose a clean retrieve() interface for the generator
  - Return structured RetrievalResult objects
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """Structured container for a single retrieved chunk."""
    text:        str
    source_url:  str
    fund_name:   str
    short_name:  str
    field_type:  str
    distance:    float

    def format_for_prompt(self) -> str:
        """Return a clean representation for inclusion in the LLM prompt."""
        return (
            f"[Chunk | fund={self.fund_name} | field={self.field_type} | "
            f"source={self.source_url}]\n{self.text}"
        )


# ---------------------------------------------------------------------------
# Embedding function factory (shared with embedder/pipeline.py)
# ---------------------------------------------------------------------------

def _build_ef():
    """
    Returns the same embedding function used during indexing.
    Enforcing sentence-transformers as the default to match ingest.
    """
    try:
        from chromadb.utils import embedding_functions  # type: ignore
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")  # type: ignore
    except Exception as exc:
        logger.warning("SentenceTransformer EF init failed: %s — using default.", exc)
        return None


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class Retriever:
    """
    Lazy-initialised retriever wrapping ChromaStore.
    The store is created on first call to retrieve() so that
    importing this module doesn't require ChromaDB to be installed.
    """

    def __init__(self):
        self._store = None

    def _get_store(self):
        if self._store is None:
            from embedder.chroma_store import ChromaStore  # type: ignore
            ef = _build_ef()
            self._store = ChromaStore(embedding_fn=ef)
        return self._store

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        fund_filter: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Retrieve top-k chunks most relevant to `query`.

        Args:
            query:       User's natural language question.
            top_k:       Number of results to return.
            fund_filter: Optional PPFAS short name ("PPFCF", "PPTSF",
                         "PPCHF", "PPLF") to scope the search.

        Returns sorted list of RetrievalResult (best match first).
        """
        store = self._get_store()
        raw = store.query(query, n_results=top_k, fund_filter=fund_filter)

        results = []
        for r in raw:
            dist = r.get("distance", 1.0)
            # Relaxed threshold: MiniLM-L6-v2 often has distances in 0.6-0.8 range for relevant results
            if dist > 0.8:
                continue

            results.append(
                RetrievalResult(
                    text=r["text"],
                    source_url=r.get("source_url", "https://amc.ppfas.com"),
                    fund_name=r.get("fund_name", "GENERAL"),
                    short_name=r.get("short_name", "ALL"),
                    field_type=r.get("field_type", "unknown"),
                    distance=dist,
                )
            )
        return results

    def collect_source_urls(self, results: list[RetrievalResult]) -> list[str]:
        """Deduplicated list of source URLs from the retrieved results."""
        seen: set[str] = set()
        urls: list[str] = []
        for r in results:
            if not r.source_url or r.source_url == "NA":
                continue
            
            # Normalize trailing slash
            u = r.source_url.strip().rstrip('/')
            if u not in seen:
                seen.add(u)
                urls.append(r.source_url)
        return urls


# ---------------------------------------------------------------------------
# Module-level singleton (used by generator.py)
# ---------------------------------------------------------------------------
_retriever_instance: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = Retriever()
    return _retriever_instance
