from pydantic import BaseModel # type: ignore
from typing import List, Optional

class ChatRequest(BaseModel):
    query: str
    scheme_filter: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    source_url: str  # Kept singular as per UI mockup requirement, will join if multiple
    sources: List[str]
    guardrail_triggered: bool
    response_time_ms: int
