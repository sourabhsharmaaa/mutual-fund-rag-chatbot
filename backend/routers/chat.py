from fastapi import APIRouter, HTTPException
from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.generator import get_generator

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def generate_chat_response(request: ChatRequest):
    try:
        generator = get_generator()
        result = generator.generate(
            query=request.query,
            fund_filter=request.scheme_filter
        )
        
        # Combine sources into a single string for simple UI parsing if needed
        # Or just pass the first one, or comma-separated
        primary_source = result.source_urls[0] if result.source_urls else "https://amc.ppfas.com"
        joined_sources = ", ".join(result.source_urls) if result.source_urls else primary_source
        
        return ChatResponse(
            answer=result.answer,
            source_url=joined_sources,  # For the frontend to render as link easily
            sources=result.source_urls,
            guardrail_triggered=result.guardrail_triggered,
            response_time_ms=int(result.elapsed_ms)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
