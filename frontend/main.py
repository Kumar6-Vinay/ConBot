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
from collections import defaultdict, deque
from typing import AsyncIterator, List, Optional

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="ConBOT API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# =========================================================
# CONFIGURATION (FROM ENV VARS)
# =========================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")

DEFAULT_MODEL = "qwen3:14b"

AVAILABLE_MODELS = {
    "qwen3:14b",
    "llama3:latest",
    "mistral:latest",
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

# Ollama runs on the host during local development. There is no Ollama on a
# managed host, so falling back to it there turns every upstream failure into a
# misleading "AI service unavailable." Set this to true only for local dev.
ALLOW_OLLAMA_FALLBACK = os.getenv("ALLOW_OLLAMA_FALLBACK", "false").lower() == "true"

OPENROUTER_MODEL_MAP = {
     "text": "nvidia/nemotron-3-ultra:free",
     "image": "google/gemma-4-26b-a4b-it:free",
     "video": "nvidia/nemotron-3-nano-omni:free",
     "imagegen" = "black-forest-labs/flux.2-klein-4b:free"
}

# DuckDuckGo Search API
DUCKDUCKGO_URL = "https://api.duckduckgo.com/"

# Weather APIs (Open-Meteo - free, no API key)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Timeouts (in seconds)
OPENROUTER_TIMEOUT = 60
OLLAMA_TIMEOUT = 120
SEARCH_TIMEOUT = 10


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

_rate_buckets: dict[str, deque] = defaultdict(deque)

DAILY_REQUEST_LIMIT = int(os.getenv("DAILY_REQUEST_LIMIT", "45"))
_daily_request_count = 0
_daily_request_day = None


def client_ip(request: Request) -> str:


    
    """Render sits behind a proxy, so the socket IP is Render's own edge,
    not the visitor's. The real address is the first hop in
    X-Forwarded-For; trust it here because Render sets it itself rather
    than passing through whatever the client sent."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, request_id: str) -> None:
    global _daily_request_count, _daily_request_day

    today = time.strftime("%Y-%m-%d", time.gmtime())

    if today != _daily_request_day:
        _daily_request_day = today
        _daily_request_count = 0

    if _daily_request_count >= DAILY_REQUEST_LIMIT:
        logger.warning(f"[{request_id}] Daily request limit reached")
        raise HTTPException(
            status_code=429,
            detail="CONBOT has reached today's prototype usage limit. Please wait until tomorrow.",
        )

    ip = client_ip(request)
    now = time.monotonic()
    bucket = _rate_buckets[ip]

    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        logger.warning(f"[{request_id}] Rate limited: {ip} ({len(bucket)} in window)")
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short time. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
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

@app.on_event("startup")
async def log_configuration() -> None:
    """One line at boot that says whether this instance can answer at all."""
    if OPENROUTER_API_KEY:
        logger.info(
            "Startup: OpenRouter configured (key ends ...%s), ollama_fallback=%s",
            OPENROUTER_API_KEY[-4:],
            ALLOW_OLLAMA_FALLBACK,
        )
    else:
        logger.error(
            "Startup: OPENROUTER_API_KEY is NOT set. "
            "Every request will fail until it is added to the environment. "
            "ollama_fallback=%s",
            ALLOW_OLLAMA_FALLBACK,
        )


# =========================================================
# CORS (FIXED FOR FRONTEND)
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://conbot.in",
        "https://www.conbot.in",
        "https://llama-chatbot-fe.onrender.com",
        # GitHub Pages origin — REPLACE <username> with your GitHub username.
        # Pages serves from https://<username>.github.io (and, for a project
        # repo, the path /ConBot/, but CORS matches the origin only, so the
        # bare github.io origin is what must be listed).
        "https://YOUR_GITHUB_USERNAME.github.io",
    ],
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

4. Do not mention Llama, Ollama, Docker, APIs, models,
   infrastructure, or internal implementation details.

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

class Turn(BaseModel):
    """One prior exchange. Sent by the client; the server keeps no state."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=3000)


# How much conversation to carry. Caps cost and latency per request.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=3000)
    model: str = Field(default=DEFAULT_MODEL, max_length=50)
    history: List[Turn] = Field(default_factory=list, max_length=16)
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
TAG_RE = re.compile(
    r"(?:^|\n)[ \t]*[\*_]{0,2}\[{0,2}[ \t]*"
    r"(?P<name>FOLLOW[ \-_]?UPS?|CLARIFY)"
    r"[ \t]*\]{0,2}[\*_]{0,2}[ \t]*:?[ \t]*(?=\n|$)",
    re.IGNORECASE,
)

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

        # Until we have enough characters to rule out "[[CLARIFY]]", hold
        # everything — otherwise the first words of a clarify block leak.
        if not self.decided:
            stripped = self.held.lstrip()
            if len(stripped) < _TAG_GUARD and not stripped.count("\n"):
                # Too early to tell — a clarify tag may still be forming.
                if re.match(r"[\*_\[ \t]*C?L?A?R?I?F?Y?", stripped, re.I) \
                        and len(stripped) < len(CLARIFY_TAG):
                    return ""
            opener = TAG_RE.match("\n" + stripped)
            if opener and opener.group("name").upper() == "CLARIFY":
                self.in_block = True
                return ""
            self.decided = True

        found = TAG_RE.search(self.held)
        if found:
            out = self.held[self.released:found.start()]
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
        out = self.held[self.released:]
        self.released = len(self.held)
        return out

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
# CURRENT INFORMATION DETECTION
# =========================================================

def needs_web_search(question: str) -> bool:
    question_lower = question.lower().strip()

    current_patterns = [
        r"\btoday\b",
        r"\btonight\b",
        r"\bnow\b",
        r"\bright now\b",
        r"\bcurrently\b",
        r"\bcurrent\b",
        r"\blatest\b",
        r"\brecent\b",
        r"\brecently\b",
        r"\bthis week\b",
        r"\bthis month\b",
        r"\bthis year\b",
        r"\byesterday\b",
        r"\btomorrow\b",
        r"\bnews\b",
        r"\bupdate\b",
        r"\bupdates\b",
        r"\bwhat happened\b",
        r"\bwhat's happening\b",
        r"\bwhats happening\b",
        r"\bprice\b",
        r"\bpricing\b",
        r"\bcost\b",
        r"\bworth\b",
        r"\bstock\b",
        r"\bshare price\b",
        r"\bbitcoin\b",
        r"\bcryptocurrency\b",
        r"\bgold price\b",
        r"\bweather\b",
        r"\btemperature\b",
        r"\btemp\b",
        r"\bforecast\b",
        r"\bscore\b",
        r"\bmatch today\b",
        r"\bgame today\b",
        r"\bplaying today\b",
        r"\bwon today\b",
        r"\bwho won\b",
        r"\blatest law\b",
        r"\bnew law\b",
        r"\bnew rules\b",
        r"\bnew rule\b",
        r"\bgovernment announcement\b",
        r"\bpolicy update\b",
        r"\bvisa rules\b",
        r"\bvisa rule\b",
        r"\bin stock\b",
        r"\bavailable now\b",
        r"\bavailability\b",
        r"\bdeal\b",
        r"\bdeals\b",
        r"\blatest version\b",
        r"\bnew version\b",
        r"\bnew release\b",
        r"\breleased\b",
        r"\brelease date\b",
    ]

    for pattern in current_patterns:
        if re.search(pattern, question_lower):
            return True

    return False


# =========================================================
# WEATHER DETECTION & API
# =========================================================

def is_weather_question(question: str) -> bool:
    """Check if the question is about weather."""
    weather_keywords = [
        r"\bweather\b",
        r"\btemperature\b",
        r"\btemp\b",
        r"\bhow hot\b",
        r"\bhow cold\b",
        r"\bwind\b",
        r"\brain\b",
        r"\braining\b",
        r"\bforecast\b",
        r"\bclimate\b",
    ]
    
    question_lower = question.lower()
    for keyword in weather_keywords:
        if re.search(keyword, question_lower):
            return True
    return False


async def get_weather(location: str, request_id: str) -> Optional[dict]:
    """Get weather from Open-Meteo (free, no API key required)."""
    
    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Geocode the location
            geo_response = await client.get(
                GEOCODING_URL,
                params={
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json"
                },
                timeout=SEARCH_TIMEOUT,
            )
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            
            if not geo_data.get("results"):
                logger.warning(f"[{request_id}] Location not found: {location}")
                return None
            
            result = geo_data["results"][0]
            lat = result["latitude"]
            lon = result["longitude"]
            location_name = f"{result.get('name', '')}, {result.get('country', '')}"
            
            # Step 2: Get weather
            weather_response = await client.get(
                WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "temperature_unit": "celsius",
                },
                timeout=SEARCH_TIMEOUT,
            )
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            
            current = weather_data.get("current", {})
            temp = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m")
            wind = current.get("wind_speed_10m")
            
            content = f"Temperature: {temp}°C, Humidity: {humidity}%, Wind: {wind} km/h"
            
            logger.info(f"[{request_id}] Weather found for {location_name}: {temp}°C")
            
            return {
                "title": f"Current Weather in {location_name}",
                "content": content,
                "url": "open-meteo.com",
            }
            
    except Exception as e:
        logger.error(f"[{request_id}] Weather API error: {str(e)}")
        return None


