from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import re
import os
import logging
import uuid

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

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://searxng:8080/search")

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

# Timeouts (in seconds)
OPENROUTER_TIMEOUT = 60
OLLAMA_TIMEOUT = 120
SEARXNG_TIMEOUT = 20


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
# OPENROUTER (PRIMARY)
# =========================================================

async def ask_openrouter(
    prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Call OpenRouter API with the given prompt and model."""
    
    openrouter_model = OPENROUTER_MODEL_MAP.get(model, model)

    payload = {
        "model": openrouter_model,
        "messages": [
            {"role": "system", "content": CONBOT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
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
    prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Call Ollama API (local fallback)."""
    
    payload = {
        "model": model,
        "prompt": prompt,
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
    prompt: str,
    model: str,
    request_id: str,
) -> str:
    """Try OpenRouter first, fall back to Ollama if it fails."""
    
    if OPENROUTER_API_KEY:
        try:
            return await ask_openrouter(prompt, model, request_id)
        except Exception as e:
            logger.warning(f"[{request_id}] OpenRouter failed, falling back to Ollama: {str(e)}")

    logger.info(f"[{request_id}] Using Ollama fallback")
    return await ask_ollama(prompt, model, request_id)


# =========================================================
# SEARXNG WEB SEARCH
# =========================================================

async def search_web(question: str, request_id: str) -> list:
    """Search the web using SearXNG."""
    
    params = {
        "q": question,
        "format": "json",
        "language": "en",
        "safesearch": 1,
        "categories": "general",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                SEARXNG_URL,
                params=params,
                timeout=SEARXNG_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            cleaned_results = []
            for result in results[:5]:
                title = result.get("title", "").strip()
                content = result.get("content", "").strip()
                url = result.get("url", "").strip()

                if not title or not url:
                    continue

                cleaned_results.append({
                    "title": title,
                    "content": content,
                    "url": url,
                })

            logger.info(f"[{request_id}] Web search found {len(cleaned_results)} results")
            return cleaned_results

    except httpx.TimeoutException:
        logger.error(f"[{request_id}] SearXNG timeout")
        return []
    except Exception as e:
        logger.error(f"[{request_id}] SearXNG error: {str(e)}")
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


@app.get("/health/search")
async def search_health():
    """Check if SearXNG is available."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                SEARXNG_URL,
                params={"q": "test", "format": "json"},
                timeout=SEARXNG_TIMEOUT,
            )
            response.raise_for_status()
            return {"status": "healthy", "searxng": "connected"}
    except Exception as e:
        logger.error(f"SearXNG health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="SearXNG unavailable.")


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
        search_results = await search_web(question, request_id)

        if not search_results:
            logger.info(f"[{request_id}] No web results, using local knowledge")
            fallback_prompt = f"""
{CONBOT_SYSTEM_PROMPT}

The user asked a question that may require current
information, but live web information is currently
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