"""Configuration from environment variables.

Raw env reads go through `_Env` (pydantic-settings) for typed parsing;
everything derived from them stays plain module-level code, exactly like the
original single-file main.py, so callers (and tests) can keep reading/
patching these as ordinary module attributes.
"""
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class _Env(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    GEMINI_TEXT_MODEL: str = "gemini-3.6-flash"
    TEXT_FALLBACK_CHAIN: str = (
        "google:gemini-3.5-flash,google:gemini-3.8-flash,google:gemini-3.1-flash-lite,"
        "openrouter:nex-agi/nex-n2.5-mini:free,openrouter:dots-studio/dots-3-note-preview:free,"
        "openrouter:nvidia/nemotron-3-super-120b-a12b:free"
    )
    FALLBACK_ATTEMPT_TIMEOUT: int = 10
    FALLBACK_TOTAL_BUDGET: int = 45
    BREAKER_FAILURE_THRESHOLD: int = 3
    BREAKER_COOLDOWN_SECONDS: int = 60
    BRAVE_SEARCH_API_KEY: str = ""
    RATE_LIMIT_MAX: int = 20
    RATE_LIMIT_WINDOW: int = 600
    DAILY_REQUEST_LIMIT: int = 45
    DAILY_PER_IP_LIMIT: int = 15
    MAX_CONCURRENT_STREAMS: int = 8
    CLIENT_IP_HEADER: str = ""
    TRUSTED_PROXY_HOPS: int = 1
    ALLOWED_ORIGINS: str = ""
    MAX_IMAGE_MB: float = 4
    MAX_BODY_MB: float = 8
    MAX_HISTORY_TURNS: int = 8
    MAX_HISTORY_CHARS: int = 3000
    FALLBACK_TIMEZONE: str = "Asia/Kolkata"
    MAX_OUTPUT_TOKENS: int = 2000
    GEMINI_TIMEOUT: int = 60


_env = _Env()

DEFAULT_MODEL = "text"

AVAILABLE_MODELS = {
    "text",
}

# Google's Gemini API (AI Studio key). This is the only LLM backend now —
# calls go straight to Google, no router in between.
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _clean_key(raw: str) -> str:
    """Tolerate a key pasted with surrounding whitespace or quotes."""
    return raw.strip().strip('"').strip("'").strip()


# GEMINI_API_KEY is the new name; fall back to the old GOOGLE var so an
# existing deployment keeps working until the env is renamed. OPENROUTER_API_KEY
# is deliberately NOT part of this chain — it's a different provider entirely
# (openrouter.ai, OpenAI-compatible schema, Bearer auth), and folding it in
# here would send an OpenRouter key to Google's endpoint and 401 the moment
# GEMINI_API_KEY was ever unset.
GEMINI_API_KEY = _clean_key(_env.GEMINI_API_KEY or _env.GOOGLE_API_KEY)
OPENROUTER_API_KEY = _clean_key(_env.OPENROUTER_API_KEY)
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# ConBOT mode -> Gemini model id. gemini-2.5-flash is the stable free alias;
# note it is scheduled to retire in Oct 2026 — bump this env var to
# gemini-3.6-flash (or the current flash) when that happens.
GEMINI_MODEL_MAP = {
    "text": _env.GEMINI_TEXT_MODEL,
}

# On a 429/5xx/timeout/empty-answer for the primary model, retry with the
# next (provider, model) pair here before giving up — still the same "text"
# mode as far as the client and rate limits are concerned, just a different
# backend answering. "google:<id>" calls Gemini directly; "openrouter:<id>"
# calls OpenRouter. No model id is hardcoded anywhere else — this string is
# the only place the fallback chain is defined. See app/services/fallback.py
# for how it's parsed and walked.
TEXT_FALLBACK_CHAIN = _env.TEXT_FALLBACK_CHAIN

# Per-attempt timeout (seconds). For a streaming call this bounds time
# between chunks, not total answer length, so a long-but-flowing answer is
# never cut short — it only ever fires on a stalled/slow-to-start attempt,
# which is exactly what should trigger moving to the next link.
FALLBACK_ATTEMPT_TIMEOUT = _env.FALLBACK_ATTEMPT_TIMEOUT

# Hard wall-clock ceiling for the whole chain, checked before every attempt
# rather than left as (links x per-attempt timeout) — stays correct even if
# the chain above grows later. Comfortably under the client's own 120s abort
# (TIMEOUT_MS in frontend/app.js).
FALLBACK_TOTAL_BUDGET = _env.FALLBACK_TOTAL_BUDGET

# Circuit breaker: after this many consecutive failures, a (provider, model)
# pair is treated as cold and skipped entirely (not even attempted) until
# the cooldown elapses. See app/core/circuit_breaker.py.
BREAKER_FAILURE_THRESHOLD = _env.BREAKER_FAILURE_THRESHOLD
BREAKER_COOLDOWN_SECONDS = _env.BREAKER_COOLDOWN_SECONDS


def model_supports_vision(mode: str) -> bool:
    """Every current Gemini flash/pro model is natively multimodal, so any
    mode we serve can read an image. Kept as a function for parity with the
    old code."""
    return True


# DuckDuckGo Instant Answer API — free, keyless, but it returns encyclopedia
# abstracts, not live results. It is the fallback only.
DUCKDUCKGO_URL = "https://api.duckduckgo.com/"

# Optional real web search (Brave Search API). Off unless a key is set.
# Setting a key changes cost per request — check Brave's current pricing.
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_SEARCH_API_KEY = _env.BRAVE_SEARCH_API_KEY.strip()

# Weather APIs (Open-Meteo - free, no API key)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Timeouts (in seconds)
SEARCH_TIMEOUT = 10


# =========================================================
# RATE LIMITING
#
# /ask and /stream are public and unauthenticated, and each request costs
# real Gemini credit. Without a limit, one script in a browser console can
# drain the key. This is a fixed-window counter per client IP, held in
# memory — no extra service, no extra dependency. It resets if the process
# restarts, and it is per-instance if this ever runs on more than one, which
# is the honest limit of "no infrastructure" rate limiting. It stops a
# casual script; it is not a defense against a determined, distributed abuser.
# =========================================================

RATE_LIMIT_MAX = _env.RATE_LIMIT_MAX        # requests
RATE_LIMIT_WINDOW = _env.RATE_LIMIT_WINDOW  # seconds (10 min)

# Global daily cap = the prototype's cost ceiling. The per-IP daily cap stops
# one visitor from spending the whole day's allowance for everyone.
DAILY_REQUEST_LIMIT = _env.DAILY_REQUEST_LIMIT
DAILY_PER_IP_LIMIT = _env.DAILY_PER_IP_LIMIT

# The window/daily caps above limit how often a client can START a stream,
# not how many it can hold open at once — a handful of IPs each opening
# several long-lived /stream connections within their own quota can still
# pin down that many concurrent Gemini calls and server tasks at the same
# time. This bounds total in-flight streams regardless of who opened them.
MAX_CONCURRENT_STREAMS = _env.MAX_CONCURRENT_STREAMS

# How the client address is found behind proxies.
#  - CLIENT_IP_HEADER: a header your edge overwrites (never passes through),
#    e.g. "cf-connecting-ip" behind Cloudflare. Takes priority when set.
#  - TRUSTED_PROXY_HOPS: otherwise, how many proxies append to
#    X-Forwarded-For. The client can put anything at the LEFT of that header,
#    so we count from the RIGHT. Verify on your host: log the header once.
CLIENT_IP_HEADER = _env.CLIENT_IP_HEADER.strip().lower()
TRUSTED_PROXY_HOPS = max(0, _env.TRUSTED_PROXY_HOPS)


# =========================================================
# CORS (FIXED FOR FRONTEND)
# =========================================================

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://conbot.in",
    "https://www.conbot.in",
    "https://llama-chatbot-fe.onrender.com",
    "https://kumar6-vinay.github.io",
]

