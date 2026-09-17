import re
from typing import Optional

import httpx

from app.config import GEOCODING_URL, SEARCH_TIMEOUT, WEATHER_URL
from app.logging_config import logger

# Words that are about weather on their own.
WEATHER_STRONG = re.compile(
    r"\b(weather|forecast|raining|rainfall|will it rain|is it raining|"
    r"humidity|humid|monsoon today|snowing|heatwave)\b"
)
# Words that are only weather when tied to a time or place
# ("normal body temperature" is not a weather question).
WEATHER_WEAK = re.compile(r"\b(temperature|temp|how hot|how cold|rain)\b")
WEATHER_CONTEXT = re.compile(
    r"\b(today|tonight|tomorrow|now|outside|this week|weekend)\b|\b(in|at|for) [a-z]"
)

# Trailing words that are part of the sentence, not the place name.
_PLACE_TAIL = re.compile(
    r"\b(today|tonight|tomorrow|now|right now|currently|this (morning|evening|"
    r"afternoon|week|weekend)|at the moment|outside|please|like|going to be|"
    r"be|is|will|weather|forecast)\b.*$",
    re.IGNORECASE,
)


def is_weather_question(question: str) -> bool:
    q = question.lower()
    if WEATHER_STRONG.search(q):
        return True
    return bool(WEATHER_WEAK.search(q) and WEATHER_CONTEXT.search(q))


def is_tomorrow(question: str) -> bool:
    return bool(re.search(r"\btomorrow\b", question.lower()))


def extract_place(question: str) -> Optional[str]:
    """ "weather in New Delhi today?" -> "New Delhi". None if no place named."""
    match = re.search(r"\b(?:in|at|for)\s+([^?.!,;]+)", question, re.IGNORECASE)
    if not match:
        return None
    place = _PLACE_TAIL.sub("", match.group(1)).strip(" '\"-")
    place = re.sub(r"^(the|my)\s+", "", place, flags=re.IGNORECASE)
    if not place or place.lower() in {"city", "area", "town", "here"}:
        return None
    return place[:60]


WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
    82: "violent rain showers", 95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


async def get_weather(location: str, tomorrow: bool, request_id: str) -> Optional[dict]:
    """Current conditions, or tomorrow's forecast, from Open-Meteo (keyless)."""
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            geo = await client.get(
                GEOCODING_URL,
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            geo.raise_for_status()
            results = geo.json().get("results") or []
            if not results:
                logger.info("[%s] weather=place_not_found", request_id)
                return None

            place = results[0]
            name = ", ".join(x for x in [place.get("name"), place.get("admin1"), place.get("country")] if x)
            params = {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "timezone": "auto",
                "temperature_unit": "celsius",
            }
            if tomorrow:
                params.update({
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max",
                    "forecast_days": 2,
                })
            else:
                params["current"] = ("temperature_2m,relative_humidity_2m,"
                                     "weather_code,wind_speed_10m")

            resp = await client.get(WEATHER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if tomorrow:
            d = data.get("daily", {})
            def at1(key):
                vals = d.get(key) or []
                return vals[1] if len(vals) > 1 else None
            content = (
                f"Forecast for {at1('time')}: {WEATHER_CODES.get(at1('weather_code'), 'mixed conditions')}, "
                f"high {at1('temperature_2m_max')}°C, low {at1('temperature_2m_min')}°C, "
                f"chance of rain {at1('precipitation_probability_max')}%."
            )
            title = f"Tomorrow's weather forecast for {name}"
        else:
            c = data.get("current", {})
            content = (
                f"As of {c.get('time')} local time: "
                f"{WEATHER_CODES.get(c.get('weather_code'), 'mixed conditions')}, "
                f"{c.get('temperature_2m')}°C, humidity {c.get('relative_humidity_2m')}%, "
                f"wind {c.get('wind_speed_10m')} km/h."
            )
            title = f"Current weather in {name}"

        logger.info("[%s] weather=ok tomorrow=%s", request_id, tomorrow)
        return {"title": title, "content": content, "url": "https://open-meteo.com/"}

    except Exception as e:
        logger.error("[%s] weather=error type=%s", request_id, type(e).__name__)
        return None
