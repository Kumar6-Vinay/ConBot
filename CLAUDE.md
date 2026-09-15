# ConBOT

A general-purpose AI assistant (conbot.in). FastAPI backend calling OpenRouter
(optional local Ollama fallback), vanilla-JS frontend. Goal: a production chat
product, not a demo.

## Repo map

| Path | What it is |
|---|---|
| `main.py` | Entire FastAPI backend. `/health`, `/ask`, `/stream`. |
| `tests/test_main.py` | Regression tests. No network, no API key. |
| `frontend/index.html` | Single-page shell: sidebar, composer, message list. |
| `frontend/app.js` | All client logic — SSE reader, markdown, sessions, voice, theme. |
| `frontend/styles.css` | All styling. Light/dark via `body.dark` / `body.light`. |
| `Dockerfile` | Backend image only. Frontend deploys to GitHub Pages. |
| `.github/workflows/` | `pages.yml` (frontend deploy), `test.yml` (pytest). |

There is no database and no auth. Rate limits are in-memory, so the backend
must run as a single instance.

## Architecture facts you must not get wrong

- **The server is stateless; the client owns the conversation.** `app.js`
  keeps `history` and replays it on each request. The server trims it to
  `MAX_HISTORY_TURNS` messages, each clipped to `MAX_HISTORY_CHARS`. Trim,
  never reject: a long answer must not break the next question.
- **`/stream` is the primary path** (SSE: `sources`, `delta`, `clarify`,
  `followups`, `truncated`, `error`, `done`). `/ask` is the non-streaming
  equivalent and returns `{answer, web_used, sources, followups, clarify}`.
- **OpenRouter is primary.** Ollama is used only when
  `ALLOW_OLLAMA_FALLBACK=true`, and on `/stream` only if OpenRouter fails
  before the first token. Ollama model names come from `OLLAMA_MODEL_MAP`.
- **The model emits `[[FOLLOWUPS]]` / `[[CLARIFY]]` blocks.** `BlockFilter`
  strips them from prose. Mid-stream, a tag only counts once its line has
  ended (`TAG_LINE_RE`); the end of the buffer is not the end of a line.
  Neither endpoint may ever return a raw tag to the client.
- **Web results are untrusted data.** They go into the final user message
  inside `<search_results>`, never into the system role.
- `AVAILABLE_MODELS` is an allow-list and currently only `text`. Adding a
  mode needs end-to-end support (request body, parser, UI), not just a map entry.
- Client-side session history lives in `localStorage` (`conbot-sessions`)
  with full messages; it never reaches the server except as replayed history.
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
- Anything that changes cost per request (models, search providers, token
  caps, rate limits) or exposes a new public endpoint needs a plan first.

## How to verify a change

```bash
pytest -q

uvicorn main:app --reload --port 8000
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
