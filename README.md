# ConBot 🤖

Open-source self-hosted AI assistant powered by NVIDIA Nemotron via OpenRouter, with optional Gemini fallback, image generation, and a lightweight JavaScript frontend.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/FastAPI-0.133.1-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License" />
  <img src="https://img.shields.io/badge/Status-Active-brightgreen" alt="Active" />
</p>

ConBot is a self-hosted AI chat assistant designed to run locally or in production with minimal setup. It combines:
- NVIDIA Nemotron as the default primary model via OpenRouter
- optional Gemini support for fallback or alternate routing
- OpenRouter compatibility for flexible model switching
- SSE streaming responses
- multimodal AI capabilities
- image generation via Pollinations.ai
- a simple, dependency-light web UI

It is built for developers who want an AI assistant they can run themselves, customize, and extend.

---

## Why ConBot?

Most AI chatbot projects are either:
- too basic and demo-only
- tightly coupled to a single provider
- expensive to self-host
- difficult to deploy and customize

ConBot aims to be different:
- NVIDIA Nemotron as the default primary model via OpenRouter
- optional Gemini and other provider support
- production-minded backend architecture
- simple frontend with no heavy framework
- stateless API design
- secure and rate-limited request handling
- deployable with Docker and easy local development

---

## Demo

[Add your screenshot or GIF here]

Example:
- chat interface
- image generation
- streaming responses
- provider fallback behavior

You can also add a live demo URL here if available.

---

## Features

### Core features
- Multi-provider text chat using NVIDIA Nemotron via OpenRouter as the default
- optional Gemini fallback / alternative provider paths
- Server-Sent Events (SSE) streaming responses
- image generation via Pollinations.ai
- optional image input support in chat
- multi-language behavior with locale-aware responses
- simple vanilla JavaScript frontend
- stateless chat model
- Docker-ready deployment
- built-in rate limiting and concurrency protection

### Production-minded capabilities
- safe request validation
- model fallback chain with circuit breaker behavior
- request and response hardening
- security headers and request body limits
- API health checks
- local development and Docker deployment workflows

---

## Architecture

ConBot uses a simple architecture designed for clarity and extensibility:

```text
Browser / Web UI
      │
      ▼
FastAPI backend (app/)
      │
      ├── request validation
      ├── rate limiting
      ├── security middleware
      ├── fallback dispatch
      │
      ├── NVIDIA Nemotron via OpenRouter
      ├── Gemini (optional / alternate provider path)
      └── Pollinations.ai image generation
```

The backend is organized as a modular Python package:
- `app/api/` – route handlers and API entrypoints
- `app/services/` – business logic
- `app/core/` – middleware, rate limiting, security, circuit breaker
- `app/models/` – request/response schemas
- `frontend/` – static web client

---

## Tech Stack

### Backend
- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic / pydantic-settings
- httpx

### Frontend
- HTML
- CSS
- Vanilla JavaScript
- no framework required

### External services
- NVIDIA Nemotron via OpenRouter (default primary model)
- Google Gemini (supported as optional provider/fallback)
- Pollinations.ai

### Deployment
- Docker
- Render (example backend deployment)
- Cloudflare Workers static asset hosting

---

## Quick Start

### Prerequisites
- Python 3.10+ (3.12 recommended)
- Docker (optional)
- OpenRouter API key for the default Nemotron path
- Gemini API key (optional, for Gemini-based fallback or alternate model usage)

### 1) Clone the repo

```bash
git clone https://github.com/Kumar6-Vinay/ConBot.git
cd ConBot
```

### 2) Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### 4) Configure environment

```bash
cp .env.example .env
```

Then edit `.env` and add:
- `OPENROUTER_API_KEY` for the default Nemotron path
- optional `GEMINI_API_KEY` if you want Gemini support enabled
- any other config needed in your environment

### 5) Start the backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6) Serve the frontend

```bash
python -m http.server 3000 --directory frontend
```

