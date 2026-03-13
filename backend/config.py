"""
config.py
---------
Central configuration for the PPFAS RAG chatbot backend.
All env vars and runtime constants live here.

Set environment variables in your shell or a .env file:
    export GEMINI_API_KEY="your_key_here"
    export CHROMA_PATH="./vector_store"         # optional
    export GEMINI_MODEL="gemini-1.5-flash"       # optional
"""

from __future__ import annotations

import os
from pathlib import Path

# Load variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Project root (two levels up from backend/)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Groq LLM settings
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL:   str = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# LLM generation parameters
LLM_TEMPERATURE:    float = 0.1
LLM_MAX_TOKENS:     int   = 1024
LLM_TOP_P:          float = 0.9

# ---------------------------------------------------------------------------
# ChromaDB vector store
# ---------------------------------------------------------------------------
CHROMA_PATH: str = os.environ.get(
    "CHROMA_PATH",
    str(ROOT / "vector_store"),
)

# Retrieval settings
RETRIEVAL_TOP_K:        int   = 20   # chunks fetched from ChromaDB
RETRIEVAL_CONTEXT_K:    int   = 12   # top-K passed to the LLM prompt

# ---------------------------------------------------------------------------
# Guardrail settings
# ---------------------------------------------------------------------------
MAX_RESPONSE_SENTENCES: int   = 10    # high cap for table/list support

# ---------------------------------------------------------------------------
# Static URLs used in guardrail refusals
# ---------------------------------------------------------------------------
SEBI_ADVISOR_URL    = "https://investor.sebi.gov.in/"
PPFAS_HOME_URL      = "https://amc.ppfas.com"
PPFAS_FACTSHEET_URL = "https://amc.ppfas.com/downloads/factsheet/"
AMFI_EDUCATION_URL  = "https://www.amfiindia.com/investor/knowledge-center"

# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def require_api_key() -> str:
    """Raises RuntimeError if the Groq API key is not set."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Set it with: export GROQ_API_KEY='your_key'"
        )
    return GROQ_API_KEY
