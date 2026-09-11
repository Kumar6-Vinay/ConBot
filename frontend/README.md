# CONBOT Frontend Redesign

Premium, Apple-inspired (but original) frontend redesign for CONBOT.

## Files

- `index.html`
- `styles.css`
- `app.js`

## Local development

Run your frontend on port 3000:

```bash
python3 -m http.server 3000
```

Run FastAPI on port 8000.

The frontend automatically uses:

- `http://localhost:8000/ask` on localhost
- `/ask` on production (e.g. `https://conbot.in/ask`)

## Production

Use Cloudflare Tunnel to route:

- `/` → frontend
- `/ask` → FastAPI

No backend changes are required for the frontend redesign.

### Layout update
The hero/chat spacing is tuned so the chat composer appears much earlier on a desktop viewport with less scrolling.