Open:
- `http://localhost:3000`

---

## Docker

### Build

```bash
docker build -t conbot:latest .
```

### Run

```bash
docker run -p 8000:8000 \
  -e OPENROUTER_API_KEY=your_key_here \
  -e GEMINI_API_KEY=your_key_here \
  conbot:latest
```

---

## Configuration

ConBot reads configuration from environment variables. A template is included in `.env.example`.

Key settings include:

- `PRIMARY_MODEL`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`
- `NVIDIA_API_KEY`
- `TEXT_FALLBACK_CHAIN`
- `RATE_LIMIT_MAX`
- `DAILY_REQUEST_LIMIT`
- `MAX_CONCURRENT_STREAMS`
- `ALLOWED_ORIGINS`

The project is designed to be flexible:
- switch providers
- adjust rate limits
- change fallback order
- run locally or in production

Current default configuration:
- `PRIMARY_MODEL=openrouter:nvidia/nemotron-3.5-super-vl:free`

---

## API Overview

### `/health`
Returns basic health/status information and whether the app is configured correctly.

### `/ask`
Send a chat prompt and receive a full response.

### `/stream`
Streaming version of chat using SSE.

### `/generate-image`
Generate an image from a text prompt using Pollinations.ai.

### `/models/image`
List the image generation models available.

---

## Project Structure

```text
ConBot/
├── app/
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── ask.py
│   │       ├── health.py
│   │       ├── image.py
│   │       └── stream.py
│   ├── core/
│   │   ├── circuit_breaker.py
│   │   ├── errors.py
│   │   ├── middleware.py
│   │   ├── rate_limit.py
│   │   └── security.py
│   ├── models/
│   │   ├── ask.py
│   │   └── image.py
│   ├── services/
│   │   ├── conversation.py
│   │   ├── fallback.py
│   │   ├── gemini_client.py
│   │   ├── image_generation.py
│   │   ├── nvidia_client.py
│   │   └── openrouter_client.py
│   ├── config.py
│   ├── logging_config.py
│   └── main.py
├── frontend/
│   ├── app.js
│   ├── index.html
│   ├── styles.css
│   ├── favicon.svg
│   └── _headers
├── tests/
│   ├── test_fallback.py
│   ├── test_image_generation.py
│   └── test_main.py
├── .env.example
├── .gitignore
├── Dockerfile
├── LICENSE
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── SECURITY_AUDIT.md
├── SECURITY.md
├── DESIGN_AUDIT.md
├── wrangler.json
└── CLAUDE.md
```

---

## Security

ConBot includes security-aware safeguards:
- explicit CORS allowlist
- rate limiting per client and globally
- request size limits
- secret-safe logging
- secure headers
- input validation on model requests and uploaded content
- dependency and runtime hardening

See:
- `SECURITY.md`
- `SECURITY_AUDIT.md`

---

## Contributing

Contributions are welcome.

### Recommended workflow
1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests
5. Open a pull request

```bash
pytest -q
```

If you add a feature, please include tests where practical.

---

## Roadmap

Planned improvements include:
- CI/CD automation
- dependency lockfile management
- better observability and analytics
- public documentation for deployment and privacy
- more starter-friendly customization examples
- broader model/provider abstraction
- more frontend polish and UX improvements

---

## License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for details.

---

## Author

Kumar Vinay  
GitHub: [@Kumar6-Vinay](https://github.com/Kumar6-Vinay)

---

## Support

For bugs, questions, or ideas, open an issue:
- https://github.com/Kumar6-Vinay/ConBot/issues

---

## Final note

ConBot is designed to be practical, minimal, and extensible rather than bloated. It is a solid foundation for building a self-hosted AI assistant or a custom chat product without locking yourself to a single provider.

If you want to go further:
- add authentication
- add persistent chat history
- add vector search
- add file upload support
- add custom prompt management
- add team workspaces

The core structure is already in place.
