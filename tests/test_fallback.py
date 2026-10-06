"""Unit tests for the multi-provider text fallback chain. No network: every
provider call is faked. Async functions are driven with asyncio.run() rather
than pytest-asyncio, matching this repo's existing no-extra-test-deps style.

Run:  pip install -r requirements.txt -r requirements-dev.txt && pytest -q
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "sk-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.core import circuit_breaker  # noqa: E402
from app.core.errors import ContentBlocked  # noqa: E402
from app.services import fallback, gemini_client, openrouter_client  # noqa: E402
from app.services.openrouter_client import OpenRouterUpstreamError  # noqa: E402


def run(coro):
    return asyncio.run(coro)


async def drain(gen):
    return [piece async for piece in gen]


def http_status_error(code):
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status_code=code, request=request)
    return httpx.HTTPStatusError(f"HTTP {code}", request=request, response=response)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    circuit_breaker._failures.clear()
    circuit_breaker._cold_until.clear()
    monkeypatch.setattr(fallback, "TEXT_FALLBACK_CHAIN", "google:model-b,google:model-c")
    monkeypatch.setattr(fallback, "GEMINI_MODEL_MAP", {"text": "model-a"})
    monkeypatch.setattr(fallback, "FALLBACK_ATTEMPT_TIMEOUT", 5)
    monkeypatch.setattr(fallback, "FALLBACK_TOTAL_BUDGET", 45)
    yield


# ---------------------------------------------------------------- get_answer: chain advance

def test_advances_past_429_then_succeeds(monkeypatch):
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        if model_id == "model-a":
            raise http_status_error(429)
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    result = run(fallback.get_answer([], "text", "req1"))

    assert result == "answer from model-b"
    assert calls == ["model-a", "model-b"]


def test_advances_past_5xx(monkeypatch):
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        if model_id == "model-a":
            raise http_status_error(503)
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    result = run(fallback.get_answer([], "text", "req1"))
    assert result == "answer from model-b"


def test_advances_past_timeout(monkeypatch):
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        if model_id == "model-a":
            raise httpx.TimeoutException("timed out")
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    result = run(fallback.get_answer([], "text", "req1"))
    assert result == "answer from model-b"


def test_advances_past_empty_answer(monkeypatch):
    async def fake_ask(messages, model_id, request_id, timeout):
        if model_id == "model-a":
            raise ValueError("Empty Gemini response with no blockReason")
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    result = run(fallback.get_answer([], "text", "req1"))
    assert result == "answer from model-b"


def test_advances_past_404(monkeypatch):
    """A 404 means the model id itself is gone (retired/paywalled free
    tier) — both clients put the model id in the request, never in
    anything else, so this can only be an advance-the-chain case."""
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        if model_id == "model-a":
            raise http_status_error(404)
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    result = run(fallback.get_answer([], "text", "req1"))
    assert result == "answer from model-b"
    assert calls == ["model-a", "model-b"]


def test_advances_across_providers_to_openrouter(monkeypatch):
    monkeypatch.setattr(fallback, "TEXT_FALLBACK_CHAIN", "google:model-b,openrouter:vendor/model-c:free")

    async def fake_ask_gemini(messages, model_id, request_id, timeout):
        raise http_status_error(429)

    async def fake_ask_openrouter(messages, model_id, request_id, timeout):
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(openrouter_client, "ask_openrouter", fake_ask_openrouter)

    result = run(fallback.get_answer([], "text", "req1"))
    assert result == "answer from vendor/model-c:free"


# ---------------------------------------------------------------- get_answer: fail fast

@pytest.mark.parametrize("code", [400, 401, 403])
def test_fail_fast_codes_stop_the_chain(monkeypatch, code):
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        raise http_status_error(code)

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    with pytest.raises(httpx.HTTPStatusError):
        run(fallback.get_answer([], "text", "req1"))

    assert calls == ["model-a"]   # never tried model-b or model-c


def test_content_blocked_stops_the_chain(monkeypatch):
    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        raise ContentBlocked("blocked: SAFETY")

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    with pytest.raises(ContentBlocked):
        run(fallback.get_answer([], "text", "req1"))

    assert calls == ["model-a"]


# ---------------------------------------------------------------- circuit breaker

def test_breaker_opens_after_threshold_and_is_skipped(monkeypatch):
    monkeypatch.setattr(config, "BREAKER_FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(config, "BREAKER_COOLDOWN_SECONDS", 60)

    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        if model_id == "model-a":
            raise http_status_error(429)
        return f"answer from {model_id}"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    # Three separate requests, each failing on model-a with a 429.
    for i in range(3):
        run(fallback.get_answer([], "text", f"req{i}"))

    assert calls.count("model-a") == 3
    assert circuit_breaker.is_cold("google:model-a") is True

    # A 4th request should skip model-a entirely — it never gets called.
    calls.clear()
    run(fallback.get_answer([], "text", "req4"))
    assert "model-a" not in calls
    assert calls == ["model-b"]


def test_breaker_closes_after_cooldown(monkeypatch):
    key = "google:model-x"
    for _ in range(config.BREAKER_FAILURE_THRESHOLD):
        circuit_breaker.record_failure(key, "req1")
    assert circuit_breaker.is_cold(key) is True

    # Simulate the cooldown having fully elapsed.
    future = time.monotonic() + config.BREAKER_COOLDOWN_SECONDS + 1
    monkeypatch.setattr(time, "monotonic", lambda: future)

    assert circuit_breaker.is_cold(key) is False


def test_breaker_success_resets_failure_count():
    key = "google:model-y"
    circuit_breaker.record_failure(key, "req1")
    circuit_breaker.record_failure(key, "req1")
    circuit_breaker.record_success(key)
    assert circuit_breaker._failures.get(key, 0) == 0
    assert circuit_breaker.is_cold(key) is False


# ---------------------------------------------------------------- budget exhaustion

def test_budget_exhausted_raises_without_any_call(monkeypatch):
    monkeypatch.setattr(fallback, "FALLBACK_TOTAL_BUDGET", -1)   # deadline already passed

    calls = []

    async def fake_ask(messages, model_id, request_id, timeout):
        calls.append(model_id)
        return "should never happen"

    monkeypatch.setattr(gemini_client, "ask_gemini", fake_ask)

    with pytest.raises(RuntimeError):
        run(fallback.get_answer([], "text", "req1"))

    assert calls == []


# ---------------------------------------------------------------- streaming

def test_stream_advances_past_failure_before_first_byte(monkeypatch):
    async def fake_stream_gemini(messages, model_id, request_id, timeout, state=None):
        if model_id == "model-a":
            raise http_status_error(429)
            yield  # pragma: no cover - unreachable, keeps this an async generator
        yield f"from {model_id}"

    monkeypatch.setattr(gemini_client, "stream_gemini", fake_stream_gemini)

    pieces = run(drain(fallback.stream_answer([], "text", "req1")))
    assert pieces == ["from model-b"]


def test_stream_mid_stream_failure_does_not_advance(monkeypatch):
    calls = []

    async def fake_stream_gemini(messages, model_id, request_id, timeout, state=None):
        calls.append(model_id)
        if model_id == "model-a":
            yield "partial answer "
            raise httpx.TimeoutException("dropped mid-stream")
        yield f"from {model_id}"

    monkeypatch.setattr(gemini_client, "stream_gemini", fake_stream_gemini)

    with pytest.raises(httpx.TimeoutException):
        run(drain(fallback.stream_answer([], "text", "req1")))

    # model-b must never have been tried — a piece was already sent to the
    # real client for model-a's attempt.
    assert calls == ["model-a"]


# ---------------------------------------------------------------- /health

def test_health_reports_degraded_flag_without_names():
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)

    circuit_breaker._cold_until.clear()
    body = client.get("/health").json()
    assert body["fallback_degraded"] is False

    circuit_breaker._cold_until["google:gemini-3.6-flash"] = time.monotonic() + 60
    body = client.get("/health").json()
    assert body["fallback_degraded"] is True
    assert "gemini" not in str(body).lower()
    assert "model" not in str(body).lower()

    circuit_breaker._cold_until.clear()
