from fastapi import APIRouter

from app import config
from app.core import circuit_breaker

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Report whether the service has at least one LLM provider configured."""
    llm_configured = any((config.GEMINI_API_KEY, config.OPENROUTER_API_KEY, config.NVIDIA_API_KEY))
    return {
        "status": "healthy" if llm_configured else "degraded",
        "llm_configured": llm_configured,
        # Coarse only — true if any link in the text fallback chain is
        # currently cold. Deliberately no model/provider name: that would
        # tell an anonymous caller exactly where quota exhaustion is
        # working, undoing the Low #10 fix from the security audit.
        "fallback_degraded": circuit_breaker.is_degraded(),
    }
