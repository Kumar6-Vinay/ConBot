# ConBOT 🤖

**A production-oriented cloud-native RAG (Retrieval-Augmented Generation) platform for intelligent conversational AI.**

ConBOT is a sophisticated multi-model AI assistant that combines local LLMs with cloud-based AI services, real-time web search, and weather APIs to deliver contextually aware, location-sensitive answers to users worldwide.

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
- **Rate Limiting & Security**: Built-in protection against abuse with per-IP rate limiting
- **Streaming Responses**: Server-sent events (SSE) for real-time answer generation
- **Production Ready**: Enterprise-grade logging, error handling, and CORS management

---

## ✨ Features

### Core Capabilities
- **Smart Web Search**: Automatic detection of queries requiring current information
- **Weather Integration**: Real-time weather data via Open-Meteo API (free, no API key required)
- **Multi-Model Support**: 
  - Qwen 3 (14B)
  - Llama 3 (Latest)
  - Mistral (Latest)
- **Intelligent Prompting**: Custom system prompts with behavioral guidelines
- **Structured Responses**: Automatic parsing of follow-up questions and clarification blocks
- **Conversation History**: Maintains context with configurable conversation depth
- **Locale-Aware Context**: Uses timezone and language data for hyper-local answers

### Technical Features
- **Server-Sent Events (SSE)**: Real-time streaming for instant user feedback
- **Fallback Mechanisms**: Graceful degradation from cloud to local models
- **Rate Limiting**: Fixed-window rate limiting per client IP
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
│  │ Web Search (DuckDuckGo) & Weather APIs               │   │
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
- **Web Search**: DuckDuckGo API
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

# 3. Install dependencies
pip install -r requirements.txt

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
# Required
OPENROUTER_API_KEY=sk-...  # Your OpenRouter API key

# Optional
OLLAMA_URL=http://host.docker.internal:11434/api/generate
ALLOW_OLLAMA_FALLBACK=false  # Use Ollama if OpenRouter fails
MAX_HISTORY_TURNS=10         # Conversation history depth
MAX_OUTPUT_TOKENS=2400       # Max tokens per response
RATE_LIMIT_MAX=20            # Max requests per window
RATE_LIMIT_WINDOW=600        # Rate limit window (seconds)
FALLBACK_TIMEZONE=Asia/Kolkata # Default timezone
```

### Supported Models
- `qwen3:14b` (Recommended for multilingual)
- `llama3:latest`
- `mistral:latest`

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

**Request**:
```json
{
  "prompt": "What's the weather like?",
  "model": "qwen3:14b",
  "history": [],
  "timezone": "Asia/Kolkata",
  "language": "en-IN"
}
```

**Response**:
```json
{
  "answer": "The current weather in Delhi is...",
  "web_used": true,
  "sources": [
    {
      "title": "Current Weather in Delhi",
      "url": "open-meteo.com"
    }
  ]
}
```

### `/stream` (POST)
Streaming endpoint using Server-Sent Events (SSE).

**Response Stream Events**:
```
data: {"type": "sources", "sources": [...]}
data: {"type": "delta", "text": "partial response text"}
data: {"type": "followups", "questions": [...]}
data: {"type": "done"}
```

---

## 🔧 Development

### Project Structure
```
ConBot/
├── main.py                      # Main FastAPI application
├── requirements.txt             # Python dependencies
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
10. **Web Search** - DuckDuckGo integration
11. **Weather** - Open-Meteo weather API
12. **LLM Backends** - OpenRouter and Ollama clients
13. **Endpoints** - API route handlers

### Testing

```bash
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

- **Render** (Recommended): Git-connected deployment with auto-scaling
- **Heroku**: Traditional Docker/buildpack deployment
- **AWS Lambda**: Serverless with ALB/API Gateway
- **Kubernetes**: Enterprise-grade orchestration
- **Docker**: Any container runtime

### CORS Configuration

Pre-configured for:
- Local development: `localhost:3000`, `localhost:3001`
- Production: `conbot.in`, `www.conbot.in`
- CDN: `llama-chatbot-fe.onrender.com`
- GitHub Pages: `kumar6-vinay.github.io`

Update the `allow_origins` list in `main.py` for custom domains.

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
   - No unit tests present
   - Should add: pytest, test fixtures, integration tests

3. **Documentation**
   - API documentation could be richer
   - No docstrings in main.py functions
   - Should add type hints throughout

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
- Add comprehensive test suite
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
