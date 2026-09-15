# ConBOT 🤖

**A general-purpose AI assistant (conbot.in) — FastAPI backend, vanilla-JS frontend.**

ConBOT answers questions through OpenRouter (with an optional local Ollama fallback), adds live weather and web results when a question needs current information, and answers for the user's country and language by default. It is a prototype working toward a production chat product.

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
- **Flexible LLM Backend**: Seamlessly switches between OpenRouter (cloud) and Ollama (local) models
- **Rate Limiting**: Per-IP window and daily caps, plus a global daily cost cap (in-memory, single instance)
- **Streaming Responses**: Server-sent events (SSE) for real-time answer generation
- **Safe errors & logs**: Request-id log lines without question text; users only ever see safe messages

---

## ✨ Features

### Core Capabilities
- **Smart Web Search**: Detects questions that need current information. Uses the Brave Search API when `BRAVE_SEARCH_API_KEY` is set; otherwise falls back to DuckDuckGo Instant Answers (encyclopedia abstracts only — weak for news, prices and scores)
- **Weather Integration**: Current conditions or tomorrow's forecast via Open-Meteo (free, no API key)
- **One mode, `text`**: served by an OpenRouter model (`OPENROUTER_TEXT_MODEL`), or a local Ollama model (`OLLAMA_MODEL`) as fallback
- **Intelligent Prompting**: Custom system prompts with behavioral guidelines
- **Structured Responses**: Automatic parsing of follow-up questions and clarification blocks
- **Conversation History**: Maintains context with configurable conversation depth
- **Locale-Aware Context**: Uses timezone and language data for hyper-local answers

### Technical Features
- **Server-Sent Events (SSE)**: Real-time streaming for instant user feedback
- **Fallback Mechanisms**: Optional OpenRouter → Ollama fallback, before the first token only
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
│  │ API Endpoints (/ask, /stream, /health)               │   │
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
         ▼ Primary                      ▼ Fallback
    ┌─────────────┐               ┌──────────────┐
    │ OpenRouter  │               │    Ollama    │
    │ Cloud API   │               │   Local LLM  │
    └─────────────┘               └──────────────┘
```

### Data Flow

1. **Request Ingestion**: User submits prompt via `/ask` or `/stream` endpoint
2. **Validation**: Input validation and rate limiting enforcement
3. **Context Resolution**: Timezone/location parsing and system prompt construction
4. **Search Decision**: Determines if web search is required based on keywords
5. **Augmentation**: Fetches web search results or weather data if needed
6. **LLM Invocation**: Sends augmented prompt to OpenRouter or Ollama
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
- **LLM Cloud**: OpenRouter API
- **Local LLM**: Ollama
- **Web Search**: Brave Search API (optional, keyed) → DuckDuckGo Instant Answer API
- **Weather**: Open-Meteo API (Free)
- **Geocoding**: Open-Meteo Geocoding API

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (optional)
- OpenRouter API Key (or local Ollama setup)

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
# Edit .env and add your OpenRouter API key

# 5. Run the backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

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
  -e OPENROUTER_API_KEY=your_key_here \
  -e ALLOW_OLLAMA_FALLBACK=false \
  conbot:latest
```

---

## ⚙️ Configuration

Environment variables (see `.env.example`):

```env
# Required (unless running Ollama-only locally)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_TEXT_MODEL=mistralai/mistral-small-3.2-24b-instruct:free

# Local fallback (development only — there is no Ollama on a managed host)
ALLOW_OLLAMA_FALLBACK=false
OLLAMA_URL=http://host.docker.internal:11434/api/generate
OLLAMA_MODEL=llama3:latest

# Live web search (optional — costs money per request once set)
BRAVE_SEARCH_API_KEY=

# Conversation and output size
MAX_HISTORY_TURNS=8          # messages replayed to the model
MAX_HISTORY_CHARS=3000       # each replayed message is trimmed to this
MAX_OUTPUT_TOKENS=1200

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

The API accepts `model: "text"` only. Image, video and image-generation modes were removed until the request body can carry attachments and the client can render images.

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
  "ollama_fallback": false
}
```

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

---

## 🔧 Development

### Project Structure
```
ConBot/
├── main.py                      # Main FastAPI application
├── requirements.txt             # Python dependencies
├── requirements-dev.txt         # Test-only dependencies (pytest)
├── tests/
│   └── test_main.py             # Regression tests, no network needed
├── Dockerfile                   # Container configuration
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore rules
├── README.md                    # This file
├── frontend/
│   ├── index.html              # Web interface
│   ├── app.js                  # Client-side logic
│   └── styles.css              # Styling
└── .github/
    └── workflows/
        └── pages.yml           # GitHub Pages deployment
```

### Code Organization

**main.py** is organized into logical sections:

1. **Imports & Logging** - Dependencies and logging setup
2. **Application Setup** - FastAPI initialization
3. **Configuration** - Environment variables and constants
4. **Rate Limiting** - Request throttling logic
5. **CORS** - Cross-origin resource sharing
6. **Behavior** - System prompts and guidelines
7. **Models** - Pydantic request/response schemas
8. **Location** - Timezone and language resolution
9. **Block Processing** - Parsing structured blocks in responses
10. **Web Search** - Brave (optional) and DuckDuckGo
11. **Weather** - Open-Meteo current conditions and forecast
12. **LLM Backends** - OpenRouter and Ollama clients
13. **Endpoints** - API route handlers

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
```

---

## 🌐 Deployment

### Environment Considerations

| Environment | LLM Backend | Configuration |
|-------------|-------------|---------------|
| **Development** | Ollama (local) | `ALLOW_OLLAMA_FALLBACK=true` |
| **Production** | OpenRouter | `OPENROUTER_API_KEY` required |
| **Hybrid** | Both | Fallback enabled + API key |

### Deployment Platforms

- **Render** (current): Git-connected Docker deployment. Rate limits are in-memory, so run one instance
- **Heroku**: Traditional Docker/buildpack deployment
- **Docker**: Any container runtime

### CORS Configuration

Built-in origins:
- Local development: `localhost:3000`, `localhost:3001`
- Production: `conbot.in`, `www.conbot.in`
- Render frontend: `llama-chatbot-fe.onrender.com`
- GitHub Pages: `kumar6-vinay.github.io`

Set `ALLOWED_ORIGINS` (comma-separated) to replace this list without editing code.

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
   - Graceful fallbacks (OpenRouter → Ollama)
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

1. **Project Structure**
   - All code in single `main.py` (consider modular structure for larger teams)
   - Should split into: `models/`, `services/`, `routers/`, `config/`

2. **Testing**
   - Regression suite in `tests/` (pytest); not yet run in CI

3. **Documentation**
   - API documentation could be richer

4. **Monitoring**
   - No metrics/observability setup
   - Consider: Prometheus, Sentry, New Relic integration

5. **CI/CD**
   - Only GitHub Pages workflow present
   - Missing: linting, testing, deployment pipelines
   - Should add: Black, Flake8, GitHub Actions

6. **Database**
   - No persistent storage for conversations
   - Consider: PostgreSQL for chat history if needed

7. **Frontend**
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
- Modularize main.py
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
- [OpenRouter API](https://openrouter.ai/docs)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [DuckDuckGo API](https://duckduckgo.com/api)

---

**Last Updated**: September 15, 2026  
**Version**: 1.0.0