# =========================================================
# MESSAGE ASSEMBLY
# =========================================================

def build_messages(system: str, history: List[Turn], question: str) -> List[dict]:
    """System prompt, then the conversation so far, then the new question.

    The server stores nothing — the client replays history, trimmed here so a
    long chat cannot inflate cost or latency without limit.
    """
    messages = [{"role": "system", "content": system}]
    for turn in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": question})

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
# OLLAMA (LOCAL FALLBACK)
# =========================================================

def ollama_prompt(messages: List[dict]) -> str:
    """Ollama's /api/generate takes one prompt, so flatten the conversation."""
    parts = []
    for m in messages:
        if m["role"] == "system":
            parts.append(m["content"])
        elif m["role"] == "user":
            parts.append(f"User:\n{m['content']}")
        else:
            parts.append(f"Assistant:\n{m['content']}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


async def ask_ollama(messages: List[dict], model: str, request_id: str) -> str:
    payload = {"model": model, "prompt": ollama_prompt(messages), "stream": False}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            response.raise_for_status()
            answer = response.json().get("response")

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty Ollama response")

            logger.info(f"[{request_id}] Ollama success with model {model}")
            return answer.strip()

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] Ollama timeout")
        raise HTTPException(status_code=504, detail="ConBOT timed out. Please try again.")
    except httpx.ConnectError:
        logger.error(f"[{request_id}] Ollama connection error (not running?)")
        raise HTTPException(status_code=503, detail="ConBOT is unavailable right now.")
    except Exception as e:
        logger.error(f"[{request_id}] Ollama error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail="ConBOT returned an invalid response.")


async def stream_ollama(
    messages: List[dict],
    model: str,
    request_id: str,
) -> AsyncIterator[str]:
    payload = {"model": model, "prompt": ollama_prompt(messages), "stream": True}

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        async with client.stream("POST", OLLAMA_URL, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = data.get("response")
                if piece:
                    yield piece
                if data.get("done"):
                    break


# =========================================================
# DISPATCH
# =========================================================

def no_llm_error() -> HTTPException:
    logger.error("OPENROUTER_API_KEY is not set — check the deployed environment")
    return HTTPException(
        status_code=503, detail="ConBOT is not configured to answer questions yet."
    )


async def get_ai_answer(messages: List[dict], model: str, request_id: str) -> str:
    if OPENROUTER_API_KEY:
        try:
            return await ask_openrouter(messages, model, request_id)
        except Exception as e:
            logger.warning(
                f"[{request_id}] OpenRouter failed: {type(e).__name__}: {str(e)[:500]}"
            )
            if not ALLOW_OLLAMA_FALLBACK:
                raise HTTPException(
                    status_code=502,
                    detail="ConBOT could not answer that right now. Please try again shortly.",
                )
    elif not ALLOW_OLLAMA_FALLBACK:
        raise no_llm_error()

    logger.info(f"[{request_id}] Using Ollama fallback")
    return await ask_ollama(messages, model, request_id)


def stream_answer(
    messages: List[dict],
    model: str,
    request_id: str,
    state: Optional[dict] = None,
) -> AsyncIterator[str]:
    if OPENROUTER_API_KEY:
        return stream_openrouter(messages, model, request_id, state)
    if ALLOW_OLLAMA_FALLBACK:
        return stream_ollama(messages, model, request_id)
    raise no_llm_error()


# =========================================================
# DUCKDUCKGO WEB SEARCH (IMPROVED)
# =========================================================

async def search_web(question: str, request_id: str) -> list:
    """Search the web using DuckDuckGo API with improved error handling."""
    
    params = {
        "q": question,
        "format": "json",
        "no_redirect": 1,
        "skip_disambig": 1,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                DUCKDUCKGO_URL,
                params=params,
                timeout=SEARCH_TIMEOUT,
            )
            
            # Handle different response codes (202 is also OK for async responses)
            if response.status_code not in [200, 202]:
                logger.warning(f"[{request_id}] DuckDuckGo returned {response.status_code}")
                return []
            
            data = response.json()
            cleaned_results = []

            # Try to get abstract result
            abstract_text = data.get("AbstractText", "").strip()
            abstract_url = data.get("AbstractURL", "").strip()
            
            if abstract_text and abstract_url:
                cleaned_results.append({
                    "title": data.get("Heading", "Search Result")[:100],
                    "content": abstract_text[:500],
                    "url": abstract_url,
                })
                logger.info(f"[{request_id}] Found abstract result from DuckDuckGo")

            # Try to get related topics
            related_topics = data.get("RelatedTopics", [])
            if related_topics:
                for result in related_topics[:3]:
                    if isinstance(result, dict):
                        text = result.get("Text", "").strip()
                        url = result.get("FirstURL", "").strip()
                        
                        if text and url:
                            cleaned_results.append({
                                "title": text[:100],
                                "content": text[:500],
                                "url": url,
                            })
                
                if cleaned_results:
                    logger.info(f"[{request_id}] Found {len(cleaned_results)} results from DuckDuckGo")

            if not cleaned_results:
                logger.warning(f"[{request_id}] DuckDuckGo returned empty response")

            return cleaned_results

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] DuckDuckGo timeout")
        return []
    except Exception as e:
        logger.error(f"[{request_id}] DuckDuckGo error: {type(e).__name__}: {str(e)}")
        return []


# =========================================================
# BUILD WEB-AUGMENTED PROMPT
# =========================================================

def build_web_prompt(question: str, search_results: list, system: str) -> str:
    """Build a prompt that includes web search results."""
    
    sources_text = []

    for index, result in enumerate(search_results, start=1):
        sources_text.append(
            f"""
SOURCE {index}

Title:
{result["title"]}

URL:
{result["url"]}

Information:
{result["content"]}
""".strip()
        )

    web_information = "\n\n".join(sources_text)

    return f"""
{system}

IMPORTANT:

The user's question requires current information.

Use the web search results below to answer the question.

Do not guess current facts.

Do not use outdated knowledge when the supplied
web information provides a reliable current answer.

If the search results do not contain enough information,
say that clearly.

When appropriate, mention the relevant source naturally.

User question:
{question}

WEB SEARCH RESULTS:

{web_information}

Now provide the clearest answer for the user.
""".strip()


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():
    """Report whether the service can actually answer, not just whether it booted."""
    return {
        "status": "healthy" if (OPENROUTER_API_KEY or ALLOW_OLLAMA_FALLBACK) else "degraded",
        "llm_configured": bool(OPENROUTER_API_KEY),
        "ollama_fallback": ALLOW_OLLAMA_FALLBACK,
    }


# =========================================================
# ASK CONBOT
# =========================================================

# =========================================================
# SHARED PREPARATION
# =========================================================

async def prepare(request: ChatRequest, request_id: str) -> dict:
    """Everything both endpoints need: validation, location, search, messages."""

    if request.model not in AVAILABLE_MODELS:
        logger.warning(f"[{request_id}] Invalid model requested: {request.model}")
        raise HTTPException(status_code=400, detail="Unsupported model.")

    question = request.prompt.strip()
    loc = resolve_location(request.timezone, request.language)
    system = base_prompt(loc)

    logger.info(
        f"[{request_id}] Q: {question[:80]}... model={request.model} "
        f"loc={loc['city']}, {loc['country']} history={len(request.history)}"
    )

    sources: list = []

    if needs_web_search(question):
        logger.info(f"[{request_id}] Web search required")
        results: list = []

        if is_weather_question(question):
            # "weather in Delhi" -> Delhi; bare "what's the weather" -> the
            # user's own city, not a hardcoded one.
            location = loc["city"] or FALLBACK_TIMEZONE.split("/")[-1]
            if " in " in question:
                location = question.split(" in ")[-1].replace("?", "").strip()

            weather = await get_weather(location, request_id)
            if weather:
                results = [weather]

        if not results:
            results = await search_web(question, request_id)

        if results:
            system = build_web_prompt(question, results, system)
            sources = [{"title": r["title"], "url": r["url"]} for r in results]
        else:
            logger.info(f"[{request_id}] No search results, answering without them")
            system += (
                "\n\nThe question may need current information, but live "
                "information is unavailable right now. Do not invent or guess "
                "current facts — say plainly that you cannot verify them."
            )

    return {
        "messages": build_messages(system, request.history, question),
        "sources": sources,
    }


# =========================================================
# ASK (NON-STREAMING)
# =========================================================

@app.post("/ask")
async def ask(request: ChatRequest, http_request: Request):
    """Whole answer in one response. Kept for clients that cannot stream."""

    request_id = str(uuid.uuid4())[:8]
    enforce_rate_limit(http_request, request_id)
    prepared = await prepare(request, request_id)

    answer = await get_ai_answer(prepared["messages"], request.model, request_id)

    return {
        "answer": answer,
        "web_used": bool(prepared["sources"]),
        "sources": prepared["sources"],
    }


# =========================================================
# STREAM
# =========================================================

def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/stream")
async def stream(request: ChatRequest, http_request: Request):
    """Server-sent events: sources first, then answer text as it is generated."""

    request_id = str(uuid.uuid4())[:8]
    enforce_rate_limit(http_request, request_id)

    # Check configuration before the response starts. Once headers are sent
    # the status code is fixed, so a 503 raised inside the generator would
    # reach the client as a 200 with an error event.
    if not OPENROUTER_API_KEY and not ALLOW_OLLAMA_FALLBACK:
        raise no_llm_error()

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
                f"[{request_id}] Stream failed: {type(e).__name__}: {str(e)[:400]}"
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
            logger.info(f"[{request_id}] Asking for clarification")
            yield sse({"type": "clarify", **clarify})
            yield sse({"type": "done"})
            return

        if not produced:
            yield sse({"type": "error", "detail": "ConBOT returned an empty answer."})
            return

        if state.get("finish_reason") == "length":
            logger.info(f"[{request_id}] Answer hit the token cap")
            yield sse({"type": "truncated"})
        else:
            followups = blocks.followups()
            if followups:
                yield sse({"type": "followups", "questions": followups})

        logger.info(f"[{request_id}] Stream complete")
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
