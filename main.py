from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import re
import os
import logging
import uuid
from typing import Optional

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

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_MODEL_MAP = {
    "qwen3:14b": "qwen/qwen3-14b",
    "llama3:latest": "meta-llama/llama-3-8b-instruct",
    "mistral:latest": "mistralai/mistral-7b-instruct",
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
# CORS
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

12. Be concise by default.

13. Do not unnecessarily repeat the user's question.

14. Do not use fake citations, fake sources, or invented
    references.

15. Be helpful, respectful, and natural.

Return only the answer intended for the user.
"""


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    model: str = Field(default=DEFAULT_MODEL, max_length=50)


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
# OPENROUTER (PRIMARY)
# =========================================================

async def ask_openrouter(
    full_prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Call OpenRouter API with the given prompt and model."""
    
    openrouter_model = OPENROUTER_MODEL_MAP.get(model, model)

    payload = {
        "model": openrouter_model,
        "messages": [
            {"role": "user", "content": full_prompt},
        ],
        "max_tokens": 1000,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=OPENROUTER_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty OpenRouter response")

            logger.info(f"[{request_id}] OpenRouter success with model {openrouter_model}")
            return answer.strip()

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] OpenRouter timeout")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"[{request_id}] OpenRouter HTTP error: {e.status_code}")
        raise
    except Exception as e:
        logger.error(f"[{request_id}] OpenRouter error: {str(e)}")
        raise


# =========================================================
# OLLAMA (FALLBACK)
# =========================================================

async def ask_ollama(
    full_prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Call Ollama API (local fallback)."""
    
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OLLAMA_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("response")

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Empty Ollama response")

            logger.info(f"[{request_id}] Ollama success with model {model}")
            return answer.strip()

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] Ollama timeout")
        raise HTTPException(status_code=504, detail="AI service timed out. Please try again.")
    except httpx.ConnectError:
        logger.error(f"[{request_id}] Ollama connection error (not running?)")
        raise HTTPException(status_code=503, detail="AI service unavailable.")
    except Exception as e:
        logger.error(f"[{request_id}] Ollama error: {str(e)}")
        raise HTTPException(status_code=502, detail="AI service returned an invalid response.")


# =========================================================
# LLM DISPATCH (OPENROUTER PRIMARY, OLLAMA FALLBACK)
# =========================================================

async def get_ai_answer(
    full_prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Try OpenRouter first, fall back to Ollama if it fails."""
    
    if OPENROUTER_API_KEY:
        try:
            return await ask_openrouter(full_prompt, model, request_id)
        except Exception as e:
            logger.warning(f"[{request_id}] OpenRouter failed, falling back to Ollama: {str(e)}")

    logger.info(f"[{request_id}] Using Ollama fallback")
    return await ask_ollama(full_prompt, model, request_id)


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

def build_web_prompt(question: str, search_results: list) -> str:
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
{CONBOT_SYSTEM_PROMPT}

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
    return {"status": "healthy"}


# =========================================================
# ASK CONBOT
# =========================================================

@app.post("/ask")
async def ask(request: ChatRequest):
    """Main endpoint: accept a question, return an answer with optional web search."""
    
    request_id = str(uuid.uuid4())[:8]
    
    # Validate model
    if request.model not in AVAILABLE_MODELS:
        logger.warning(f"[{request_id}] Invalid model requested: {request.model}")
        raise HTTPException(status_code=400, detail="Unsupported model.")

    question = request.prompt.strip()
    logger.info(f"[{request_id}] Question: {question[:100]}... Model: {request.model}")

    # Check if web search is needed
    web_required = needs_web_search(question)

    # =====================================================
    # WEB SEARCH CASE
    # =====================================================

    if web_required:
        logger.info(f"[{request_id}] Web search required")
        
        search_results = []
        
        # Check if it's a weather question first
        if is_weather_question(question):
            logger.info(f"[{request_id}] Weather question detected")
            
            # Extract location (e.g., "Kota" from "what's the weather in Kota")
            location = "Kota"  # Default to Kota
            if " in " in question:
                location = question.split(" in ")[-1].replace("?", "").strip()
            
            weather = await get_weather(location, request_id)
            if weather:
                search_results = [weather]
                logger.info(f"[{request_id}] Got weather data for {location}")
        
        # If no weather data or not a weather question, use DuckDuckGo
        if not search_results:
            logger.info(f"[{request_id}] Using DuckDuckGo search")
            search_results = await search_web(question, request_id)

        # =====================================================
        # NO RESULTS FALLBACK
        # =====================================================

        if not search_results:
            logger.info(f"[{request_id}] No search results, using local knowledge")
            fallback_prompt = f"""
{CONBOT_SYSTEM_PROMPT}

The user asked a question that may require current
information, but live information is currently
unavailable.

Do NOT invent or guess current facts.

If the answer depends on current information, clearly
tell the user that you cannot reliably verify it right now.

User question:
{question}
""".strip()

            answer = await get_ai_answer(fallback_prompt, request.model, request_id)

            return {
                "answer": answer,
                "web_used": False,
                "sources": [],
            }

        # =====================================================
        # BUILD ANSWER FROM RESULTS
        # =====================================================

        web_prompt = build_web_prompt(question, search_results)
        answer = await get_ai_answer(web_prompt, request.model, request_id)

        sources = [
            {"title": result["title"], "url": result["url"]}
            for result in search_results
        ]

        logger.info(f"[{request_id}] Answer generated with web search")
        return {
            "answer": answer,
            "web_used": True,
            "sources": sources,
        }

    # =====================================================
    # LOCAL QUESTION (NO WEB SEARCH)
    # =====================================================

    logger.info(f"[{request_id}] Local answer (no web search)")
    full_prompt = (
        CONBOT_SYSTEM_PROMPT.strip()
        + "\n\nUser question:\n"
        + question
    )

    answer = await get_ai_answer(full_prompt, request.model, request_id)

    return {
        "answer": answer,
        "web_used": False,
        "sources": [],
    }