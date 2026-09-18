"""OpenRouter client — the fallback-tail provider.

Our internal `messages` are already OpenAI-shaped (see gemini_client.
gemini_payload's docstring), so unlike the Gemini client this needs no
translation layer: they go straight into a standard chat-completions body.

Two OpenRouter-specific failure shapes to watch for, both found live:
  1. An HTTP 200 whose JSON body is itself {"error": {...}} — the upstream
     provider's real status is the embedded `code`, not the HTTP status.
  2. A normal 200 with choices[0].message.content == null alongside a
     hidden `reasoning` field that ate the whole token budget without ever
     answering. Treated the same as an empty Gemini response: a failure to
     advance past, not a crash.
"""
import json
from typing import AsyncIterator, List, Optional

import httpx

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE, MAX_OUTPUT_TOKENS
from app.logging_config import logger


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # OpenRouter asks for these on free models; harmless otherwise.
        "HTTP-Referer": "https://conbot.in",
        "X-Title": "ConBOT",
    }


def _payload(messages: List[dict], model_id: str, stream: bool) -> dict:
    return {
        "model": model_id,
        "messages": messages,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": stream,
    }


class OpenRouterUpstreamError(Exception):
    """A provider-side failure carrying the real status code, whichever of
    the two shapes above it arrived in — lets the caller classify it as
    fail-fast vs advance-the-chain the same way as an httpx.HTTPStatusError."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


def _extract_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise OpenRouterUpstreamError(502, f"no choices in response: {json.dumps(data)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    return content or ""


async def ask_openrouter(messages: List[dict], model_id: str, request_id: str, timeout: float) -> str:
    """One non-streaming attempt against one OpenRouter model."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=_payload(messages, model_id, stream=False),
            headers=_headers(),
        )
        body_text = response.text[:500]
        try:
            data = response.json()
        except ValueError:
            data = None

        if data is not None and "error" in data:
            err = data["error"]
            code = int(err.get("code") or response.status_code or 502)
            logger.warning("[%s] openrouter embedded error model=%s: %s", request_id, model_id, body_text)
            raise OpenRouterUpstreamError(code, err.get("message", body_text))

        if response.status_code >= 400:
            logger.warning("[%s] openrouter HTTP %d model=%s: %s", request_id, response.status_code, model_id, body_text)
            raise OpenRouterUpstreamError(response.status_code, body_text)

        answer = _extract_content(data)
        if not answer.strip():
            raise OpenRouterUpstreamError(502, "empty/null content (likely a hidden reasoning trace)")
        return answer.strip()


async def stream_openrouter(
    messages: List[dict],
    model_id: str,
    request_id: str,
    timeout: float,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """One streaming attempt against one OpenRouter model. Raises before the
    first token on any failure, same invariant as stream_gemini."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{OPENROUTER_BASE}/chat/completions",
            json=_payload(messages, model_id, stream=True),
            headers=_headers(),
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                logger.warning("[%s] openrouter HTTP %d model=%s: %s", request_id, response.status_code, model_id, body[:500])
                raise OpenRouterUpstreamError(response.status_code, body[:500])

            produced = False
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                if "error" in data:
                    err = data["error"]
                    raise OpenRouterUpstreamError(int(err.get("code") or 502), err.get("message", str(err)))

                for choice in data.get("choices", []):
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    finish_reason = choice.get("finish_reason")
                    if state is not None and finish_reason and finish_reason != "stop":
                        state["finish_reason"] = "length" if finish_reason == "length" else finish_reason
                    if piece:
                        produced = True
                        yield piece

            if not produced:
                raise OpenRouterUpstreamError(502, "stream ended with no content (likely a hidden reasoning trace)")
