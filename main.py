from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx
import re
import os
import json
import logging
import time
import uuid
import hashlib
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("conbot")

# httpx logs every request URL at INFO — search URLs contain the user's
# question, which must not reach the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# =========================================================
# APPLICATION
# =========================================================

# The FastAPI instance is created further down, once the lifespan handler
# (startup diagnostics) is defined.


# =========================================================
# CONFIGURATION (FROM ENV VARS)
# =========================================================

DEFAULT_MODEL = "text"

# Only modes that work end to end. The request body carries text only and the
# stream parser reads text deltas only, so image/video/imagegen modes were
# reachable but could never produce a usable answer (and imagegen is paid).
# Re-add them together with attachment support and image rendering.
AVAILABLE_MODELS = {
    "text",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Tolerate a key pasted with surrounding whitespace, quotes, or a "Bearer "
# prefix — all three are common and all three produce a silent 401.
def _clean_key(raw: str) -> str:
    key = raw.strip().strip('"').strip("'").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


OPENROUTER_API_KEY = _clean_key(os.getenv("OPENROUTER_API_KEY", ""))


OPENROUTER_MODEL_MAP = {
    "text": os.getenv("OPENROUTER_TEXT_MODEL", "google/gemma-4-26b-a4b-it:free"),
}


# OpenRouter models that accept image input. A request with an image must go
# to one of these; anything else gets a clear error instead of a silent drop.
# Keep in sync with OPENROUTER_MODEL_MAP as models change.
VISION_MODELS = {
    m.strip() for m in os.getenv(
        "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free",
    ).split(",") if m.strip()
}


def model_supports_vision(mode: str) -> bool:
    return OPENROUTER_MODEL_MAP.get(mode, mode) in VISION_MODELS


# Timeouts (in seconds)
OPENROUTER_TIMEOUT = 60


# =========================================================
# RATE LIMITING
#
# /ask and /stream are public and unauthenticated, and each request costs
# real OpenRouter credit. Without a limit, one script in a browser console
# can drain the key. This is a fixed-window counter per client IP, held in
# memory — no extra service, no extra dependency. It resets if the process
# restarts, and it is per-instance if this ever runs on more than one, which
# is the honest limit of "no infrastructure" rate limiting. It stops a
# casual script; it is not a defense against a determined, distributed abuser.
# =========================================================

RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))        # requests
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "600"))  # seconds (10 min)

# Global daily cap = the prototype's cost ceiling. The per-IP daily cap stops
# one visitor from spending the whole day's allowance for everyone.
DAILY_REQUEST_LIMIT = int(os.getenv("DAILY_REQUEST_LIMIT", "45"))
DAILY_PER_IP_LIMIT = int(os.getenv("DAILY_PER_IP_LIMIT", "15"))

# How the client address is found behind proxies.
#  - CLIENT_IP_HEADER: a header your edge overwrites (never passes through),
#    e.g. "cf-connecting-ip" behind Cloudflare. Takes priority when set.
#  - TRUSTED_PROXY_HOPS: otherwise, how many proxies append to
#    X-Forwarded-For. The client can put anything at the LEFT of that header,
#    so we count from the RIGHT. Verify on your host: log the header once.
CLIENT_IP_HEADER = os.getenv("CLIENT_IP_HEADER", "").strip().lower()
TRUSTED_PROXY_HOPS = max(0, int(os.getenv("TRUSTED_PROXY_HOPS", "1")))

_rate_buckets: dict[str, deque] = defaultdict(deque)
_daily_per_ip: dict[str, int] = defaultdict(int)
_daily_request_count = 0
_daily_request_day: Optional[str] = None


