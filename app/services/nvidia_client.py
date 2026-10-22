"""NVIDIA NIM client — direct provider for Nemotron models via build.nvidia.com.

Uses NVIDIA's OpenAI-compatible chat-completions endpoint. No translation
layer needed: our internal `messages` are already OpenAI-shaped and pass
straight into the request body.

NVIDIA-specific failure shapes:
  1. HTTP 401 — API key missing/expired (fail-fast, advance-the-chain won't help)
  2. HTTP 404 — model slug not found / retired (advance to next link)
  3. HTTP 429/5xx — transient (advance to next link)
"""
import json
from typing import AsyncIterator, List, Optional

import httpx

from app.config import MAX_OUTPUT_TOKENS, NVIDIA_API_KEY, NVIDIA_BASE
from app.logging_config import logger


class NVIDIAUpstreamError(Exception):
    """A provider-side failure carrying the real status code, so the caller can
    classify it as fail-fast vs advance-the-chain the same way as an
    httpx.HTTPStatusError."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        # NVIDIA requests these for telemetry; harmless otherwise.
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


def _extract_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise NVIDIAUpstreamError(502, f"no choices in response: {json.dumps(data)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    return content or ""


async def ask_nvidia(messages: List[dict], model_id: str, request_id: str, timeout: float) -> str:
    """One non-streaming attempt against one NVIDIA model."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{NVIDIA_BASE}/chat/completions",
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
            logger.warning("[%s] nvidia embedded error model=%s: %s", request_id, model_id, body_text)
            raise NVIDIAUpstreamError(code, err.get("message", body_text))

        if response.status_code >= 400:
            logger.warning("[%s] nvidia HTTP %d model=%s: %s", request_id, response.status_code, model_id, body_text)
            raise NVIDIAUpstreamError(response.status_code, body_text)

        answer = _extract_content(data)
        if not answer.strip():
            raise NVIDIAUpstreamError(502, "empty/null content (likely a hidden reasoning trace)")
        return answer.strip()


async def stream_nvidia(
    messages: List[dict],
    model_id: str,
    request_id: str,
    timeout: float,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """One streaming attempt against one NVIDIA model. Raises before the first
    token on any failure, same invariant as stream_gemini / stream_openrouter."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{NVIDIA_BASE}/chat/completions",
            json=_payload(messages, model_id, stream=True),
            headers=_headers(),
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                logger.warning("[%s] nvidia HTTP %d model=%s: %s", request_id, response.status_code, model_id, body[:500])
                raise NVIDIAUpstreamError(response.status_code, body[:500])

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
                    raise NVIDIAUpstreamError(int(err.get("code") or 502), err.get("message", str(err)))

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
                raise NVIDIAUpstreamError(502, "stream ended with no content (likely a hidden reasoning trace)")
