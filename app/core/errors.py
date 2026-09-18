from fastapi import HTTPException

from app.logging_config import logger


class ContentBlocked(Exception):
    """The prompt itself was refused (safety/policy), not a transient
    failure. A different model in the fallback chain might have a different
    threshold, but per product decision this fails fast instead of trying —
    treating a policy refusal as "this model is down" would be misleading,
    and silently trying another model to route around a safety block is not
    behavior to build by default."""


def no_llm_error() -> HTTPException:
    logger.error("GEMINI_API_KEY is not set — check the deployed environment")
    return HTTPException(
        status_code=503, detail="ConBOT is not configured to answer questions yet."
    )