def client_ip(request: Request) -> str:
    """Best-effort client address for rate limiting — never for auth."""
    if CLIENT_IP_HEADER:
        value = (request.headers.get(CLIENT_IP_HEADER) or "").strip()
        if value:
            return value

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and TRUSTED_PROXY_HOPS:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            # The entry our nearest trusted proxy appended is the last one.
            index = max(0, len(hops) - TRUSTED_PROXY_HOPS)
            return hops[index]

    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, request_id: str) -> None:
    global _daily_request_count, _daily_request_day

    today = time.strftime("%Y-%m-%d", time.gmtime())
    if today != _daily_request_day:
        _daily_request_day = today
        _daily_request_count = 0
        _daily_per_ip.clear()

    if _daily_request_count >= DAILY_REQUEST_LIMIT:
        logger.warning("[%s] rate_limit=daily_global count=%d", request_id, _daily_request_count)
        raise HTTPException(
            status_code=429,
            detail=(
                "ConBOT is a prototype with a small shared daily allowance, "
                "and it has been used up for today. Please try again tomorrow."
            ),
        )

    ip = client_ip(request)

    if _daily_per_ip[ip] >= DAILY_PER_IP_LIMIT:
        logger.warning("[%s] rate_limit=daily_ip", request_id)
        raise HTTPException(
            status_code=429,
            detail="You've reached today's question limit for this prototype. Please come back tomorrow.",
        )

    now = time.monotonic()
    bucket = _rate_buckets[ip]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        logger.warning("[%s] rate_limit=window in_window=%d", request_id, len(bucket))
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short time. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
    _daily_per_ip[ip] += 1
    _daily_request_count += 1

    # Bound memory: an unbounded number of distinct IPs would otherwise
    # accumulate forever on a long-running process.
    if len(_rate_buckets) > 5000:
        stale = [k for k, v in _rate_buckets.items() if not v]
        for k in stale[:2000]:
            del _rate_buckets[k]


# =========================================================
# STARTUP DIAGNOSTICS
# =========================================================

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """One line at boot that says whether this instance can answer at all."""
    if OPENROUTER_API_KEY:
        logger.info(
            "startup openrouter=configured key_suffix=...%s",
            OPENROUTER_API_KEY[-4:], 
        )
    else:
        logger.error(
            "startup openrouter=MISSING — configure OPENROUTER_API_KEY to enable the service."
        )
    yield


app = FastAPI(
    title="ConBOT API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


# =========================================================
# CORS (FIXED FOR FRONTEND)
# =========================================================

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://conbot.in",
    "https://www.conbot.in",
    "https://llama-chatbot-fe.onrender.com",
    "https://kumar6-vinay.github.io",
]

# Comma-separated override, e.g. to add a GitHub Pages origin
# (https://<username>.github.io — CORS matches the origin, not the path).
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# =========================================================
# CONBOT BEHAVIOUR
# =========================================================

CONBOT_SYSTEM_PROMPT = """
You are ConBOT, a helpful AI assistant for everyday users.

Your purpose is to help people ask questions, learn,
understand ideas, solve everyday problems, and explore
information clearly.

Follow these principles:

1. Answer the user's actual question directly.

2. Prefer simple, clear language before technical detail.

3. Use short paragraphs and helpful lists when appropriate.

4. Do not mention Docker, APIs, models, infrastructure, or internal implementation details.

5. Do not claim to have access to information, tools,
   websites, files, or personal data that you do not have.

6. Do not invent facts.

7. When web information is supplied, use it as the source
   of current information. Do not contradict reliable
   search results using your own outdated knowledge.

8. If web sources disagree, clearly explain the disagreement.

9. For questions involving law, tax, finance, health,
   safety, or other high-impact decisions, provide useful
   general information but clearly indicate that important
   decisions should be verified with an appropriate
   authoritative or qualified source.

10. If a question depends on a country, location, date,
    or other important context that has not been provided,
    do not silently assume the answer.

11. If the user asks for an explanation, start with the
    simplest explanation and then provide an example when
    useful.

12. Keep answers short by default: usually 2–5 short paragraphs
    or bullets, and roughly under 350 words unless the user
    asks for more detail.

13. Do not unnecessarily repeat the user's question.

14. Do not use fake citations, fake sources, or invented
    references.

15. Be helpful, respectful, and natural.

16. Reply in the same language and script the user wrote in. If they
    write in Hindi, reply in Hindi. If they write romanised Hindi or
    mix Hindi and English ("mujhe PAN card ke baare mein batao"),
    reply the same way — do not switch them to formal English or to
    Devanagari they did not use. The same applies to any other
    language.

HOW TO SHAPE AN ANSWER

Lead with the answer. The first one or two sentences must answer what
was actually asked. Definitions, background and caveats come after, if
they are needed at all. Never open by restating the question.

Then add only the structure the answer needs — short paragraphs, or a
list when the content really is a list.

WHEN THE QUESTION IS UNDERSPECIFIED

If a materially different answer would follow from a detail the user
has not given — which tax regime, which state, which year, which
board — do not guess. Reply with ONLY this block and nothing else:

[[CLARIFY]]
question: <one short question>
- <option>
- <option>
- <option>

Ask one question, never several, with two to four options. Use this
sparingly: only when guessing would likely produce a wrong answer, not
merely when more detail would be nice to have.

AFTER A COMPLETE ANSWER

End every complete answer with this block:

[[FOLLOWUPS]]
- <question>
- <question>

Two or three questions, each a real gap this answer just opened — the
thing a thoughtful reader would now want to know, phrased as they
would type it. Never generic ("tell me more", "any other questions").
Never something the answer already covered. Write them in the same
language as the answer.

Return only the answer intended for the user, plus these blocks.
"""


