# ConBOT 🤖

**A general-purpose AI assistant (conbot.in) — FastAPI backend, vanilla-JS frontend.**

ConBOT answers questions through Google's Gemini API, adds live weather and web results when a question needs current information, generates images via Pollinations.ai, and answers for the user's country and language by default. It is a prototype working toward a production chat product.

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
- **Real-time Information**: Integrates web search and weather APIs for current data
- **LLM Backend**: Google's Gemini API (multimodal — text and image input in the same chat)
- **Image Generation**: On-demand image generation via Pollinations.ai
- **Rate Limiting**: Per-IP window and daily caps, plus a global daily cost cap (in-memory, single instance)
- **Streaming Responses**: Server-sent events (SSE) for real-time answer generation
- **Safe errors & logs**: Request-id log lines without question text; users only ever see safe messages

---

## ✨ Features

### Core Capabilities
- **Smart Web Search**: Detects questions that need current information. Uses the Brave Search API when `BRAVE_SEARCH_API_KEY` is set; otherwise falls back to DuckDuckGo Instant Answers (encyclopedia abstracts only — weak for news, prices and scores)
- **Weather Integration**: Current conditions or tomorrow's forecast via Open-Meteo (free, no API key)
- **One chat mode, `text`**: served by a Gemini model (`GEMINI_TEXT_MODEL`, mapped in `GEMINI_MODEL_MAP`)
- **Image Generation**: A separate `/generate-image` endpoint calling Pollinations.ai, with a choice of models via `/models/image`
- **Intelligent Prompting**: Custom system prompts with behavioral guidelines
- **Structured Responses**: Automatic parsing of follow-up questions and clarification blocks
- **Conversation History**: Maintains context with configurable conversation depth
- **Locale-Aware Context**: Uses timezone and language data for hyper-local answers

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
│  │ Location Resolution & Context Building               │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Web Search (Brave / DuckDuckGo) & Weather APIs       │   │
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
3. **Context Resolution**: Timezone/location parsing and system prompt construction
4. **Search Decision**: Determines if web search is required based on keywords
5. **Augmentation**: Fetches web search results or weather data if needed
6. **LLM Invocation**: Sends augmented prompt to Google's Gemini API
7. **Post-Processing**: Parses structured blocks (clarifications, follow-ups)
8. **Response**: Streams or returns complete answer with metadata

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
- **Styling**: CSS3 (modern with animations)
- **Interactivity**: Vanilla JavaScript (no frameworks)

### Infrastructure
- **Containerization**: Docker
- **Runtime**: Python 3.12-slim
- **Security**: Non-root user execution

### External Services
- **LLM**: Google Gemini API
- **Image Generation**: Pollinations.ai
- **Web Search**: Brave Search API (optional, keyed) → DuckDuckGo Instant Answer API
- **Weather**: Open-Meteo API (Free)
- **Geocoding**: Open-Meteo Geocoding API

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
# Required — Google AI Studio key for the Gemini API.
# GOOGLE_API_KEY and OPENROUTER_API_KEY are read as legacy aliases if
# GEMINI_API_KEY is unset, so an old deployment keeps working until renamed.
GEMINI_API_KEY=...
GEMINI_TEXT_MODEL=gemini-3.6-flash

# Image generation (Pollinations.ai). Required for /generate-image; the
# rest of the app works without it.
POLLINATIONS_API_KEY=
POLLINATIONS_MODEL=lykon/dreamshaper-8-lcm

# Live web search (optional — costs money per request once set)
BRAVE_SEARCH_API_KEY=

# Conversation and output size
MAX_HISTORY_TURNS=8          # messages replayed to the model
MAX_HISTORY_CHARS=3000       # each replayed message is trimmed to this
MAX_OUTPUT_TOKENS=1200
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
```

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
  "answer": "The current weather in Delhi is...",
  "web_used": true,
  "sources": [{"title": "Current weather in Delhi, India", "url": "https://open-meteo.com/"}],
  "followups": ["Will it rain later today?"],
  "clarify": null
}
```

`answer` never contains the raw `[[FOLLOWUPS]]` / `[[CLARIFY]]` blocks. When the model needs one detail first, `clarify` is `{"question": ..., "options": [...]}` and `answer` holds the question.

### `/stream` (POST)
Streaming endpoint using Server-Sent Events (SSE).

**Response Stream Events**:
```
data: {"type": "sources", "sources": [...]}
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
│   │   ├── web_search.py          # Brave (optional) and DuckDuckGo
│   │   ├── weather.py             # Open-Meteo current conditions and forecast
│   │   └── conversation.py        # System prompt, locale, BlockFilter, message assembly
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
│   └── test_image_generation.py  # Image generation regression tests, no network needed
├── Dockerfile                    # Container configuration
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── README.md                     # This file
└── frontend/
    ├── index.html               # Web interface
    ├── app.js                   # Client-side logic
    └── styles.css               # Styling
```

### Code Organization

The backend is a package (`app/`), not a single file. Route handlers in
`app/api/routes/` are thin — they call into `app/services/` (business logic,
no FastAPI imports), `app/core/` (rate limiting, errors, security), and
`app/api/deps.py` (the shared `/ask` + `/stream` pipeline: `prepare()`,
model validation, Gemini dispatch). Callers import these as modules
(`from app.services import web_search`) rather than importing bare
functions, so tests can monkeypatch them at the module level.

Image generation (`app/services/image_generation.py`) is a self-contained
Pollinations.ai client with its own env var reads, used only by
`app/api/routes/image.py`.

### Testing

```bash
# Unit/regression tests (no API key, no network)
pytest -q

# Test endpoints locally
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?"}'

# Test streaming
curl -X POST http://localhost:8000/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a joke"}'

# Test image generation
curl -X POST http://localhost:8000/generate-image \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat astronaut"}'
```

---

## 🌐 Deployment

### Environment Considerations

Both development and production use the same backend: Google's Gemini API, configured with `GEMINI_API_KEY`. There is no local-model fallback.

### Deployment Platforms

- **Backend — Render** (current): Git-connected Docker deployment. Rate limits are in-memory, so run one instance
- **Frontend — Cloudflare Pages** (current): static deploy of `frontend/`, no build step. The repo is private, so this is a Git-connected Cloudflare Pages project (Cloudflare's GitHub App supports private repos, unlike GitHub Pages on the free plan) with custom domain `conbot.in`
- **Docker**: Any container runtime, for the backend

### CORS Configuration

Built-in origins:
- Local development: `localhost:3000`, `localhost:3001`
- Production: `conbot.in`, `www.conbot.in`
- Render frontend: `llama-chatbot-fe.onrender.com`

Set `ALLOWED_ORIGINS` (comma-separated) to replace this list without editing code — needed for the Cloudflare Pages preview URL (`*.pages.dev`) if you test against the live backend from there before DNS cutover.

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
   - No GitHub Actions workflows — frontend deploys via Cloudflare Pages' own Git integration, backend via Render's
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

**Last Updated**: September 17, 2026  
**Version**: 1.0.0
