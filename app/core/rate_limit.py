"""In-memory rate limiting.

/ask and /stream are public and unauthenticated, and each request costs real
Gemini credit. Without a limit, one script in a browser console can drain the
key. This is a fixed-window counter per client IP, held in memory — no extra
service, no extra dependency. It resets if the process restarts, and it is
per-instance if this ever runs on more than one, which is the honest limit of
"no infrastructure" rate limiting. It stops a casual script; it is not a
defense against a determined, distributed abuser.
"""
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

from app.config import (
    CLIENT_IP_HEADER,
    DAILY_PER_IP_LIMIT,
    DAILY_REQUEST_LIMIT,
    MAX_CONCURRENT_STREAMS,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    TRUSTED_PROXY_HOPS,
)
from app.logging_config import logger

_rate_buckets: dict[str, deque] = defaultdict(deque)
_daily_per_ip: dict[str, int] = defaultdict(int)
_daily_request_count = 0
_daily_request_day: Optional[str] = None
_in_flight_streams = 0


def client_ip(request: Request) -> str:
    """Best-effort client address for rate limiting — never for auth."""
    if CLIENT_IP_HEADER:
        value = (request.headers.get(CLIENT_IP_HEADER) or "").strip()
        if value:
            return value

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and TRUSTED_PROXY_HOPS:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            # The entry our nearest trusted proxy appended is the last one.
            index = max(0, len(hops) - TRUSTED_PROXY_HOPS)
            return hops[index]

    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, request_id: str) -> None:
    global _daily_request_count, _daily_request_day

    today = time.strftime("%Y-%m-%d", time.gmtime())
    if today != _daily_request_day:
        _daily_request_day = today
        _daily_request_count = 0
        _daily_per_ip.clear()

    if _daily_request_count >= DAILY_REQUEST_LIMIT:
        logger.warning("[%s] rate_limit=daily_global count=%d", request_id, _daily_request_count)
        raise HTTPException(
            status_code=429,
            detail=(
                "ConBOT is a prototype with a small shared daily allowance, "
                "and it has been used up for today. Please try again tomorrow."
            ),
        )

    ip = client_ip(request)

    if _daily_per_ip[ip] >= DAILY_PER_IP_LIMIT:
        logger.warning("[%s] rate_limit=daily_ip", request_id)
        raise HTTPException(
            status_code=429,
            detail="You've reached today's question limit for this prototype. Please come back tomorrow.",
        )

    now = time.monotonic()
    bucket = _rate_buckets[ip]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        logger.warning("[%s] rate_limit=window in_window=%d", request_id, len(bucket))
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short time. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
    _daily_per_ip[ip] += 1
    _daily_request_count += 1

    # Bound memory: an unbounded number of distinct IPs would otherwise
    # accumulate forever on a long-running process.
    if len(_rate_buckets) > 5000:
        stale = [k for k, v in _rate_buckets.items() if not v]
        for k in stale[:2000]:
            del _rate_buckets[k]


def acquire_stream_slot(request_id: str) -> None:
    """Cap total concurrent /stream connections, across all clients.

    Plain sync function with no `await` inside — under asyncio's cooperative
    scheduling that makes the check-then-increment atomic with respect to
    other requests, no lock needed. Pair every call with release_stream_slot()
    in a finally block, on every exit path.
    """
    global _in_flight_streams
    if _in_flight_streams >= MAX_CONCURRENT_STREAMS:
        logger.warning("[%s] rate_limit=concurrency in_flight=%d", request_id, _in_flight_streams)
        raise HTTPException(
            status_code=429,
            detail="ConBOT is handling a lot of requests right now. Please try again in a moment.",
        )
    _in_flight_streams += 1


def release_stream_slot() -> None:
    global _in_flight_streams
    _in_flight_streams = max(0, _in_flight_streams - 1)
