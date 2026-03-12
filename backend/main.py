from fastapi import FastAPI # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from backend.routers import chat
import os

app = FastAPI(title="PPFAS RAG Backend API", version="1.0.0")

# Allow CORS for local React development
origins = [
    "http://localhost:5173", # Vite default
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API router
app.include_router(chat.router, prefix="/api")

@app.on_event("startup")
async def startup_event():
    # Pre-init the RAG generator (loads embedding model, etc.)
    from backend.services.generator import get_generator # type: ignore
    get_generator()

@app.get("/api/status")
def get_service_status():
    """Returns the last updated timestamp for the data."""
    import json
    metadata_path = os.path.join(os.getcwd(), "data", "metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"last_updated": "Initial data", "status": "ok"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn # type: ignore
    # Allow running directly via python -m backend.main
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