# Comma-separated override, e.g. to add a GitHub Pages origin
# (https://<username>.github.io — CORS matches the origin, not the path).
ALLOWED_ORIGINS = [
    o.strip() for o in _env.ALLOWED_ORIGINS.split(",") if o.strip()
] or DEFAULT_ORIGINS


# =========================================================
# REQUEST LIMITS
# =========================================================

MAX_PROMPT_CHARS = 3000

# Image input. The client sends a base64 data URL; the ceiling is on the
# encoded string, which is ~33% larger than the raw file. 4 MB of file is
# ~5.5 MB of base64, so allow a little headroom.
MAX_IMAGE_MB = _env.MAX_IMAGE_MB
MAX_IMAGE_CHARS = int(MAX_IMAGE_MB * 1024 * 1024 * 4 / 3) + 2048

# Largest request body we'll fully read and JSON-parse, checked by
# Content-Length before FastAPI/Pydantic ever touch the body — those only
# reject an oversized field *after* the whole body is buffered and parsed,
# which is too late to protect memory/CPU. Sized with headroom above the
# largest legitimate body (image + full history + prompt, ~6.5 MB).
MAX_BODY_MB = _env.MAX_BODY_MB
MAX_BODY_BYTES = int(MAX_BODY_MB * 1024 * 1024)

# How much conversation to carry, and how much of each message. These cap
# cost and latency. The server TRIMS to them; it does not reject — a long
# answer must never break the next question.
MAX_HISTORY_TURNS = _env.MAX_HISTORY_TURNS
MAX_HISTORY_CHARS = _env.MAX_HISTORY_CHARS

# Hard ceilings that only stop abusive payloads, well above anything the
# client sends after its own trimming.
HISTORY_ITEM_CEILING = 20000
HISTORY_LEN_CEILING = 50

# Used when the browser sends nothing at all.
FALLBACK_TIMEZONE = _env.FALLBACK_TIMEZONE

# Devanagari and other non-Latin scripts tokenize far less efficiently than
# English. A cap tuned for English silently truncates Hindi mid-sentence.
MAX_OUTPUT_TOKENS = _env.MAX_OUTPUT_TOKENS

GEMINI_TIMEOUT = _env.GEMINI_TIMEOUT