# =========================================================
# REQUEST MODEL
# =========================================================

MAX_PROMPT_CHARS = 3000

# Image input. The client sends a base64 data URL; the ceiling is on the
# encoded string, which is ~33% larger than the raw file. 4 MB of file is
# ~5.5 MB of base64, so allow a little headroom.
MAX_IMAGE_MB = float(os.getenv("MAX_IMAGE_MB", "4"))
MAX_IMAGE_CHARS = int(MAX_IMAGE_MB * 1024 * 1024 * 4 / 3) + 2048
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# data:image/png;base64,AAAA...  — capture the mime type and confirm base64.
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,[A-Za-z0-9+/=\s]+$")

# How much conversation to carry, and how much of each message. These cap
# cost and latency. The server TRIMS to them; it does not reject — a long
# answer must never break the next question.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))
MAX_HISTORY_CHARS = int(os.getenv("MAX_HISTORY_CHARS", "3000"))

# Hard ceilings that only stop abusive payloads, well above anything the
# client sends after its own trimming.
HISTORY_ITEM_CEILING = 20000
HISTORY_LEN_CEILING = 50


class Turn(BaseModel):
    """One prior exchange. Sent by the client; the server keeps no state."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=HISTORY_ITEM_CEILING)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    model: str = Field(default=DEFAULT_MODEL, max_length=50)
    history: List[Turn] = Field(default_factory=list, max_length=HISTORY_LEN_CEILING)
    # Optional image as a base64 data URL. Sent to the model with this one
    # question only; never stored in history. Pydantic checks the ceiling so
    # an oversized body is rejected before it reaches any handler.
    image: Optional[str] = Field(default=None, max_length=MAX_IMAGE_CHARS)
    # Sent by the browser. Neither is precise location and neither needs a
    # permission prompt — a timezone is city-level at best.
    timezone: Optional[str] = Field(default=None, max_length=64)
    language: Optional[str] = Field(default=None, max_length=32)


# =========================================================
# LOCATION
# =========================================================

# Country code -> name. Only what the region tag of navigator.language
# commonly produces; anything else falls through to the raw code.
COUNTRY_NAMES = {
    "IN": "India", "US": "the United States", "GB": "the United Kingdom",
    "CA": "Canada", "AU": "Australia", "NZ": "New Zealand", "IE": "Ireland",
    "SG": "Singapore", "AE": "the United Arab Emirates", "SA": "Saudi Arabia",
    "DE": "Germany", "FR": "France", "ES": "Spain", "IT": "Italy",
    "NL": "the Netherlands", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "PL": "Poland", "PT": "Portugal", "CH": "Switzerland",
    "AT": "Austria", "BE": "Belgium", "CZ": "Czechia", "GR": "Greece",
    "JP": "Japan", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan",
    "KR": "South Korea", "TH": "Thailand", "VN": "Vietnam", "ID": "Indonesia",
    "MY": "Malaysia", "PH": "the Philippines", "PK": "Pakistan",
    "BD": "Bangladesh", "LK": "Sri Lanka", "NP": "Nepal",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "EG": "Egypt",
    "BR": "Brazil", "MX": "Mexico", "AR": "Argentina", "CL": "Chile",
    "CO": "Colombia", "RU": "Russia", "TR": "Turkey", "IL": "Israel",
    "UA": "Ukraine",
}

# Timezones that pin a country when the language tag has no region
# (a user with "en" but "Asia/Kolkata" is still in India).
TIMEZONE_COUNTRIES = {
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Karachi": "PK",
    "Asia/Dhaka": "BD", "Asia/Colombo": "LK", "Asia/Kathmandu": "NP",
    "Asia/Dubai": "AE", "Asia/Singapore": "SG", "Asia/Tokyo": "JP",
    "Asia/Shanghai": "CN", "Asia/Hong_Kong": "HK", "Asia/Seoul": "KR",
    "Asia/Bangkok": "TH", "Asia/Jakarta": "ID", "Asia/Manila": "PH",
    "Europe/London": "GB", "Europe/Dublin": "IE", "Europe/Berlin": "DE",
    "Europe/Paris": "FR", "Europe/Madrid": "ES", "Europe/Rome": "IT",
    "Europe/Amsterdam": "NL", "Europe/Stockholm": "SE", "Europe/Oslo": "NO",
    "Europe/Zurich": "CH", "Europe/Lisbon": "PT", "Europe/Warsaw": "PL",
    "Europe/Moscow": "RU", "Europe/Istanbul": "TR", "Europe/Kyiv": "UA",
    "Africa/Johannesburg": "ZA", "Africa/Lagos": "NG", "Africa/Nairobi": "KE",
    "Africa/Cairo": "EG", "America/Toronto": "CA", "America/Vancouver": "CA",
    "America/Sao_Paulo": "BR", "America/Mexico_City": "MX",
    "America/Argentina/Buenos_Aires": "AR", "America/Bogota": "CO",
    "America/Santiago": "CL", "Australia/Sydney": "AU",
    "Australia/Melbourne": "AU", "Pacific/Auckland": "NZ",
    "Asia/Jerusalem": "IL", "Asia/Riyadh": "SA",
}

# Browsers still report these older IANA names.
TIMEZONE_ALIASES = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Europe/Kiev": "Europe/Kyiv",
    "Asia/Dacca": "Asia/Dhaka",
}

# Used when the browser sends nothing at all.
FALLBACK_TIMEZONE = os.getenv("FALLBACK_TIMEZONE", "Asia/Kolkata")


def resolve_location(timezone: Optional[str], language: Optional[str]) -> dict:
    """Turn the browser's timezone and language tag into a place description.

    Neither input is trusted for anything but prompt context, so a bad value
    degrades to a vaguer answer rather than an error.
    """
    tz = (timezone or "").strip() or FALLBACK_TIMEZONE
    if not re.fullmatch(r"[A-Za-z_+\-/]{1,64}", tz):
        tz = FALLBACK_TIMEZONE
    tz = TIMEZONE_ALIASES.get(tz, tz)

    # Timezone first: it says where the device physically is. The language
    # region tag only says how the OS is configured, so it is the fallback.
    code = TIMEZONE_COUNTRIES.get(tz)

    if not code:
        lang = (language or "").strip()
        match = re.fullmatch(r"([a-zA-Z]{2,3})[-_]([A-Za-z]{2})", lang)
        if match:
            code = match.group(2).upper()

    # "Asia/Kolkata" -> "Kolkata"; a coarse city, not a precise one.
    city = tz.split("/")[-1].replace("_", " ") if "/" in tz else None

    return {
        "timezone": tz,
        "city": city,
        "country": COUNTRY_NAMES.get(code, code) if code else None,
    }


def build_locale_note(loc: dict) -> str:
    """The block prepended to every prompt so answers are local by default."""
    where = loc["country"] or f"the {loc['timezone']} timezone"
    city_line = f"Their nearest major city is roughly {loc['city']}.\n" if loc["city"] else ""

    return f"""
