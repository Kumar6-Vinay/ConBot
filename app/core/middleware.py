"""ASGI-level request middleware.

Separate from rate_limit.py: that limits how often a client can call an
endpoint; this limits how large a single request body can be, checked
before FastAPI/Pydantic ever read it.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import MAX_BODY_BYTES


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject an oversized body by its declared Content-Length up front.

    Pydantic's own max_length checks only run after the whole body has
    already been read into memory and JSON-parsed — for a large-but-invalid
    body, that cost is paid before validation ever gets a chance to reject
    it. A client that omits Content-Length (chunked transfer) isn't caught
    here; this stops the common case (any normal HTTP client, including a
    simple script, sets it automatically), not a determined evasion attempt.
    """

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = False
            if too_large:
                return JSONResponse(
                    {"detail": "Request body too large."}, status_code=413
                )
        return await call_next(request)
