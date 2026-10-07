# ConBOT 🤖

**A general-purpose AI assistant (conbot.in) — FastAPI backend, vanilla-JS frontend.**

ConBOT is a stateless chat assistant backed by a multi-provider text fallback chain (Google Gemini direct, with OpenRouter as cross-provider insurance) and Pollinations.ai for image generation. No database, no auth, no persisted conversation history — a production chat product focused on simplicity, resilience and privacy.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Deployment](#deployment)
- [Security](#security)
- [Project Structure](#project-structure)
- [Known Limitations & Roadmap](#known-limitations--roadmap)

---

## 🎯 Overview

- **Multi-provider text chat**: `PRIMARY_MODEL` (Gemini direct, free quota) is tried first; on failure it walks `TEXT_FALLBACK_CHAIN` across more Gemini models and OpenRouter — one paid cross-provider link plus free OpenRouter models as a last resort
- **Multi-language, location-aware**: responds in the user's language, using timezone for locale context
- **Image generation**: on-demand, via a separate `/generate-image` endpoint backed by Pollinations.ai
- **Rate limiting**: per-IP sliding window, per-IP daily cap, global daily cap, and a concurrent-stream ceiling — all in-memory, single instance
- **Streaming responses**: Server-Sent Events (SSE) for real-time answer generation
- **Safe errors & logs**: request-id log lines never contain question text; users only ever see safe, generic messages; upstream provider details never leak to the client

---

## ✨ Features

### Core Capabilities
- **Text Chat**: One mode, `text`. See [Text fallback chain](#configuration) for how `PRIMARY_MODEL` and `TEXT_FALLBACK_CHAIN` work together
- **Image Generation**: `/generate-image` calling Pollinations.ai, with a choice of models via `/models/image`
- **Intelligent Prompting**: custom system prompt with behavioral guidelines
- **Structured Responses**: automatic parsing of follow-up questions and clarification blocks out of the raw model output
- **Stateless Design**: no persistent conversation history — the client replays its own history each request
- **Multi-language Support**: responds in the user's language with localized context

### Technical Features
- **Server-Sent Events (SSE)**: real-time streaming for instant user feedback
- **Multi-provider fallback + circuit breaker**: a failed (provider, model) link is skipped cold for a cooldown window instead of being retried every request
- **Rate Limiting**: sliding-window + daily caps per client IP, a global daily cap, and a concurrent-`/stream` ceiling
- **Request Tracking**: UUID-based request IDs on every log line
- **Error Resilience**: upstream failures always map to a safe, generic client message
- **Security headers & body-size limits**: CSP/HSTS/nosniff on both the frontend (Cloudflare) and API, oversized request bodies rejected before parsing
- **CORS Support**: explicit origin allow-list, no wildcard, no credentials

---

## 🏗️ Architecture

```
                         User (browser)
                               │
                               ▼
                 Cloudflare Workers (static assets)
                    frontend/ — HTML, JS, CSS
                    CSP / HSTS via frontend/_headers
                               │
                               │ fetch() — separate origin
                               ▼
                    Render (Docker, single instance)
     ┌─────────────────────────────────────────────────────────┐
     │                FastAPI backend (app/)                   │
     │  CORS allow-list → MaxBodySize → SecurityHeaders         │
     │  Rate limiting (window + daily + concurrency)            │
     │                                                           │
     │  /ask, /stream ──────────► fallback.py (the only loop)   │
     │                              │  circuit-breaker aware     │
     │                              │                            │
     │                     ┌────────┴────────┐                  │
     │                     ▼                 ▼                  │
     │             Google Gemini       OpenRouter                │
     │             (direct, free)      (1 paid + 2 free)         │
     │             primary + 2         cross-provider            │
     │             fallbacks           insurance tier            │
     │                                                           │
     │  /generate-image ────────► Pollinations.ai (paid, own     │
     │                             account, separate budget)     │
     └─────────────────────────────────────────────────────────┘
```

No database, no file storage, no background jobs, no authentication — intentional for this MVP stage, not an oversight (see [Known Limitations](#known-limitations--roadmap)).

### Data Flow

1. **Request ingestion**: client calls `/ask` or `/stream` with `{prompt, model, history, ...}`
2. **Validation**: Pydantic field bounds, model allow-list check, then rate limiting — in that order, so an invalid request never costs quota
3. **Message assembly**: system prompt + trimmed history + current prompt
4. **Model dispatch**: `fallback.py` walks `PRIMARY_MODEL` then `TEXT_FALLBACK_CHAIN`, skipping any link the circuit breaker has marked cold, advancing past a 404/429/5xx/timeout/empty answer, failing fast on a 400/401/403 or content-policy block
5. **Post-processing**: strips `[[FOLLOWUPS]]`/`[[CLARIFY]]` blocks out of the raw text — the client never sees a raw tag
6. **Response**: streamed as SSE events, or returned whole from `/ask`

---

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI 0.133.1
- **Server**: Uvicorn 0.35.0
- **HTTP Client**: httpx 0.27.0
- **ASGI toolkit**: Starlette 1.3.1 (pinned explicitly — see [Security](#security))
- **Settings**: pydantic-settings 2.11.0
- **Language**: Python 3.12 (Docker); local dev needs 3.10+ (`python-dotenv` 1.2.2's floor)
- **Environment**: python-dotenv 1.2.2

### Frontend
- **Markup**: HTML5
- **Styling**: CSS3 with design tokens in `:root`, Geist font (Google Fonts), light/dark themes
- **Interactivity**: Vanilla JavaScript (no frameworks, no build step). Photo capture uses `getUserMedia`, which needs `localhost` or HTTPS

### Infrastructure
- **Containerization**: Docker, `python:3.12-slim`, non-root user
- **Hosting**: Render (backend), Cloudflare Workers static assets (frontend)

### External Services
- **Text**: Google Gemini API (direct), OpenRouter (fallback tier)
- **Image Generation**: Pollinations.ai

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ (3.12 recommended, matches the Docker image)
- Docker (optional, for a prod-parity run)
- A Gemini API key (Google AI Studio) — required
- An OpenRouter API key — optional, but needed if you keep the default `TEXT_FALLBACK_CHAIN` (it includes one paid OpenRouter link and two free ones)

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/Kumar6-Vinay/ConBot.git
cd ConBot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies (dev file adds pytest)
pip install -r requirements.txt -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add GEMINI_API_KEY at minimum, OPENROUTER_API_KEY if you keep the default fallback chain

# 5. Run the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Serve frontend (in another terminal)
python -m http.server 3000 --directory frontend
```

### Docker Deployment

```bash
# Build image
docker build -t conbot:latest .

# Run container
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your_key_here \
  -e OPENROUTER_API_KEY=your_key_here \
  conbot:latest
```

---

## ⚙️ Configuration

Environment variables (see `.env.example`):

```env
# Primary LLM model (provider:model_id format). Default: Gemini direct.
# Examples:
#   PRIMARY_MODEL=google:gemini-3.1-flash-lite (current default, free Google quota)
#   PRIMARY_MODEL=openrouter:qwen/qwen3.8-27b:free (free OpenRouter tier — no
#     SLA, slugs get retired/repriced without notice; don't use as primary)
# If format is "model_id" without provider prefix, "google" is assumed (legacy).
PRIMARY_MODEL=google:gemini-3.1-flash-lite

# Required for Gemini: Google AI Studio key.
# GOOGLE_API_KEY is read as a legacy alias if GEMINI_API_KEY is unset.
GEMINI_API_KEY=

# Required for OpenRouter models in PRIMARY_MODEL or TEXT_FALLBACK_CHAIN.
# Free models on OpenRouter require a key but may not charge. Get one at openrouter.ai/keys
OPENROUTER_API_KEY=

# Image generation (Pollinations.ai). Required for /generate-image; the
# rest of the app works without it. Own account/billing, separate from
# OpenRouter credit.
POLLINATIONS_API_KEY=
POLLINATIONS_MODEL=lykon/dreamshaper-8-lcm

# Conversation and output size
MAX_HISTORY_TURNS=8          # messages replayed to the model
MAX_HISTORY_CHARS=3000       # each replayed message is trimmed to this
MAX_OUTPUT_TOKENS=2000
MAX_IMAGE_MB=4                # ceiling for an image attached to a chat message

# Rate limits
RATE_LIMIT_MAX=20            # per IP, per window
RATE_LIMIT_WINDOW=600        # seconds
DAILY_PER_IP_LIMIT=15        # per IP, per UTC day
DAILY_REQUEST_LIMIT=45       # whole service, per UTC day (cost ceiling)
MAX_CONCURRENT_STREAMS=8     # in-flight /stream connections, across all clients
MAX_BODY_MB=8                # request bodies larger than this are rejected before parsing

# Client IP behind proxies (see "Client IP" below)
CLIENT_IP_HEADER=            # e.g. cf-connecting-ip, if your edge sets it
TRUSTED_PROXY_HOPS=1         # proxies that append to X-Forwarded-For

# CORS — comma-separated; replaces the built-in list when set
ALLOWED_ORIGINS=

FALLBACK_TIMEZONE=Asia/Kolkata

# Text fallback chain — tried in order, after PRIMARY_MODEL, whenever a
# link 404s (model gone/retired), 429s (quota), 5xx's, times out, or returns
# an empty answer. A 400/401/403 or a content-policy block fails immediately
# instead — a different model won't fix a malformed request or a bad key.
# "google:" calls Gemini directly; "openrouter:" calls OpenRouter (needs
# OPENROUTER_API_KEY). openai/gpt-5-mini is a cheap paid cross-provider link
# — insurance against a Google-wide outage, not expected to be hit often.
TEXT_FALLBACK_CHAIN=google:gemini-3.5-flash,google:gemini-3.8-flash,openrouter:openai/gpt-5-mini,openrouter:dots-studio/dots-3-note-preview:free,openrouter:nvidia/nemotron-3-ultra-550b-a55b:free
FALLBACK_ATTEMPT_TIMEOUT=10   # seconds per attempt
FALLBACK_TOTAL_BUDGET=45      # seconds, whole chain, worst case
BREAKER_FAILURE_THRESHOLD=3   # consecutive failures before a link goes cold
BREAKER_COOLDOWN_SECONDS=60   # how long a cold link is skipped entirely
```

### Text fallback chain

Google's Gemini free tier caps request volume per (key, model); once hit, it
returns 429 until the window resets. Rather than surface that to the user,
`/ask` and `/stream` walk an ordered chain of (provider, model) pairs — same
`{prompt, model}` request, same response shape, entirely invisible to the
frontend. Gemini direct leads the chain because it's free and has no
version-churn problem; a small paid OpenRouter link (`openai/gpt-5-mini`)
sits after it purely as cross-provider insurance against a Google-wide
outage, with free OpenRouter tiers as the very last resort. "Free" OpenRouter
models get retired or repriced without notice — a previous default,
`openrouter:qwen/qwen3.8-27b:free`, 404'd after being pulled from OpenRouter's
free tier, and `fallback.py` now treats a 404 as "this model id is gone,
advance" rather than failing the whole chain. Re-verify any `:free` slug
against OpenRouter's live catalog before relying on it — don't trust this
file's picks to still be current months later.

A circuit breaker (`app/core/circuit_breaker.py`) tracks failures per
(provider, model): after `BREAKER_FAILURE_THRESHOLD` consecutive failures, a
link is skipped entirely (not even attempted) for `BREAKER_COOLDOWN_SECONDS`,
so a request never pays the cost of rediscovering an already-broken link.
`GET /health`'s `fallback_degraded` field is `true` if anything is currently
cold — deliberately without naming which link, so an anonymous caller can't
use it to map out exactly where quota is exhausted.

To add or change fallback models: edit `TEXT_FALLBACK_CHAIN` — no code
change needed. Order matters: OpenRouter's free tier is more rate-limited
and queue-prone than a working Google model, so it belongs at the tail.

### Modes

The chat API (`/ask`, `/stream`) accepts `model: "text"` only, though every
current Gemini model is natively multimodal — a chat request can carry a
`prompt` plus an optional `image` (base64 data URL) in the same turn. Image
*generation* is a separate concern, served by `/generate-image` and backed by
Pollinations.ai rather than Gemini.

### Client IP

Rate limits key on the client address. Anything at the *left* of `X-Forwarded-For` is client-controlled, so ConBOT counts `TRUSTED_PROXY_HOPS` entries from the *right*. Before relying on it in production, log the raw header once on your host and confirm which entry is the visitor. If your edge sets a header it always overwrites (e.g. Cloudflare's `CF-Connecting-IP`), set `CLIENT_IP_HEADER` to it instead. If every visitor appears as the same address, all of them share one limit — check this first when users report unexpected 429s.

---

## 📡 API Endpoints

### `/health` (GET)
Health check — reports whether the service can actually answer, not just whether it booted.

**Response**:
```json
{
  "status": "healthy",
  "llm_configured": true,
  "fallback_degraded": false
}
```
`status` is `"degraded"` when `GEMINI_API_KEY` is missing. `fallback_degraded` is `true` if any link in the text fallback chain is currently cold — deliberately coarse, no model/provider name, so an anonymous caller can't map out exactly what's exhausted.

### `/ask` (POST)
Non-streaming endpoint for full responses.

**Request** (same body for `/stream`):
```json
{
  "prompt": "What's the weather like?",
  "model": "text",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "timezone": "Asia/Kolkata",
  "language": "en-IN"
}
```

Limits: `prompt` ≤ 3000 characters, `role` must be `user` or `assistant`. History is trimmed server-side to the last `MAX_HISTORY_TURNS` messages, each clipped to `MAX_HISTORY_CHARS` — long history is never rejected (a hard Pydantic ceiling further back, 50 turns / 20,000 characters per message, exists only to bound memory on a pathological request; the trim above is what actually shapes what the model sees).

**Response**:
```json
{
  "answer": "To help you best, I need to know which state you're asking about...",
  "web_used": false,
  "sources": [],
  "followups": ["What is the tax regime for individuals?"],
  "clarify": {"question": "Which tax regime?", "options": ["Old regime", "New regime"]}
}
```

`answer` never contains the raw `[[FOLLOWUPS]]` / `[[CLARIFY]]` blocks. When the model needs one detail first, `clarify` is `{"question": ..., "options": [...]}` and `answer` holds the question. `web_used` and `sources` are always `false`/`[]` — there is no web search in the current build.

### `/stream` (POST)
Streaming endpoint using Server-Sent Events (SSE).

**Response Stream Events**:
```
data: {"type": "delta", "text": "partial response text"}
data: {"type": "clarify", "question": "...", "options": [...]}   # instead of deltas
data: {"type": "followups", "questions": [...]}
data: {"type": "truncated"}                                       # hit MAX_OUTPUT_TOKENS
data: {"type": "error", "detail": "safe message"}
data: {"type": "done"}
```

Errors before the stream starts are normal HTTP errors: `400` bad model, `413` body too large, `422` invalid body (`detail` is a list), `429` rate limited, `503` not configured. Once the stream has started, every error — including a mid-chain provider failure — arrives as an SSE `error` event instead, since the HTTP status is already committed to `200`.

### `/generate-image` (POST)
Generates an image via Pollinations.ai.

**Request**:
```json
{
  "prompt": "a cat astronaut",
  "model": "lykon/dreamshaper-8-lcm",
  "width": 1024,
  "height": 1024,
  "seed": null
}
```
Limits: `prompt` ≤ 1000 characters, `width`/`height` 512–2048, `seed` (if given) 0 to 2³²−1. `model` must be one of the ids from `/models/image`.

**Response**:
```json
{
  "url": "data:image/jpeg;base64,...",
  "prompt": "a cat astronaut",
  "model": "lykon/dreamshaper-8-lcm",
  "width": 1024,
  "height": 1024,
  "cost": 0.0001
}
```
The image is returned inline as a base64 data URL — the Pollinations key stays server-side and is never exposed to the client. This endpoint shares the same rate limiter as `/ask` and `/stream` (it is not a separate, unprotected cost surface). Errors: `400` bad prompt/model/dimensions or generation not configured, `502` upstream generation failure.

### `/models/image` (GET)
Lists the image generation models available to `/generate-image`, each with a display name and per-generation cost in USD.

---

## 🔧 Development

### Testing

```bash
# Unit/regression tests (no API key, no network)
pytest -q

# Test endpoints locally
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?"}'

# Test streaming
curl -sN -X POST http://localhost:8000/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke"}'

# Test image generation (costs real Pollinations credit)
curl -s -X POST http://localhost:8000/generate-image \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat astronaut"}'
```

### Code Organization

The backend is a package (`app/`), not a single file. Route handlers in
`app/api/routes/` are thin — they call into `app/services/` (business logic,
no FastAPI imports), `app/core/` (rate limiting, circuit breaker, middleware,
security helpers), and `app/api/deps.py` (the shared `/ask` + `/stream`
pipeline: `prepare()`, model validation, fallback chain dispatch). Callers
import these as modules (`from app.services import conversation`) rather than
importing bare functions, so tests can monkeypatch them at the module level —
patching a bare imported name silently does nothing.

Image generation (`app/services/image_generation.py`) is a self-contained
Pollinations.ai client with its own env var reads, used only by
`app/api/routes/image.py`.

---

## 🌐 Deployment

### Environment Considerations

Development and production both run the same backend code against the same two text providers (Gemini direct, OpenRouter). There is no local-model fallback and no dev/prod code branching — only configuration differs.

### Deployment Platforms

- **Backend — Render** (current): Git-connected Docker deployment, reads the repo-root `Dockerfile`. Rate limits and the circuit breaker are in-memory, so this must run as a single instance — confirm autoscaling is off for this service
- **Frontend — Cloudflare Workers (static assets)** (current): `frontend/` served as static assets via a Worker, configured by `wrangler.json` (`assets.directory`), not classic Cloudflare Pages — Cloudflare's newer unified "Workers & Pages" onboarding defaults to a Worker/`wrangler deploy` project. Git-connected (Cloudflare's GitHub App supports private repos, unlike GitHub Pages on the free plan), custom domain `conbot.in`
- **Docker**: any container runtime, for the backend

### CORS Configuration

Built-in origins:
- Local development: `localhost:3000`, `localhost:3001` (and `127.0.0.1` equivalents)
- Production: `conbot.in`, `www.conbot.in`
- Render frontend: `llama-chatbot-fe.onrender.com`

Set `ALLOWED_ORIGINS` (comma-separated) to replace this list without editing code — needed for the Cloudflare Workers preview URL (`*.workers.dev`) if you test against the live backend from there before DNS cutover.

---

## 🔒 Security

A full audit lives in [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) — read it for the detailed findings and severity ranking. In short, as of the last pass:

- **Secrets**: `.env` has never been committed (verified against full git history), no key-shaped strings anywhere in tracked files or history
- **CORS**: explicit allow-list, `allow_credentials=False`, no wildcard
- **Rate limiting**: sliding window + per-IP daily + global daily + concurrent-stream cap, shared by every AI-costing endpoint including `/generate-image`
- **Input validation**: Pydantic field bounds everywhere, strict base64/MIME allow-list for uploaded images, request bodies rejected by `Content-Length` before they're parsed
- **XSS**: model output and user text are never passed to `innerHTML`; both go through `markdown()` (escapes first) or `textContent`
- **Headers**: CSP/HSTS/`X-Content-Type-Options`/`Referrer-Policy` on both the frontend (`frontend/_headers`) and the API (`SecurityHeadersMiddleware`)
- **Logging**: request-ID-tagged; question text is never logged, only a hash + length
- **Container**: non-root user, pinned base image, dev tooling never baked in
- **Dependencies**: pinned direct deps, checked against OSV.dev's live vulnerability database — `starlette` is pinned explicitly (not left to float transitively) after a prior CVE was found unpatched

Report a vulnerability by opening a private disclosure rather than a public issue if it's exploitable in the live deployment.

---

## 📂 Project Structure
```
ConBot/
├── app/                           # Backend package
│   ├── main.py                    # FastAPI app creation, lifespan, CORS, middleware, routers
│   ├── config.py                  # Settings from env vars (pydantic-settings)
│   ├── logging_config.py          # Structured logger setup
│   ├── api/
│   │   ├── deps.py                 # Shared pipeline: prepare(), validate_model(), fallback dispatch
│   │   └── routes/
│   │       ├── health.py           # GET /health
│   │       ├── ask.py              # POST /ask
│   │       ├── stream.py           # POST /stream
│   │       └── image.py            # POST /generate-image, GET /models/image
│   ├── services/                   # Business logic, no FastAPI imports
│   │   ├── gemini_client.py        # One Gemini attempt
│   │   ├── openrouter_client.py    # One OpenRouter attempt, mirrors gemini_client.py
│   │   ├── fallback.py             # Walks TEXT_FALLBACK_CHAIN — the only place that loops
│   │   ├── image_generation.py     # Pollinations.ai client
│   │   └── conversation.py         # System prompt, BlockFilter, message assembly
│   ├── models/                     # Pydantic request/response schemas
│   │   ├── ask.py                  # Turn, ChatRequest
│   │   └── image.py                # ImageGenerationRequest/Response
│   └── core/
│       ├── rate_limit.py           # In-memory rate limiting + concurrency cap
│       ├── circuit_breaker.py      # Cold-skips a failing (provider, model) pair
│       ├── middleware.py           # MaxBodySizeMiddleware, SecurityHeadersMiddleware
│       ├── security.py             # validate_image(), clip()
│       └── errors.py               # no_llm_error(), ContentBlocked
├── requirements.txt                # Python dependencies
├── requirements-dev.txt            # Test-only dependencies (pytest)
├── tests/
│   ├── test_main.py                # Chat/stream regression tests, no network needed
│   ├── test_fallback.py            # Fallback chain advance/fail-fast/breaker/budget tests
│   └── test_image_generation.py    # Image generation regression tests, no network needed
├── Dockerfile                      # Container configuration (backend)
├── wrangler.json                   # Cloudflare Workers config (serves frontend/ as static assets)
├── .env.example                    # Environment template
├── .gitignore
├── SECURITY_AUDIT.md                # Security findings and fix status
├── README.md                        # This file
└── frontend/
    ├── index.html                  # Web interface
    ├── app.js                      # Client-side logic
    ├── styles.css                  # Styling and design tokens
    ├── favicon.svg
    └── _headers                     # Cloudflare header rules (CSP, HSTS)
```

---

## 📝 Known Limitations & Roadmap

Honest gaps, not aspirational filler — see `SECURITY_AUDIT.md` for the full severity-ranked list this is drawn from.

**Accepted for this MVP stage, by design:**
- No database, no persisted conversation history, no authentication
- No CI/CD — `pytest -q` is run manually before every change
- Single-instance deployment required (in-memory rate limiting / circuit breaker state)
- Image editing isn't implemented — `/generate-image` only generates from a text prompt

**Worth doing as traffic grows:**
- A GitHub Actions workflow that runs `pytest -q` on push — cheapest possible CI, currently nonexistent
- A dependency lockfile (`pip-compile` or similar) — transitive versions currently drift silently between rebuilds, which is exactly how an unpinned `starlette` CVE went unnoticed before
- Real observability — logs exist and are structured, but nothing is aggregated (no APM, no per-model cost/latency dashboard, no error tracker)
- A public privacy policy page — the technical practice is already good (nothing is persisted), it just isn't written down anywhere a visitor can read

---

## 📄 License

Unlicensed — no license file is currently present in this repository. Treat the code as all-rights-reserved until one is added.

---

## 👨‍💻 Author

**Kumar Vinay** - [@Kumar6-Vinay](https://github.com/Kumar6-Vinay)

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Run `pytest -q` and the manual verification commands in [Testing](#development) before opening a PR — there is no CI to catch a regression for you yet.

---

## 🆘 Support & Issues

For bugs, feature requests, or questions, open an [Issue](https://github.com/Kumar6-Vinay/ConBot/issues).

---

## 🔗 Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Gemini API](https://ai.google.dev/gemini-api/docs)
- [OpenRouter](https://openrouter.ai/docs) — model catalog, pricing, API reference
- [Pollinations.ai](https://pollinations.ai/)

---

**Last Updated**: October 7, 2026
**Version**: 1.2.0 — Multi-provider text fallback chain (Gemini + OpenRouter), hardened dependencies, stateless by design
