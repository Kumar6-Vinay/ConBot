import json
import re
from typing import AsyncIterator, List, Optional

import httpx

from app.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL_MAP, GEMINI_TIMEOUT, MAX_OUTPUT_TOKENS
from app.logging_config import logger


def _gemini_url(model_id: str, method: str) -> str:
    return f"{GEMINI_BASE}/models/{model_id}:{method}"


def _gemini_headers() -> dict:
    return {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}


def _part_from_content(content) -> List[dict]:
    """Turn one OpenAI-style message content into Gemini `parts`.

    A plain string becomes one text part. Our multimodal user turn is a list
    of {type:text|image_url}; translate each into Gemini's shape.
    """
    if isinstance(content, str):
        return [{"text": content}]

    parts: List[dict] = []
    for item in content:
        if item.get("type") == "text":
            parts.append({"text": item["text"]})
        elif item.get("type") == "image_url":
            url = (item.get("image_url") or {}).get("url", "")
            # data:image/png;base64,AAAA...  ->  inlineData for Gemini
            match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", url, re.DOTALL)
            if match:
                parts.append({"inlineData": {"mimeType": match.group(1), "data": match.group(2)}})
    return parts or [{"text": ""}]


def gemini_payload(messages: List[dict]) -> dict:
    """Translate our OpenAI-style messages into a Gemini request body.

    System messages fold into `system_instruction`; user/assistant turns
    become `contents` with role `user`/`model`. We keep building `messages`
    the OpenAI way everywhere else, so only this boundary changes.
    """
    system_texts: List[str] = []
    contents: List[dict] = []

    for message in messages:
        role = message["role"]
        if role == "system":
            # system content is always plain text in our code
            system_texts.append(message["content"] if isinstance(message["content"], str) else "")
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": _part_from_content(message["content"])})

    body: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    if system_texts:
        body["system_instruction"] = {"parts": [{"text": "\n\n".join(t for t in system_texts if t)}]}
    return body


def _extract_text(data: dict) -> str:
    """Pull the text out of a Gemini candidate object."""
    for cand in data.get("candidates", []):
        parts = (cand.get("content") or {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if text:
            return text
    return ""


async def ask_gemini(messages: List[dict], model: str, request_id: str) -> str:
    """Non-streaming call. Used by /ask."""
    model_id = GEMINI_MODEL_MAP.get(model, model)
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT) as client:
            response = await client.post(
                _gemini_url(model_id, "generateContent"),
                json=gemini_payload(messages),
                headers=_gemini_headers(),
            )
            if response.status_code >= 400:
                body = response.text[:500]
                logger.error("[%s] gemini HTTP %d: %s", request_id, response.status_code, body)
                response.raise_for_status()
            data = response.json()

        answer = _extract_text(data)
        if not answer.strip():
            # A blocked prompt returns no text but a promptFeedback block.
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise ValueError(f"Empty Gemini response (blockReason={reason})")

        logger.info("[%s] gemini=ok", request_id)
        return answer.strip()

    except httpx.TimeoutException:
        logger.error("[%s] gemini timeout after %ds", request_id, GEMINI_TIMEOUT)
        raise
    except Exception as e:
        logger.error("[%s] gemini error: %s: %s", request_id, type(e).__name__, str(e)[:200])
        raise


async def stream_gemini(
    messages: List[dict],
    model: str,
    request_id: str,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Yield answer text as it arrives via Gemini SSE. Raises before the first
    token if the upstream call fails, so the caller can still return a clean
    error."""
    model_id = GEMINI_MODEL_MAP.get(model, model)
    # alt=sse makes Gemini emit Server-Sent Events instead of a JSON array.
    url = _gemini_url(model_id, "streamGenerateContent") + "?alt=sse"

    async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT) as client:
        async with client.stream(
            "POST", url, json=gemini_payload(messages), headers=_gemini_headers()
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                logger.error("[%s] gemini HTTP %d: %s", request_id, response.status_code, body[:500])
                response.raise_for_status()

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

                for cand in data.get("candidates", []):
                    reason = cand.get("finishReason")
                    # MAX_TOKENS means the cap cut the answer off; the UI says so.
                    if state is not None and reason and reason != "STOP":
                        state["finish_reason"] = "length" if reason == "MAX_TOKENS" else reason
                    parts = (cand.get("content") or {}).get("parts", [])
                    piece = "".join(p.get("text", "") for p in parts)
                    if piece:
                        yield piece
