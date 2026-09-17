from fastapi import APIRouter

from app.config import GEMINI_API_KEY, GEMINI_MODEL_MAP

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Report whether the service can actually answer, not just whether it booted."""
    return {
        "status": "healthy" if GEMINI_API_KEY else "degraded",
        "llm_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL_MAP["text"],
    }