WHERE THE USER IS

The user is in {where}. {city_line}Their timezone is {loc["timezone"]}.

Answer for that place by default, in every kind of question — not only money.
That means local currency and units, local laws, taxes, rules and regulators,
local institutions, services, providers and brands that actually operate there,
local exam systems, holidays, seasons and conventions, and examples the user
would recognise.

Do not give answers framed around a different country unless the user asks
about one. If the user names another place, follow them instead.

Their location is inferred from their device settings, so it is approximate.
If a precise location would change the answer materially — a specific address,
branch, or local office — say what you are assuming and ask.

LANGUAGE

Reply in the same language and script the user wrote in. If they write in
Hindi, reply in Hindi. If they write romanised Hindi or a mix of Hindi and
English — "mera PAN card kaise banega" — reply the same way, naturally, not in
formal English and not in Devanagari unless they used it. Keep technical terms
in English where that is how people actually say them.
""".strip()


# =========================================================
# STRUCTURED BLOCKS IN A STREAM
# =========================================================

CLARIFY_TAG = "[[CLARIFY]]"
FOLLOWUPS_TAG = "[[FOLLOWUPS]]"

# Matches [[FOLLOWUPS]], [[FOLLOW-UPS]], **FOLLOWUPS:**, FOLLOWUPS: and the
# same shapes for CLARIFY — at a line start only.
_TAG_BODY = (
    r"(?:^|\n)[ \t]*[\*_]{0,2}\[{0,2}[ \t]*"
    r"(?P<name>FOLLOW[ \-_]?UPS?|CLARIFY)"
    r"[ \t]*\]{0,2}[\*_]{0,2}[ \t]*:?[ \t]*[\*_]{0,2}[ \t]*"
)

# Complete text: a tag line may end at a newline or at the end of the text.
TAG_RE = re.compile(_TAG_BODY + r"(?=\n|$)", re.IGNORECASE)

# Mid-stream: the buffer end is NOT the end of the line — "Followup" may be
# the start of "Followup care…". Only a line that has actually ended counts.
TAG_LINE_RE = re.compile(_TAG_BODY + r"(?=\n)", re.IGNORECASE)

# Longest tag shape we might have to hold back mid-stream.
_TAG_GUARD = 24


class BlockFilter:
    """Strip the structured blocks out of a streaming answer.

    The model writes prose, then a tagged block. We must never emit even a
    partial tag to the client, so the last few characters are always held
    back until they are known not to be the start of one.

    A CLARIFY block replaces the answer entirely, so nothing is emitted
    until we know the reply does not begin with that tag.
    """

    def __init__(self) -> None:
        self.raw = ""          # everything the model produced
        self.held = ""         # not yet released to the client
        self.released = 0      # chars of prose already sent
        self.in_block = False  # a tag has been seen; prose is over
        self.decided = False   # we know whether this is a CLARIFY reply

    def feed(self, piece: str) -> str:
        self.raw += piece
        if self.in_block:
            return ""

        self.held += piece

        # Until the first line is complete (or clearly too long to be a tag),
        # hold everything — otherwise the first words of a clarify block leak.
        if not self.decided:
            stripped = self.held.lstrip()
            if "\n" not in stripped and len(stripped) < _TAG_GUARD:
                return ""
            opener = TAG_LINE_RE.match("\n" + stripped)
            if opener and opener.group("name").upper() == "CLARIFY":
                self.in_block = True
                return ""
            self.decided = True

        # Search from a little before the release point: the newline that
        # starts a tag may already have been released.
        found = TAG_LINE_RE.search(self.held, max(0, self.released - 1))
        if found:
            out = self.held[self.released:max(self.released, found.start())]
            self.released = len(self.held)
            self.in_block = True
            return out

        # Hold back a tail that could still turn into a tag.
        safe_end = max(self.released, len(self.held) - _TAG_GUARD)
        out = self.held[self.released:safe_end]
        self.released = safe_end
        return out

    def flush(self) -> str:
        """Release anything held back once the stream ends."""
        if self.in_block:
            return ""
        rest = self.held[self.released:]
        self.released = len(self.held)

        if not self.decided:
            # A very short reply that is only a tag line.
            opener = TAG_RE.match("\n" + rest.lstrip())
            if opener and opener.group("name").upper() == "CLARIFY":
                self.in_block = True
                return ""

        # Now the buffer end really is the end — a tag may sit there.
        found = TAG_RE.search(rest)
        if found:
            self.in_block = True
            return rest[:found.start()]
        return rest

    # -- parsing the blocks once the stream is done --------------------

    def _block(self, want: str) -> Optional[str]:
        for found in TAG_RE.finditer(self.raw):
            name = found.group("name").upper().replace("-", "").replace("_", "").replace(" ", "")
            if name.rstrip("S") != want.rstrip("S"):
                continue
            rest = self.raw[found.end():]
            nxt = TAG_RE.search(rest)
            return (rest if not nxt else rest[:nxt.start()]).strip()
        return None

    def followups(self) -> List[str]:
        body = self._block("FOLLOWUPS")
        if not body:
            return []
        items = []
        for line in body.split("\n"):
            line = line.strip().lstrip("-*").strip()
            line = re.sub(r"^\d+[.)]\s*", "", line)
            if 8 <= len(line) <= 120:
                items.append(line)
        return items[:2]

    def clarify(self) -> Optional[dict]:
        body = self._block("CLARIFY")
        if not body:
            return None

        question, options = None, []
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("question:"):
                question = line.split(":", 1)[1].strip()
            elif line.startswith(("-", "*")):
                option = line.lstrip("-*").strip()
                if option:
                    options.append(option)

        if not question or len(options) < 2:
            return None
        return {"question": question, "options": options[:4]}


def base_prompt(loc: dict) -> str:
    """System prompt plus the locale block. Use this everywhere, not the raw prompt."""
    return CONBOT_SYSTEM_PROMPT.strip() + "\n\n" + build_locale_note(loc)


# =========================================================
# MESSAGE ASSEMBLY
# =========================================================

def clip(text: str, limit: int) -> str:
    """Keep the start of a long message — that is where its point usually is."""
    return text if len(text) <= limit else text[:limit].rstrip() + " …[trimmed]"


def validate_image(image: Optional[str]) -> Optional[str]:
    """Return the data URL if it is a well-formed, allowed image, else raise.

    The Pydantic ceiling already bounds the length; here we confirm it is a
    base64 image data URL of a type the vision models accept.
    """
    if not image:
        return None
    match = _DATA_URL_RE.match(image.strip())
    if not match or match.group(1).lower() not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="That image could not be read. Please attach a PNG, JPEG, WebP or GIF.",
        )
    return image.strip()


def build_messages(
    system: str,
    history: List[Turn],
    question: str,
    context: Optional[str] = None,
    image: Optional[str] = None,
) -> List[dict]:
    """System prompt, then the conversation so far, then the new question.

    The server stores nothing — the client replays history, trimmed here so a
    long chat cannot inflate cost or latency without limit. Web results, when
    present, travel inside the final user message as clearly-labelled data,
    never in the system role.
    """
    messages = [{"role": "system", "content": system}]

    recent = history[-MAX_HISTORY_TURNS:]
    # Chat APIs expect the conversation to open with a user turn.
    while recent and recent[0].role != "user":
        recent = recent[1:]
    for turn in recent:
        messages.append({"role": turn.role, "content": clip(turn.content, MAX_HISTORY_CHARS)})

    final = question if not context else f"{context}\n\nMY QUESTION:\n{question}"
    if image:
        # Vision request: the final turn carries text + the image. Images are
        # never added to history, so this only ever affects the current turn.
        messages.append({"role": "user", "content": [
            {"type": "text", "text": final},
            {"type": "image_url", "image_url": {"url": image}},
        ]})
    else:
        messages.append({"role": "user", "content": final})

    # Smaller models reliably drop an instruction buried in a long system
    # prompt. Repeating it as the last thing they read is what makes it stick.
    messages.append({
        "role": "system",
        "content": (
            "Reminder: after the answer, end your reply with this block, "
            "exactly as written:\n\n"
            "[[FOLLOWUPS]]\n- <question>\n- <question>\n\n"
            "Two specific questions this answer just opened, in the "
            "same language as the answer. This block is required. If instead "
            "you need one detail before you can answer at all, reply with "
            "only a [[CLARIFY]] block."
        ),
    })
    return messages



# =========================================================
# OPENROUTER (PRIMARY)
# =========================================================

# Devanagari and other non-Latin scripts tokenize far less efficiently than
# English — the same answer can cost 3-4x the tokens. A cap tuned for English
# silently truncates Hindi mid-sentence.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1200"))


def openrouter_payload(messages: List[dict], model: str, stream: bool) -> dict:
    return {
        "model": OPENROUTER_MODEL_MAP.get(model, model),
        "messages": messages,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.7,
        "stream": stream,
    }


OPENROUTER_HEADERS = {"Content-Type": "application/json"}


def auth_headers() -> dict:
    return {**OPENROUTER_HEADERS, "Authorization": f"Bearer {OPENROUTER_API_KEY}"}


async def ask_openrouter(messages: List[dict], model: str, request_id: str) -> str:
    """Non-streaming call. Used by /ask."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_URL,
                json=openrouter_payload(messages, model, stream=False),
                headers=auth_headers(),
                timeout=OPENROUTER_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and data.get("error"):
                raise ValueError(f"OpenRouter error payload: {data['error']}")

            answer = data["choices"][0]["message"]["content"]

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty OpenRouter response")

            logger.info(f"[{request_id}] OpenRouter success")
            return answer.strip()

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] OpenRouter timeout after {OPENROUTER_TIMEOUT}s")
        raise
    except httpx.HTTPStatusError as e:
        # HTTPStatusError has no .status_code — it is on .response.
        logger.error(
            f"[{request_id}] OpenRouter HTTP {e.response.status_code}: "
            f"{e.response.text[:500]}"
        )
        raise
    except Exception as e:
        logger.error(f"[{request_id}] OpenRouter error: {type(e).__name__}: {e}")
        raise


