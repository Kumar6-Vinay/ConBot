# ConBOT

A general-purpose AI assistant (conbot.in). FastAPI backend, primarily on
Google's Gemini API with an OpenRouter fallback tier, vanilla-JS frontend.
Goal: a production chat product, not a demo.

## Repo map

| Path | What it is |
|---|---|
| `app/main.py` | FastAPI app creation, lifespan, CORS, and route registration only — no business logic. |
| `app/config.py` | All settings derived from env vars (pydantic-settings + plain derived constants). |
| `app/api/routes/` | Route handlers, one file per endpoint: `health.py`, `ask.py`, `stream.py`, `image.py` (`/generate-image`, `/models/image`). |
| `app/api/deps.py` | The shared request pipeline both `/ask` and `/stream` call: `prepare()`, `validate_model()`, dispatch to the fallback chain (`get_ai_answer`/`stream_answer`, backed by `app.services.fallback`). |
| `app/services/` | Business logic, no FastAPI imports: `gemini_client.py` (one Gemini attempt), `openrouter_client.py` (one OpenRouter attempt, mirrors `gemini_client.py`), `fallback.py` (walks `TEXT_FALLBACK_CHAIN` across both, the only place that loops), `image_generation.py` (Pollinations.ai), `conversation.py` (system prompt, `BlockFilter`, message assembly). |
| `app/core/` | `rate_limit.py`, `circuit_breaker.py` (marks a cold `provider:model` pair so the chain skips it), `middleware.py` (`MaxBodySizeMiddleware`, `SecurityHeadersMiddleware`), `errors.py` (`no_llm_error`, `ContentBlocked`), `security.py` (`validate_image`, `clip`). |
| `app/models/` | Pydantic request/response schemas: `ask.py` (`Turn`, `ChatRequest`), `image.py`. |
| `tests/` | `test_main.py` (chat/stream), `test_image_generation.py`, `test_fallback.py` (chain advance, fail-fast, breaker, budget). No network, no API key. |
| `frontend/index.html` | Single-page shell: sidebar (always present; drawer on mobile), header bar, home hero ("What do you want to know?" + composer + 4 suggestion chips), message thread, docked composer, `+` menu, camera modal, image-generator view. |
| `frontend/app.js` | All client logic — SSE reader, markdown, sessions, voice, theme, `+` menu (upload/take photo via `getUserMedia`), "Create image" toggle (generates in-thread via `/generate-image`; the `+` menu and sidebar still open the dedicated generator view), composer pinning on phones. |
| `frontend/styles.css` | All styling. Tokens in `:root` (Geist font, `--page-bg`/`--surface`/`--canvas`, `--ink*`, `--accent` #2563EB). Light/dark via `body.dark` / `body.light`; never detect the theme by pixel colour. |
| `frontend/_headers` | Cloudflare Workers static-assets header rules (CSP, HSTS, etc.) for the frontend's own responses. |
| `Dockerfile` | Backend image only. |
| `wrangler.json` | Cloudflare Workers config that serves `frontend/` as static assets — this is how the frontend deploys, not classic Cloudflare Pages. |

There is no database and no auth. Rate limits are in-memory, so the backend
must run as a single instance. The repo is private; the frontend deploys via
Cloudflare Workers static assets (not GitHub Pages) because GitHub Pages
requires a public repo on the free plan. There is no CI workflow — `pytest -q`
is run manually.

## Architecture facts you must not get wrong

- **The backend is the `app/` package, not a single file.** Route handlers
  (`app/api/routes/`) are thin — they call into `app/services/`, `app/core/`
  and `app/api/deps.py`. Always import those as modules
  (`from app.services import conversation`) and call module functions,
  never import bare functions — tests monkeypatch these at the module level
  (e.g. `monkeypatch.setattr(conversation, "build_messages", ...)`),
  and patching a bare imported name silently does nothing.
- **The server is fully stateless; conversations are ephemeral.** `app.js`
  keeps `history` in memory for the current session and replays it on each request.
  The server trims it to `MAX_HISTORY_TURNS` messages, each clipped to
  `MAX_HISTORY_CHARS`. Trim, never reject: a long answer must not break the
  next question. No persistence to disk, localStorage, or database.
- **`/stream` is the primary path** (SSE: `delta`, `clarify`,
  `followups`, `truncated`, `error`, `done`). `/ask` is the non-streaming
  equivalent and returns `{answer, followups, clarify}`. No web sources.
- **Text chat walks a multi-provider fallback chain, not a single model.**
  `GEMINI_MODEL_MAP[mode]` resolves to `PRIMARY_MODEL` (`provider:model_id`,
  currently OpenRouter's Qwen free tier by default — not Gemini) and is
  always tried first; on a 429, 5xx, timeout, or empty answer it falls
  through `TEXT_FALLBACK_CHAIN`
  (`app/config.py`), an ordered `provider:model_id` list mixing more Google
  models and OpenRouter models — `app/services/fallback.py` is the only
  place that loops across them. `GEMINI_API_KEY` and `OPENROUTER_API_KEY`
  are two independent credentials for two different providers, never one
  aliasing the other — `GOOGLE_API_KEY` remains a legacy alias for
  `GEMINI_API_KEY` only. A 400/401/403/404 or a Gemini content-policy block
  (`ContentBlocked`) fails immediately instead of advancing — a different
  model won't fix a bad request or a policy refusal.
- **A circuit breaker (`app/core/circuit_breaker.py`) skips known-cold
  links.** After `BREAKER_FAILURE_THRESHOLD` consecutive failures, a
  `provider:model` pair is skipped entirely (not attempted) for
  `BREAKER_COOLDOWN_SECONDS`. `GET /health`'s `fallback_degraded` boolean is
  the only thing this ever exposes over HTTP — deliberately coarse, no
  model or provider name, so an anonymous caller can't map out exactly
  what's currently exhausted.
- **The model emits `[[FOLLOWUPS]]` / `[[CLARIFY]]` blocks.** `BlockFilter`
  strips them from prose. Mid-stream, a tag only counts once its line has
  ended (`TAG_LINE_RE`); the end of the buffer is not the end of a line.
  Neither endpoint may ever return a raw tag to the client.
- `AVAILABLE_MODELS` is an allow-list and currently only `text`. Adding a
  mode needs end-to-end support (request body, parser, UI), not just a map entry.
- Client-side conversation history lives in memory (JavaScript `history` array)
  for the current session only; it is replayed on each request but never persisted.
- Client limits must stay at or under server limits: prompt 3000 chars,
  `MAX_TURNS` 16, per-message 3000 chars.

## Conventions

**Python**
- Type hints on every function. Pydantic models for request bodies.
- `async def` endpoints with `httpx.AsyncClient` — never blocking `requests`.
- Never `print()`. Use `logger` with `[request_id]` and key=value fields.
- Never log question text — use `question_fingerprint()` and lengths.
- Never leak upstream internals to the client — no model names, no stack
  traces, no provider errors. Map to a safe `detail` string.
- Secrets, endpoints and model names come from environment variables.
- Validate the model before `enforce_rate_limit()` so bad requests cost no quota.

**JavaScript**
- No build step, no framework, no bundler.
- Never `innerHTML` with model output or user text. Model output goes through
  `markdown()` (escape first); user text goes through `textContent`.
- Only show `detail` from the server when it is a string (`errorText()`).
- Keep the existing naming style in `app.js` (short local names, block comment
  banners between sections).

**CSS**
- Use the existing custom properties. Do not introduce a utility framework.

## Guardrails

- Do not add a dependency without saying why in the same message.
  Test-only dependencies go in `requirements-dev.txt`.
- Do not rewrite `styles.css` or `app.js` wholesale. Targeted edits only.
- Do not change the public API shape without updating `frontend/app.js`,
  `README.md` and the tests in the same change.
- Do not touch `CONBOT_SYSTEM_PROMPT` wording unless asked — it is product copy.
- Anything that changes cost per request (models, token caps, rate limits)
  or exposes a new public endpoint needs a plan first.
- Removal of features (web search, weather, sessions, etc.) can be done directly
  if all cleanup (code, tests, docs) is complete in the same change.

## How to verify a change

```bash
pytest -q

uvicorn app.main:app --reload --port 8000
curl -s localhost:8000/health
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"prompt":"say hi in 3 words"}'
curl -sN localhost:8000/stream -H 'content-type: application/json' \
  -d '{"prompt":"say hi in 3 words"}'

python -m http.server 3000 -d frontend
```

A change is not done until the tests pass and you have run the request path
and pasted the actual output. Do not report success from reading the diff.

## Definition of done

Every feature ships with: input validation, a rate limit, a log line with a
request id (no user text), an error path that returns a safe message, a
regression test, and a `README.md` note if it changes how the app is run.