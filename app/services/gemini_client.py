import json
import re
from typing import AsyncIterator, List, Optional

import httpx

from app.config import GEMINI_API_KEY, GEMINI_BASE, MAX_OUTPUT_TOKENS
from app.core.errors import ContentBlocked
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


async def ask_gemini(messages: List[dict], model_id: str, request_id: str, timeout: float) -> str:
    """One non-streaming attempt against one Gemini model. No retry, no
    fallback — that's app.services.fallback's job, since it now spans more
    than one provider."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _gemini_url(model_id, "generateContent"),
                json=gemini_payload(messages),
                headers=_gemini_headers(),
            )
            if response.status_code >= 400:
                body = response.text[:500]
                logger.warning("[%s] gemini HTTP %d: %s", request_id, response.status_code, body)
                response.raise_for_status()
            data = response.json()

        answer = _extract_text(data)
        if not answer.strip():
            # A blocked prompt returns no text but a promptFeedback block —
            # a policy refusal, not a transient failure, so it's fail-fast
            # for the fallback chain. A genuinely empty (unblocked) response
            # is worth trying the next model for instead.
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            if reason:
                raise ContentBlocked(f"Gemini blocked the prompt: {reason}")
            raise ValueError("Empty Gemini response with no blockReason")

        return answer.strip()

    except httpx.TimeoutException:
        logger.warning("[%s] gemini timeout after %ss (model=%s)", request_id, timeout, model_id)
        raise


async def stream_gemini(
    messages: List[dict],
    model_id: str,
    request_id: str,
    timeout: float,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """One streaming attempt against one Gemini model. Raises before the
    first token if the upstream call fails, so the caller can still fall
    back to the next (provider, model) pair cleanly."""
    # alt=sse makes Gemini emit Server-Sent Events instead of a JSON array.
    url = _gemini_url(model_id, "streamGenerateContent") + "?alt=sse"

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", url, json=gemini_payload(messages), headers=_gemini_headers()
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                logger.warning("[%s] gemini HTTP %d: %s", request_id, response.status_code, body[:500])
                response.raise_for_status()

            produced = False
            block_reason = None
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

                feedback_reason = (data.get("promptFeedback") or {}).get("blockReason")
                if feedback_reason:
                    block_reason = feedback_reason

                for cand in data.get("candidates", []):
                    reason = cand.get("finishReason")
                    # MAX_TOKENS means the cap cut the answer off; the UI says so.
                    if state is not None and reason and reason != "STOP":
                        state["finish_reason"] = "length" if reason == "MAX_TOKENS" else reason
                    parts = (cand.get("content") or {}).get("parts", [])
                    piece = "".join(p.get("text", "") for p in parts)
                    if piece:
                        produced = True
                        yield piece

            if not produced:
                if block_reason:
                    raise ContentBlocked(f"Gemini blocked the prompt: {block_reason}")
                raise ValueError("Empty Gemini stream with no blockReason")