async def stream_openrouter(
    messages: List[dict],
    model: str,
    request_id: str,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Yield answer text as it arrives. Raises before the first token if the
    upstream call fails, so the caller can still return a clean error."""

    async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT) as client:
        async with client.stream(
            "POST",
            OPENROUTER_URL,
            json=openrouter_payload(messages, model, stream=True),
            headers=auth_headers(),
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                logger.error(
                    f"[{request_id}] OpenRouter HTTP {response.status_code}: {body[:500]}"
                )
                response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break

                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                if data.get("error"):
                    raise ValueError(f"OpenRouter error payload: {data['error']}")

                for choice in data.get("choices", []):
                    # "length" means the token cap cut the answer off, not
                    # that the model finished. The UI needs to say so.
                    if state is not None and choice.get("finish_reason"):
                        state["finish_reason"] = choice["finish_reason"]

                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        yield piece



# =========================================================
# DISPATCH
# =========================================================

# =========================================================
# DISPATCH
# =========================================================

def no_llm_error() -> HTTPException:
    logger.error("OPENROUTER_API_KEY is not set — check the deployed environment")
    return HTTPException(
        status_code=503, detail="ConBOT is not configured to answer questions yet."
    )


async def get_ai_answer(messages: List[dict], model: str, request_id: str) -> str:
    if not OPENROUTER_API_KEY:
        raise no_llm_error()
    try:
        return await ask_openrouter(messages, model, request_id)
    except Exception as e:
        logger.warning(
            f"[{request_id}] OpenRouter failed: {type(e).__name__}: {str(e)[:500]}"
        )
        raise HTTPException(
            status_code=502,
            detail="ConBOT could not answer that right now. Please try again shortly.",
        )


async def stream_answer(
    messages: List[dict],
    model: str,
    request_id: str,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Stream the answer directly from OpenRouter."""
    if not OPENROUTER_API_KEY:
        raise no_llm_error()

    async for piece in stream_openrouter(messages, model, request_id, state):
        yield piece



# =========================================================
# =========================================================
# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health() -> dict:
    """Report whether the OpenRouter service is configured."""
    return {
        "status": "healthy" if OPENROUTER_API_KEY else "degraded",
        "llm_configured": bool(OPENROUTER_API_KEY),
    }



# =========================================================
# SHARED PREPARATION
# =========================================================

def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def validate_model(request: ChatRequest, request_id: str) -> None:
    """Checked before rate limiting, so a bad request doesn't use up quota."""
    if request.model not in AVAILABLE_MODELS:
        logger.warning("[%s] invalid_model", request_id)
        raise HTTPException(status_code=400, detail="Unsupported model.")


def question_fingerprint(question: str) -> str:
    """Enough to correlate log lines without storing what the user asked."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:10]


async def prepare(request: ChatRequest, request_id: str) -> dict:
    """Prepare location context and messages for the OpenRouter model."""

    question = request.prompt.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question.")

    image = validate_image(request.image)
    if image and not model_supports_vision(request.model):
        raise HTTPException(
            status_code=400,
            detail="This model can't read images. Please remove the image and ask in text.",
        )
    if image and not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Image questions aren't available right now. Please ask in text.",
        )

    loc = resolve_location(request.timezone, request.language)
    system = base_prompt(loc)

    logger.info(
        "[%s] request q_hash=%s q_len=%d model=%s country=%s history=%d image=%s",
        request_id, question_fingerprint(question), len(question),
        request.model, loc["country"], len(request.history), bool(image),
    )

    return {
        "messages": build_messages(system, request.history, question, None, image),
        "sources": [],
    }


# =========================================================
# ASK (NON-STREAMING)
# =========================================================

@app.post("/ask")
async def ask(request: ChatRequest, http_request: Request) -> dict:
    """Whole answer in one response. Kept for clients that cannot stream.

    Returns {answer, web_used, sources, followups, clarify}. `answer` is prose
    only — the structured blocks are parsed out, never shown raw.
    """
    request_id = new_request_id()
    validate_model(request, request_id)
    enforce_rate_limit(http_request, request_id)
    prepared = await prepare(request, request_id)

    raw = await get_ai_answer(prepared["messages"], request.model, request_id)

    blocks = BlockFilter()
    answer = (blocks.feed(raw) + blocks.flush()).strip()
    clarify = blocks.clarify()

    if clarify:
        answer = clarify["question"]
    elif not answer:
        logger.warning("[%s] ask=empty_answer", request_id)
        raise HTTPException(status_code=502, detail="ConBOT returned an empty answer. Please try again.")

    logger.info("[%s] ask=complete clarify=%s", request_id, bool(clarify))
    return {
        "answer": answer,
        "web_used": bool(prepared["sources"]),
        "sources": prepared["sources"],
        "followups": [] if clarify else blocks.followups(),
        "clarify": clarify,
    }


# =========================================================
# STREAM
# =========================================================

def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/stream")
async def stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """Server-sent events: sources first, then answer text as it is generated."""

    request_id = new_request_id()
    validate_model(request, request_id)

    # Check configuration before the response starts. Once headers are sent
    # the status code is fixed, so a 503 raised inside the generator would
    # reach the client as a 200 with an error event.
    if not OPENROUTER_API_KEY:
        raise no_llm_error()

    enforce_rate_limit(http_request, request_id)
    prepared = await prepare(request, request_id)
    async def events() -> AsyncIterator[str]:
        if prepared["sources"]:
            yield sse({"type": "sources", "sources": prepared["sources"]})

        produced = False
        state = {}
        blocks = BlockFilter()
        try:
            async for piece in stream_answer(
                prepared["messages"], request.model, request_id, state
            ):
                visible = blocks.feed(piece)
                if visible:
                    produced = True
                    yield sse({"type": "delta", "text": visible})

            tail = blocks.flush()
            if tail:
                produced = True
                yield sse({"type": "delta", "text": tail})

        except Exception as e:
            logger.warning(
                "[%s] stream=failed type=%s produced=%s", request_id, type(e).__name__, produced
            )
            # Nothing sent yet — a clean error still reads well in the UI.
            # Mid-stream, the client keeps what it has and shows the notice.
            yield sse({
                "type": "error",
                "detail": "ConBOT could not finish that answer. Please try again.",
            })
            return

        clarify = blocks.clarify()
        if clarify:
            # A clarify reply has no prose at all — the question is the answer.
            logger.info("[%s] stream=clarify", request_id)
            yield sse({"type": "clarify", **clarify})
            yield sse({"type": "done"})
            return

        if not produced:
            yield sse({"type": "error", "detail": "ConBOT returned an empty answer."})
            return

        if state.get("finish_reason") == "length":
            logger.info("[%s] stream=truncated", request_id)
            yield sse({"type": "truncated"})
        else:
            followups = blocks.followups()
            if followups:
                yield sse({"type": "followups", "questions": followups})

        logger.info("[%s] stream=complete", request_id)
        yield sse({"type": "done"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # stop proxies buffering the stream
            "Connection": "keep-alive",
        },
    )