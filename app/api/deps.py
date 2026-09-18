import uuid
from typing import AsyncIterator, List, Optional

from fastapi import HTTPException

from app.config import AVAILABLE_MODELS, GEMINI_API_KEY
from app.core import security
from app.core.errors import no_llm_error
from app.logging_config import logger
from app.models.ask import ChatRequest
from app.services import conversation, fallback


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def validate_model(request: ChatRequest, request_id: str) -> None:
    """Checked before rate limiting, so a bad request doesn't use up quota."""
    if request.model not in AVAILABLE_MODELS:
        logger.warning("[%s] invalid_model", request_id)
        raise HTTPException(status_code=400, detail="Unsupported model.")


async def prepare(request: ChatRequest, request_id: str) -> dict:
    """Everything both endpoints need: location, search, messages."""

    question = request.prompt.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question.")

    image = security.validate_image(request.image)
    if image and not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Image questions aren't available right now. Please ask in text.",
        )

    loc = conversation.resolve_location(request.timezone, request.language)
    system = conversation.base_prompt(loc)

    logger.info(
        "[%s] request q_hash=%s q_len=%d model=%s country=%s history=%d image=%s",
        request_id, conversation.question_fingerprint(question), len(question),
        request.model, loc["country"], len(request.history), bool(image),
    )

    return {
        "messages": conversation.build_messages(system, request.history, question, None, image),
        "sources": [],
    }


async def get_ai_answer(messages: List[dict], model: str, request_id: str) -> str:
    if not GEMINI_API_KEY:
        raise no_llm_error()
    try:
        return await fallback.get_answer(messages, model, request_id)
    except Exception as e:
        logger.warning("[%s] fallback chain failed: %s: %s", request_id, type(e).__name__, str(e)[:300])
        raise HTTPException(
            status_code=502,
            detail="ConBOT could not answer that right now. Please try again shortly.",
        )


async def stream_answer(
    messages: List[dict],
    model: str,
    request_id: str,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    if not GEMINI_API_KEY:
        raise no_llm_error()
    async for piece in fallback.stream_answer(messages, model, request_id, state):
        yield piece
