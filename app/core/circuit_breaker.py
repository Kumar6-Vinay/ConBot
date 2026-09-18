"""In-memory circuit breaker for the text fallback chain.

Same pattern as core/rate_limit.py: no extra service, held in memory,
per-instance if this ever runs on more than one (an existing, documented
limit of this whole "no infrastructure" approach). A single failure for a
(provider, model) pair is normal — that's what the fallback chain is for.
Repeated failures across separate requests are a real signal that pair is
currently down, not just momentarily out of quota, so it gets skipped
entirely (not even attempted) until a cooldown elapses.
"""
import time
from typing import Dict, Tuple

from app.config import BREAKER_COOLDOWN_SECONDS, BREAKER_FAILURE_THRESHOLD
from app.logging_config import logger

_failures: Dict[str, int] = {}
_cold_until: Dict[str, float] = {}


def is_cold(key: str) -> bool:
    until = _cold_until.get(key)
    return until is not None and time.monotonic() < until


def record_success(key: str) -> None:
    if _failures.pop(key, None) or _cold_until.pop(key, None):
        logger.info("breaker_close provider_model=%s", key)


def record_failure(key: str, request_id: str) -> None:
    count = _failures.get(key, 0) + 1
    _failures[key] = count
    if count >= BREAKER_FAILURE_THRESHOLD:
        _cold_until[key] = time.monotonic() + BREAKER_COOLDOWN_SECONDS
        logger.warning(
            "[%s] breaker_open provider_model=%s failures=%d cooldown=%ds",
            request_id, key, count, BREAKER_COOLDOWN_SECONDS,
        )


def is_degraded() -> bool:
    """True if anything in the chain is currently cold. Deliberately coarse
    — no model or provider name — so /health can report it without handing
    an anonymous caller a map of exactly which upstream quotas are exhausted."""
    now = time.monotonic()
    return any(until > now for until in _cold_until.values())


def snapshot() -> Dict[str, Tuple[int, float]]:
    """For tests/debugging only — never exposed over HTTP."""
    now = time.monotonic()
    return {
        key: (_failures.get(key, 0), max(0.0, _cold_until.get(key, 0.0) - now))
        for key in set(_failures) | set(_cold_until)
    }
