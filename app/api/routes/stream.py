import json
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import config
from app.api import deps
from app.core import rate_limit
from app.core.errors import no_llm_error
from app.logging_config import logger
from app.models.ask import ChatRequest
from app.services.conversation import BlockFilter

router = APIRouter()


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/stream")
async def stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """Server-sent events: sources first, then answer text as it is generated."""

    request_id = deps.new_request_id()
    deps.validate_model(request, request_id)

    # Check configuration before the response starts. Once headers are sent
    # the status code is fixed, so a 503 raised inside the generator would
    # reach the client as a 200 with an error event.
    if not config.GEMINI_API_KEY:
        raise no_llm_error()

    rate_limit.enforce_rate_limit(http_request, request_id)
    prepared = await deps.prepare(request, request_id)
    async def events() -> AsyncIterator[str]:
        if prepared["sources"]:
            yield sse({"type": "sources", "sources": prepared["sources"]})

        produced = False
        state = {}
        blocks = BlockFilter()
        try:
            async for piece in deps.stream_answer(
                prepared["messages"], request.model, request_id, state
            ):
                visible = blocks.feed(piece)
                if visible:
                    produced = True
                    yield sse({"type": "delta", "text": visible})

            tail = blocks.flush()
            if tail:
                produced = True
                yield sse({"type": "delta", "text": tail})

        except Exception as e:
            logger.warning(
                "[%s] stream=failed type=%s produced=%s", request_id, type(e).__name__, produced
            )
            # Nothing sent yet — a clean error still reads well in the UI.
            # Mid-stream, the client keeps what it has and shows the notice.
            yield sse({
                "type": "error",
                "detail": "ConBOT could not finish that answer. Please try again.",
            })
            return

        clarify = blocks.clarify()
        if clarify:
            # A clarify reply has no prose at all — the question is the answer.
            logger.info("[%s] stream=clarify", request_id)
            yield sse({"type": "clarify", **clarify})
            yield sse({"type": "done"})
            return

        if not produced:
            yield sse({"type": "error", "detail": "ConBOT returned an empty answer."})
            return

        if state.get("finish_reason") == "length":
            logger.info("[%s] stream=truncated", request_id)
            yield sse({"type": "truncated"})
        else:
            followups = blocks.followups()
            if followups:
                yield sse({"type": "followups", "questions": followups})

        logger.info("[%s] stream=complete", request_id)
        yield sse({"type": "done"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # stop proxies buffering the stream
            "Connection": "keep-alive",
        },
    )
