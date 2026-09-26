# ConBOT 🤖

**A general-purpose AI assistant (conbot.in) — FastAPI backend, vanilla-JS frontend.**

ConBOT is a stateless chat assistant powered by Google's Gemini API. It generates images via Pollinations.ai, supports multiple languages, and operates without persistent conversation history. A production chat product focused on simplicity and privacy.

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
- [Project Structure](#project-structure)

---

## 🎯 Overview

ConBOT is an intelligent conversational platform designed for:

- **Multi-language Support**: Responds in the user's language with localized information
- **Location Awareness**: Provides location-specific answers based on timezone and regional settings
- **LLM Backend**: Google's Gemini API (multimodal — text and image input in the same chat)
- **Image Generation**: On-demand image generation via Pollinations.ai
- **Rate Limiting**: Per-IP window and daily caps, plus a global daily cost cap (in-memory, single instance)
- **Streaming Responses**: Server-sent events (SSE) for real-time answer generation
- **Safe errors & logs**: Request-id log lines without question text; users only ever see safe messages

---

## ✨ Features

### Core Capabilities
- **Text Chat**: One mode, `text`. `PRIMARY_MODEL` (`provider:model_id`, default OpenRouter's Qwen free tier) is tried first, then `TEXT_FALLBACK_CHAIN` across Google and OpenRouter models
- **Image Generation**: A separate `/generate-image` endpoint calling Pollinations.ai, with a choice of models via `/models/image`
- **Intelligent Prompting**: Custom system prompts with behavioral guidelines
- **Structured Responses**: Automatic parsing of follow-up questions and clarification blocks
- **Stateless Design**: No persistent conversation history; each session is independent
- **Multi-language Support**: Responds in the user's language with localized context

### Technical Features
- **Server-Sent Events (SSE)**: Real-time streaming for instant user feedback
- **Rate Limiting**: Sliding-window + daily caps per client IP, and a global daily cap
- **Request Tracking**: UUID-based request IDs for comprehensive logging
- **Error Resilience**: Detailed error handling with meaningful user messages
- **CORS Support**: Pre-configured for multiple frontend origins

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Web)                          │
│              (HTML, JavaScript, CSS)                         │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/SSE
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              ConBOT FastAPI Backend                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ API Endpoints (/ask, /stream, /health,               │   │
│  │                /generate-image, /models/image)       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Request Processing & Validation                      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Message Processing & Validation                       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Rate Limiting & Security                             │   │
│  └──────────────────────────────────────────────────────┘   │
└────────┬─────────────────────────────────────────┬───────────┘
         │                                         │
         ▼ Chat (/ask, /stream)         ▼ Image generation (/generate-image)
    ┌─────────────┐               ┌──────────────┐
    │ Google      │               │ Pollinations │
    │ Gemini API  │               │    .ai API   │
    └─────────────┘               └──────────────┘
```

### Data Flow

1. **Request Ingestion**: User submits prompt via `/ask` or `/stream` endpoint
2. **Validation**: Input validation and rate limiting enforcement
3. **Message Assembly**: Constructs system prompt and message history from request
4. **LLM Invocation**: Sends prompt to Google's Gemini API
5. **Post-Processing**: Parses structured blocks (clarifications, follow-ups)
6. **Response**: Streams or returns complete answer with metadata

---

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI 0.116.1
- **Server**: Uvicorn 0.35.0
- **HTTP Client**: httpx 0.27.0
- **Language**: Python 3.12
- **Environment**: python-dotenv 1.0.1

### Frontend
- **Markup**: HTML5
- **Styling**: CSS3 with design tokens in `:root`, Geist font (Google Fonts), light/dark themes
- **Interactivity**: Vanilla JavaScript (no frameworks, no build step). Photo capture uses `getUserMedia`, which needs `localhost` or HTTPS

### Infrastructure
- **Containerization**: Docker
- **Runtime**: Python 3.12-slim
- **Security**: Non-root user execution

### External Services
- **LLM**: Google Gemini API
- **Image Generation**: Pollinations.ai

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (optional)
- Gemini API Key (Google AI Studio)

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
# Edit .env and add your Gemini API key

# 5. Run the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Serve frontend (in another terminal)
# Use any static server, e.g.:
python -m http.server 3000 --directory frontend
```

### Docker Deployment

```bash
# Build image
docker build -t conbot:latest .

# Run container
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your_key_here \
  conbot:latest
```

---

## ⚙️ Configuration

Environment variables (see `.env.example`):

```env
# Primary LLM model (provider:model_id format). Default: OpenRouter's free Qwen.
# Examples:
#   PRIMARY_MODEL=openrouter:qwen/qwen3.8-27b:free (current default, free)
#   PRIMARY_MODEL=google:gemini-3.5-flash (requires GEMINI_API_KEY)
# If format is "model_id" without provider prefix, "google" is assumed (legacy).
PRIMARY_MODEL=openrouter:qwen/qwen3.8-27b:free

# Required for Gemini: Google AI Studio key.
# GOOGLE_API_KEY is read as a legacy alias if GEMINI_API_KEY is unset.
GEMINI_API_KEY=

# Required for OpenRouter models in PRIMARY_MODEL or TEXT_FALLBACK_CHAIN.
# Free models on OpenRouter require a key but may not charge. Get one at openrouter.ai/keys
OPENROUTER_API_KEY=

# Image generation (Pollinations.ai). Required for /generate-image; the
# rest of the app works without it.
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

# Client IP behind proxies (see "Client IP" below)
CLIENT_IP_HEADER=            # e.g. cf-connecting-ip, if your edge sets it
TRUSTED_PROXY_HOPS=1         # proxies that append to X-Forwarded-For

# CORS — comma-separated; replaces the built-in list when set
ALLOWED_ORIGINS=

FALLBACK_TIMEZONE=Asia/Kolkata

# Text fallback chain — tried in order, after PRIMARY_MODEL, whenever a
# link 429s (quota), 5xx's, times out, or returns an empty answer. A 400/401/
# 403/404 or a content-policy block fails immediately instead — a different
# model won't fix a bad request or a bad key. "google:" calls Gemini
# directly; "openrouter:" calls OpenRouter (needs OPENROUTER_API_KEY).
TEXT_FALLBACK_CHAIN=google:gemini-3.5-flash,google:gemini-3.8-flash,google:gemini-3.1-flash-lite,openrouter:nex-agi/nex-n2.5-mini:free,openrouter:dots-studio/dots-3-note-preview:free,openrouter:nvidia/nemotron-3-ultra-550b-a55b:free
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
frontend. The default chain's picks were chosen live (not from memory) by
probing OpenRouter's free-tier models and Google's own model list with the
project's actual keys — most "free" OpenRouter models turned out to be
unreliable (provider capacity errors, agentic-harness-only access, or
`content: null` responses hiding a token-burning reasoning trace); only the
three in the default chain survived a 3-prompt smoke test cleanly.

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
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "llm_configured": true,
  "model": "gemini-3.6-flash"
}
```
`status` is `"degraded"` when `GEMINI_API_KEY` is missing.

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

Limits: `prompt` ≤ 3000 characters. History is trimmed server-side to the last `MAX_HISTORY_TURNS` messages, each clipped to `MAX_HISTORY_CHARS` — long history is never rejected.

**Response**:
```json
{
  "answer": "To help you best, I need to know which state you're asking about...",
  "followups": ["What is the tax regime for individuals?"],
  "clarify": {"question": "Which tax regime?", "options": ["Old regime", "New regime"]}
}
```

`answer` never contains the raw `[[FOLLOWUPS]]` / `[[CLARIFY]]` blocks. When the model needs one detail first, `clarify` is `{"question": ..., "options": [...]}` and `answer` holds the question. `sources` is always an empty array (no web search).

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

Errors before the stream starts are normal HTTP errors: `400` bad model, `422` invalid body (`detail` is a list), `429` rate limited, `503` not configured.

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
Limits: `prompt` ≤ 1000 characters, `width`/`height` 512–2048. `model` must be one of the ids from `/models/image`.

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
The image is returned inline as a base64 data URL — the Pollinations key stays server-side and is never exposed to the client. Errors: `400` bad prompt/model/dimensions or generation not configured, `502` upstream generation failure.

### `/models/image` (GET)
Lists the image generation models available to `/generate-image`, each with a display name and per-generation cost in USD.

---

## 🔧 Development

### Project Structure
```
ConBot/
├── app/                          # Backend package
│   ├── main.py                   # FastAPI app creation, lifespan, CORS, routers
│   ├── config.py                 # Settings from env vars (pydantic-settings)
│   ├── logging_config.py         # Structured logger setup
│   ├── api/
│   │   ├── deps.py                # Shared pipeline: prepare(), Gemini dispatch
│   │   └── routes/
│   │       ├── health.py          # GET /health
│   │       ├── ask.py             # POST /ask
│   │       ├── stream.py          # POST /stream
│   │       └── image.py           # POST /generate-image, GET /models/image
│   ├── services/                  # Business logic, no FastAPI imports
│   │   ├── gemini_client.py       # Gemini API calls
│   │   ├── image_generation.py    # Pollinations.ai client
│   │   ├── fallback.py            # Multi-provider fallback chain
│   │   ├── openrouter_client.py   # OpenRouter API calls
│   │   └── conversation.py        # System prompt, BlockFilter, message assembly
│   ├── models/                    # Pydantic request/response schemas
│   │   ├── ask.py
│   │   └── image.py
│   └── core/
│       ├── errors.py              # no_llm_error()
│       ├── rate_limit.py          # In-memory rate limiting
│       └── security.py            # validate_image(), clip()
├── requirements.txt              # Python dependencies
├── requirements-dev.txt          # Test-only dependencies (pytest)
├── tests/
│   ├── test_main.py              # Chat/stream regression tests, no network needed
│   ├── test_fallback.py          # Fallback chain, breaker and budget tests
│   └── test_image_generation.py  # Image generation regression tests, no network needed
├── Dockerfile                    # Container configuration (backend)
├── wrangler.json                 # Cloudflare Workers config (serves frontend/ as static assets)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── README.md                     # This file
└── frontend/
    ├── index.html               # Web interface
    ├── app.js                   # Client-side logic
    ├── styles.css               # Styling and design tokens
    ├── favicon.svg
    └── _headers                 # Cloudflare header rules (CSP, HSTS)
```

### Code Organization

The backend is a package (`app/`), not a single file. Route handlers in
`app/api/routes/` are thin — they call into `app/services/` (business logic,
no FastAPI imports), `app/core/` (rate limiting, errors, security), and
`app/api/deps.py` (the shared `/ask` + `/stream` pipeline: `prepare()`,
model validation, fallback chain dispatch). Callers import these as modules
(`from app.services import conversation`) rather than importing bare
functions, so tests can monkeypatch them at the module level.

Image generation (`app/services/image_generation.py`) is a self-contained
Pollinations.ai client with its own env var reads, used only by
`app/api/routes/image.py`.

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

# Test image generation
curl -s -X POST http://localhost:8000/generate-image \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat astronaut"}'
```

---

## 🌐 Deployment

### Environment Considerations

Both development and production use the same backend: Google's Gemini API, configured with `GEMINI_API_KEY`. There is no local-model fallback.

### Deployment Platforms

- **Backend — Render** (current): Git-connected Docker deployment. Rate limits are in-memory, so run one instance
- **Frontend — Cloudflare Workers (static assets)** (current): `frontend/` served as static assets via a Worker, configured by `wrangler.json` (`assets.directory`), not classic Cloudflare Pages — Cloudflare's newer unified "Workers & Pages" onboarding defaults to a Worker/`wrangler deploy` project. Git-connected (Cloudflare's GitHub App supports private repos, unlike GitHub Pages on the free plan), custom domain `conbot.in`
- **Docker**: Any container runtime, for the backend

### CORS Configuration

Built-in origins:
- Local development: `localhost:3000`, `localhost:3001`
- Production: `conbot.in`, `www.conbot.in`
- Render frontend: `llama-chatbot-fe.onrender.com`

Set `ALLOWED_ORIGINS` (comma-separated) to replace this list without editing code — needed for the Cloudflare Workers preview URL (`*.workers.dev`) if you test against the live backend from there before DNS cutover.

---

## 📊 Industry Best Practices Assessment

### ✅ Implemented Best Practices

1. **Code Organization**
   - Clear section headers for logical separation
   - Single-responsibility functions
   - Consistent naming conventions

2. **Security**
   - Non-root Docker user (appuser)
   - Input validation with Pydantic
   - Rate limiting to prevent abuse
   - Environment variable separation from code

3. **Error Handling**
   - Upstream errors mapped to safe, generic messages
   - Meaningful error messages
   - Comprehensive exception handling
   - Request-scoped error tracking

4. **Logging**
   - Structured logging with request IDs
   - Multiple log levels (INFO, WARNING, ERROR)
   - Request tracking throughout lifecycle

5. **API Design**
   - RESTful endpoints
   - Streaming support for real-time UX
   - Health check endpoint
   - Clear request/response schemas

6. **Configuration Management**
   - Environment-based configuration
   - Sensible defaults
   - `.env.example` for documentation
   - Proper `.gitignore`

7. **Containerization**
   - Multi-stage optimization (slim base)
   - Layer caching optimization
   - Non-root user execution
   - Proper file permissions

### ⚠️ Areas for Improvement

1. **Testing**
   - Regression suite in `tests/` (pytest); not yet run in CI

2. **Documentation**
   - API documentation could be richer

3. **Monitoring**
   - No metrics/observability setup
   - Consider: Prometheus, Sentry, New Relic integration

4. **CI/CD**
   - No GitHub Actions workflows — frontend deploys via Cloudflare's own Git integration, backend via Render's
   - Missing: linting, automated testing on push
   - Should add: Black, Flake8, a test-on-push workflow

5. **Database**
   - No persistent storage for conversations
   - Consider: PostgreSQL for chat history if needed

6. **Frontend**
   - Vanilla JS without build tooling
   - Consider: React/Vue for larger frontend

---

## 📝 Recommended Improvements

### Immediate (Week 1)
```bash
# Add type hints and docstrings
# Setup pre-commit hooks (black, flake8, mypy)
# Add pytest configuration
```

### Short-term (Month 1)
```
- Run the test suite in CI
- Setup CI/CD pipeline with GitHub Actions
- Add API documentation (FastAPI Swagger)
```

### Long-term (Quarter 1)
```
- Add conversation database
- Implement user authentication
- Add metrics/monitoring
- Implement caching layer
```

---

## 📄 License

Unlicensed (No license specified - consider adding MIT/Apache 2.0)

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

---

## 🆘 Support & Issues

For bugs, feature requests, or questions:
- Open an [Issue](https://github.com/Kumar6-Vinay/ConBot/issues)
- Check existing documentation
- Review [CHANGELOG](./CHANGELOG.md) (to be created)

---

## 🔗 Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Gemini API](https://ai.google.dev/gemini-api/docs)
- [Pollinations.ai](https://pollinations.ai/)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [DuckDuckGo API](https://duckduckgo.com/api)

---

**Last Updated**: September 19, 2026  
**Version**: 1.1.0 — Stateless (web search, weather, and session storage removed)
