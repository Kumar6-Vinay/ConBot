# ConBot

A self-hostable AI assistant with a streaming web interface, multimodal chat, and a provider fallback layer. Built with FastAPI and vanilla JavaScript.

[![CI](https://github.com/Kumar6-Vinay/ConBot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Kumar6-Vinay/ConBot/actions/workflows/ci.yml) [![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Live app:** [conbot.in](https://conbot.in) · **API health:** [`/v1/health`](https://llama-chatbot-qb2c.onrender.com/v1/health)

> ConBot is an independent portfolio project. It is not affiliated with or endorsed by OpenAI, Anthropic, Google, NVIDIA, OpenRouter, or Pollinations.ai.

## What it demonstrates

- **Streaming API design:** FastAPI endpoints stream model output to the browser over Server-Sent Events (SSE).
- **Provider adapters and fallback:** Gemini, OpenRouter, and NVIDIA integrations sit behind a configurable provider/model chain. Transient failures can advance to another configured model; a circuit breaker skips repeatedly failing links.
- **Multimodal and image workflows:** Gemini-powered image understanding, plus image generation through Pollinations.ai.
- **A deliberately small client:** responsive HTML/CSS and vanilla JavaScript, with no frontend framework or build step.
- **Defensive API engineering:** Pydantic request validation, request-size controls, CORS allowlisting, security headers, rate limits, concurrency limits for chat streams, and request-ID-based logs.
- **Runnable project practices:** Docker packaging, automated tests, and GitHub Actions CI.

## Try it

Visit [conbot.in](https://conbot.in) to use the hosted application. The hosted service may be subject to rate limits and provider availability.

## Architecture

```text
Browser (static HTML/CSS/JavaScript)
  ├─ POST /v1/stream ───────────────┐
  ├─ POST /v1/ask                    │
  └─ POST /v1/generate-image         │
                                     ▼
                              FastAPI application
                              ├─ request validation and limits
                              ├─ conversation preparation
                              ├─ provider/model fallback chain
                              │    ├─ Google Gemini
                              │    ├─ OpenRouter
                              │    └─ NVIDIA API
                              └─ Pollinations.ai image generation
```

The backend keeps no conversation database. The browser sends the relevant text history with each chat request; the UI stores chat text in that browser's `localStorage`. Image attachments are sent with one request and are not added to chat history. Provider credentials remain on the backend.

## Run locally

### Requirements

- Python 3.12 (the CI workflow and Docker image use 3.12)
- An API key for at least one configured text provider
- `POLLINATIONS_API_KEY` if you want to use image generation

### 1. Install and configure

```bash
git clone https://github.com/Kumar6-Vinay/ConBot.git
cd ConBot
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` and set credentials for the providers in your selected model chain. The checked-in defaults use Gemini as the primary model and include Gemini and OpenRouter fallback models, so the default setup needs the corresponding keys. To use only OpenRouter, set `PRIMARY_MODEL` to an `openrouter:<model-id>` model and configure `TEXT_FALLBACK_CHAIN` with only providers for which you have keys. NVIDIA models use the `nvidia:<model-id>` provider prefix. Do not commit `.env` or real credentials.

Image understanding currently requires `GEMINI_API_KEY`. Image generation requires `POLLINATIONS_API_KEY`.

### 2. Start the API

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is mounted under `/v1`. Verify the server at <http://127.0.0.1:8000/v1/health>.

### 3. Point the frontend at your local API

The checked-in static page points at the hosted API. For local development, change the `data-api-base` value on the script tag near the end of `frontend/index.html` to `http://127.0.0.1:8000/v1`, then serve the static files:

```bash
python -m http.server 3000 --directory frontend
```

Open <http://127.0.0.1:3000>. Restore the hosted API URL before deploying the static frontend.

## Provider configuration

Model names use `provider:model-id` syntax. The current defaults in `app/config.py` are:

```dotenv
PRIMARY_MODEL=google:gemini-2.5-flash
TEXT_FALLBACK_CHAIN=google:gemini-2.5-flash-lite,openrouter:nvidia/nemotron-3.5-super-vl:free
```

Supported provider prefixes are `google`, `openrouter`, and `nvidia`. The model chain is configurable through environment variables; check the target provider's current model catalog and account requirements before choosing a model. Availability and pricing can change independently of this project.

## API overview

All routes are prefixed with `/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/v1/health` | Basic service and provider-configuration status. |
| `POST` | `/v1/ask` | Return a complete chat response as JSON. |
| `POST` | `/v1/stream` | Stream chat events using SSE. The web client uses this route. |
| `POST` | `/v1/generate-image` | Generate an image through Pollinations.ai. |
| `GET` | `/v1/models/image` | List image-generation models exposed by the app. |

A minimal non-streaming request:

```bash
curl -sS http://127.0.0.1:8000/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain SSE in a few sentences."}'
```

The streaming endpoint emits `data: <JSON>` SSE events, including answer deltas and completion or error events. See `app/api/routes/stream.py` for the event contract.

## Tests and CI

Run the test suite locally:

```bash
pytest -q
```

Tests use fakes for upstream model calls and do not require live provider credentials. GitHub Actions runs the tests on Python 3.12 for pushes and pull requests targeting `main` and `redesign`.

## Docker

Build and run the API container:

```bash
docker build -t conbot:local .
docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=your_key_here \
  conbot:local
```

For an OpenRouter-only deployment, supply a compatible `PRIMARY_MODEL` and `OPENROUTER_API_KEY` as well. The Docker image runs as a non-root user. The static frontend is served separately.

## Security, privacy, and operational limits

- The API uses an explicit CORS allowlist. Configure `ALLOWED_ORIGINS` for the origins where you host the frontend.
- Chat rate limits, daily quotas, circuit-breaker state, and stream concurrency counters are held in process memory. They reset on restart and are not shared across multiple replicas; this is not a distributed abuse-prevention system.
- Chat text is sent to the configured model provider. The frontend stores conversation text in browser `localStorage`; clear that browser storage to remove it. Attached images are sent with their request and are not added to the text history.
- The frontend includes a Google Analytics tag. Review or remove it if you do not want analytics on your deployment.
- Image generation requires a Pollinations API key. Provider usage may incur charges under the provider's current terms.

See [SECURITY.md](SECURITY.md) for vulnerability reporting. `SECURITY_AUDIT.md` is a historical audit document; its findings should not be treated as a current assessment without re-verification.

## Project layout

```text
app/
  api/          HTTP routes and request preparation
  core/         middleware, request limits, security, and circuit breaker
  models/       request and response schemas
  services/     provider clients, fallback, conversations, image generation
frontend/       static browser client
 tests/         automated tests
.github/        CI workflow
```

## Contributing

Bug reports and focused improvements are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), then run `pytest -q` before opening a pull request.

## License

ConBot is distributed under the [MIT License](LICENSE).
