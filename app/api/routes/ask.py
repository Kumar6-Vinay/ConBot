from fastapi import APIRouter, HTTPException, Request

from app.api import deps
from app.core import rate_limit
from app.logging_config import logger
from app.models.ask import ChatRequest
from app.services.conversation import BlockFilter

router = APIRouter()


@router.post("/ask")
async def ask(request: ChatRequest, http_request: Request) -> dict:
    """Whole answer in one response. Kept for clients that cannot stream.

    Returns {answer, web_used, sources, followups, clarify}. `answer` is prose
    only — the structured blocks are parsed out, never shown raw.
    """
    request_id = deps.new_request_id()
    deps.validate_model(request, request_id)
    rate_limit.enforce_rate_limit(http_request, request_id)
    prepared = await deps.prepare(request, request_id)

    raw = await deps.get_ai_answer(prepared["messages"], request.model, request_id)

    blocks = BlockFilter()
    answer = (blocks.feed(raw) + blocks.flush()).strip()
    clarify = blocks.clarify()

    if clarify:
        answer = clarify["question"]
    elif not answer:
        logger.warning("[%s] ask=empty_answer", request_id)
        raise HTTPException(status_code=502, detail="ConBOT returned an empty answer. Please try again.")

    logger.info("[%s] ask=complete clarify=%s", request_id, bool(clarify))
    return {
        "answer": answer,
        "web_used": bool(prepared["sources"]),
        "sources": prepared["sources"],
        "followups": [] if clarify else blocks.followups(),
        "clarify": clarify,
    }
