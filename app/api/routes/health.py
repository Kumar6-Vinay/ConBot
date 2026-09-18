from fastapi import APIRouter

from app.config import GEMINI_API_KEY
from app.core import circuit_breaker

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Report whether the service can actually answer, not just whether it booted."""
    return {
        "status": "healthy" if GEMINI_API_KEY else "degraded",
        "llm_configured": bool(GEMINI_API_KEY),
        # Coarse only — true if any link in the text fallback chain is
        # currently cold. Deliberately no model/provider name: that would
        # tell an anonymous caller exactly where quota exhaustion is
        # working, undoing the Low #10 fix from the security audit.
        "fallback_degraded": circuit_breaker.is_degraded(),
    }
