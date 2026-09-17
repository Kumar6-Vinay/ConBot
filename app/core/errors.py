from fastapi import HTTPException

from app.logging_config import logger


def no_llm_error() -> HTTPException:
    logger.error("GEMINI_API_KEY is not set — check the deployed environment")
    return HTTPException(
        status_code=503, detail="ConBOT is not configured to answer questions yet."
    )
