"""Multi-provider fallback chain for text chat.

Both /ask and /stream funnel through get_answer()/stream_answer() here
instead of calling gemini_client directly. This is the only place that
loops across (provider, model) pairs — gemini_client and openrouter_client
each only know how to make one attempt against one model.

Chain shape: config.GEMINI_MODEL_MAP[mode] is always tried first (provider
"google", implicit), then config.TEXT_FALLBACK_CHAIN — a comma-separated
"provider:model_id" string — in order. No model id is hardcoded here; the
chain is entirely env-var-driven (see app/config.py).

Classification, for every attempt:
  - success (non-empty answer)                    -> record breaker success,
                                                       done.
  - 404 / 429 / any 5xx / timeout / empty content  -> record breaker failure,
                                                       advance to the next
                                                       link. Both clients put
                                                       the model id in the
                                                       request itself (the
                                                       OpenRouter body or the
                                                       Gemini URL path), never
                                                       in anything else about
                                                       the request shape, so a
                                                       404 here can only mean
                                                       "this model id is
                                                       gone" — exactly what a
                                                       different link can fix.
  - 400 / 401 / 403 / ContentBlocked               -> raise immediately. A
                                                       different model won't
                                                       fix a malformed
                                                       request, a bad key, or
                                                       a policy refusal.

For streaming, once a single piece has been yielded from an attempt, any
later failure from that same attempt propagates as-is — never silently
advances to a different model mid-answer, which would garble or duplicate
output the client has already started rendering.
"""
import time
from typing import AsyncIterator, List, Optional, Tuple

import httpx

from app.config import (
    FALLBACK_ATTEMPT_TIMEOUT,
    FALLBACK_TOTAL_BUDGET,
    GEMINI_MODEL_MAP,
    TEXT_FALLBACK_CHAIN,
)
from app.core import circuit_breaker
from app.core.errors import ContentBlocked
from app.logging_config import logger
from app.services import gemini_client, openrouter_client
from app.services.openrouter_client import OpenRouterUpstreamError

# Codes that mean "this exact request is bad," not "this model is down."
# Retrying it against a different model/provider won't help. 404 is
# deliberately not here — see the module docstring.
_FAIL_FAST_CODES = {400, 401, 403}


def _parse_chain(mode: str) -> List[Tuple[str, str]]:
    primary_spec = GEMINI_MODEL_MAP[mode]
    # Primary model can be "provider:model_id" (e.g. "openrouter:qwen/qwen3.8-27b:free")
    # or just "model_id" (legacy, assumed to be Google)
    if ":" in primary_spec:
        parts = primary_spec.split(":", 1)
        primary = (parts[0].strip(), parts[1].strip())
    else:
        primary = ("google", primary_spec)
    chain = [primary]
    for entry in TEXT_FALLBACK_CHAIN.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        provider, model_id = entry.split(":", 1)
        provider = provider.strip()
        model_id = model_id.strip()
        if provider and model_id and (provider, model_id) not in chain:
            chain.append((provider, model_id))
    return chain


def _classify(exc: Exception) -> Optional[int]:
    """Return the effective HTTP status code for an attempt's exception, or
    None if it isn't one of the codes this chain understands (caller treats
    unknown exceptions as fail-fast, same as today's single-model behavior)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    if isinstance(exc, OpenRouterUpstreamError):
        return exc.status_code
    return None


def _should_advance(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, ValueError)):
        return True
    if isinstance(exc, ContentBlocked):
        return False
    code = _classify(exc)
    if code is None:
        return False
    if code in _FAIL_FAST_CODES:
        return False
    return code == 404 or code == 429 or 500 <= code < 600


async def get_answer(messages: List[dict], mode: str, request_id: str) -> str:
    """Non-streaming path, used by /ask."""
    deadline = time.monotonic() + FALLBACK_TOTAL_BUDGET
    chain = _parse_chain(mode)

    for provider, model_id in chain:
        key = f"{provider}:{model_id}"
        if circuit_breaker.is_cold(key):
            continue
        if time.monotonic() >= deadline:
            logger.warning("[%s] fallback_budget_exhausted before trying %s", request_id, key)
            break

        try:
            if provider == "google":
                answer = await gemini_client.ask_gemini(messages, model_id, request_id, FALLBACK_ATTEMPT_TIMEOUT)
            elif provider == "openrouter":
                answer = await openrouter_client.ask_openrouter(messages, model_id, request_id, FALLBACK_ATTEMPT_TIMEOUT)
            else:
                logger.error("[%s] fallback unknown provider=%s, skipping", request_id, provider)
                continue
            circuit_breaker.record_success(key)
            logger.info("[%s] fallback_success provider_model=%s", request_id, key)
            return answer

        except Exception as e:
            if _should_advance(e):
                circuit_breaker.record_failure(key, request_id)
                logger.warning(
                    "[%s] fallback_advance provider_model=%s reason=%s: %s",
                    request_id, key, type(e).__name__, str(e)[:200],
                )
                continue
            logger.warning(
                "[%s] fallback_fail_fast provider_model=%s reason=%s: %s",
                request_id, key, type(e).__name__, str(e)[:200],
            )
            raise

    logger.error("[%s] fallback_exhausted every link cold or failed", request_id)
    raise RuntimeError("Every text fallback link is unavailable")


async def stream_answer(
    messages: List[dict], mode: str, request_id: str, state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Streaming path, used by /stream — the only path the live frontend
    actually calls."""
    deadline = time.monotonic() + FALLBACK_TOTAL_BUDGET
    chain = _parse_chain(mode)

    for provider, model_id in chain:
        key = f"{provider}:{model_id}"
        if circuit_breaker.is_cold(key):
            continue
        if time.monotonic() >= deadline:
            logger.warning("[%s] fallback_budget_exhausted before trying %s", request_id, key)
            break

        produced_here = False
        try:
            if provider == "google":
                source = gemini_client.stream_gemini(messages, model_id, request_id, FALLBACK_ATTEMPT_TIMEOUT, state)
            elif provider == "openrouter":
                source = openrouter_client.stream_openrouter(messages, model_id, request_id, FALLBACK_ATTEMPT_TIMEOUT, state)
            else:
                logger.error("[%s] fallback unknown provider=%s, skipping", request_id, provider)
                continue

            async for piece in source:
                produced_here = True
                yield piece

            circuit_breaker.record_success(key)
            logger.info("[%s] fallback_success provider_model=%s", request_id, key)
            return

        except Exception as e:
            if produced_here:
                # Already sent bytes to the real client for this answer —
                # advancing now would garble or duplicate it. Let it
                # propagate exactly like today's single-model failure path.
                logger.warning(
                    "[%s] fallback_mid_stream_failure provider_model=%s reason=%s: %s",
                    request_id, key, type(e).__name__, str(e)[:200],
                )
                raise

            if _should_advance(e):
                circuit_breaker.record_failure(key, request_id)
                logger.warning(
                    "[%s] fallback_advance provider_model=%s reason=%s: %s",
                    request_id, key, type(e).__name__, str(e)[:200],
                )
                continue

            logger.warning(
                "[%s] fallback_fail_fast provider_model=%s reason=%s: %s",
                request_id, key, type(e).__name__, str(e)[:200],
            )
            raise

    logger.error("[%s] fallback_exhausted every link cold or failed", request_id)
    raise RuntimeError("Every text fallback link is unavailable")
