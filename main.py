from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import re


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
# CONFIGURATION
# =========================================================

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

SEARXNG_URL = "http://searxng:8080/search"

DEFAULT_MODEL = "qwen3:14b"

AVAILABLE_MODELS = {
    "qwen3:14b",
    "llama3:latest",
    "mistral:latest",
}


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
    allow_methods=[
        "GET",
        "POST",
    ],
    allow_headers=[
        "Content-Type",
    ],
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

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )

    model: str = Field(
        default=DEFAULT_MODEL,
        max_length=50,
    )


# =========================================================
# CURRENT INFORMATION DETECTION
# =========================================================

def needs_web_search(question: str) -> bool:

    question_lower = question.lower().strip()

    current_patterns = [

        # Time-sensitive language
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

        # News / updates
        r"\bnews\b",
        r"\bupdate\b",
        r"\bupdates\b",
        r"\bwhat happened\b",
        r"\bwhat's happening\b",
        r"\bwhats happening\b",

        # Prices / markets
        r"\bprice\b",
        r"\bpricing\b",
        r"\bcost\b",
        r"\bworth\b",
        r"\bstock\b",
        r"\bshare price\b",
        r"\bbitcoin\b",
        r"\bcryptocurrency\b",
        r"\bgold price\b",

        # Weather
        r"\bweather\b",
        r"\btemperature\b",
        r"\bforecast\b",

        # Sports
        r"\bscore\b",
        r"\bmatch today\b",
        r"\bgame today\b",
        r"\bplaying today\b",
        r"\bwon today\b",
        r"\bwho won\b",

        # Government / rules / policies
        r"\blatest law\b",
        r"\bnew law\b",
        r"\bnew rules\b",
        r"\bnew rule\b",
        r"\bgovernment announcement\b",
        r"\bpolicy update\b",
        r"\bvisa rules\b",
        r"\bvisa rule\b",

        # Products / availability
        r"\bin stock\b",
        r"\bavailable now\b",
        r"\bavailability\b",
        r"\bdeal\b",
        r"\bdeals\b",

        # Latest versions
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
# OLLAMA
# =========================================================

def ask_ollama(
    prompt: str,
    model: str,
) -> str:

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=180,
        )

        response.raise_for_status()

    except requests.Timeout:

        print("ConBOT: Ollama request timed out.")

        raise HTTPException(
            status_code=504,
            detail="AI service timed out. Please try again.",
        )

    except requests.RequestException as error:

        print(
            f"ConBOT: Ollama request failed: {error}"
        )

        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable.",
        )

    try:

        data = response.json()

    except ValueError:

        print(
            "ConBOT: Ollama returned invalid JSON."
        )

        raise HTTPException(
            status_code=502,
            detail="AI service returned an invalid response.",
        )

    answer = data.get("response")

    if (
        not isinstance(answer, str)
        or not answer.strip()
    ):

        print(
            "ConBOT: Ollama response did not contain an answer."
        )

        raise HTTPException(
            status_code=502,
            detail="AI service returned an invalid response.",
        )

    return answer.strip()


# =========================================================
# SEARXNG WEB SEARCH
# =========================================================

def search_web(question: str):

    params = {
        "q": question,
        "format": "json",
        "language": "en",
        "safesearch": 1,
        "categories": "general",
    }

    try:

        response = requests.get(
            SEARXNG_URL,
            params=params,
            timeout=20,
        )

        response.raise_for_status()

    except requests.Timeout:

        print("ConBOT: SearXNG request timed out.")

        return []

    except requests.RequestException as error:

        print(
            f"ConBOT: SearXNG request failed: {error}"
        )

        return []

    try:

        data = response.json()

    except ValueError:

        print(
            "ConBOT: SearXNG returned invalid JSON."
        )

        return []

    results = data.get("results", [])

    cleaned_results = []

    for result in results[:5]:

        title = result.get("title", "").strip()
        content = result.get("content", "").strip()
        url = result.get("url", "").strip()

        if not title or not url:
            continue

        cleaned_results.append(
            {
                "title": title,
                "content": content,
                "url": url,
            }
        )

    return cleaned_results


# =========================================================
# BUILD WEB-AUGMENTED PROMPT
# =========================================================

def build_web_prompt(
    question: str,
    search_results: list,
) -> str:

    sources_text = []

    for index, result in enumerate(
        search_results,
        start=1,
    ):

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

    web_information = "\n\n".join(
        sources_text
    )

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
def health():

    return {
        "status": "healthy"
    }


# =========================================================
# SEARCH HEALTH
# =========================================================

@app.get("/health/search")
def search_health():

    try:

        response = requests.get(
            SEARXNG_URL,
            params={
                "q": "test",
                "format": "json",
            },
            timeout=10,
        )

        response.raise_for_status()

        return {
            "status": "healthy",
            "searxng": "connected",
        }

    except Exception as error:

        print(
            f"ConBOT: SearXNG health check failed: {error}"
        )

        raise HTTPException(
            status_code=503,
            detail="SearXNG unavailable.",
        )


# =========================================================
# ASK CONBOT
# =========================================================

@app.post("/ask")
def ask(request: ChatRequest):

    # -----------------------------------------------------
    # MODEL VALIDATION
    # -----------------------------------------------------

    if request.model not in AVAILABLE_MODELS:

        raise HTTPException(
            status_code=400,
            detail="Unsupported model.",
        )

    question = request.prompt.strip()

    # -----------------------------------------------------
    # DETERMINE WHETHER WEB SEARCH IS NEEDED
    # -----------------------------------------------------

    web_required = needs_web_search(question)

    # -----------------------------------------------------
    # CURRENT INFORMATION QUESTION
    # -----------------------------------------------------

    if web_required:

        print(
            f"ConBOT: Web search required: {question}"
        )

        search_results = search_web(question)

        # -------------------------------------------------
        # SEARCH FAILED
        # -------------------------------------------------

        if not search_results:

            print(
                "ConBOT: No web results available."
            )

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

            answer = ask_ollama(
                fallback_prompt,
                request.model,
            )

            return {
                "answer": answer,
                "web_used": False,
                "sources": [],
            }

        # -------------------------------------------------
        # SEND WEB RESULTS TO QWEN
        # -------------------------------------------------

        web_prompt = build_web_prompt(
            question,
            search_results,
        )

        answer = ask_ollama(
            web_prompt,
            request.model,
        )

        # -------------------------------------------------
        # RETURN ANSWER + SOURCES
        # -------------------------------------------------

        sources = [
            {
                "title": result["title"],
                "url": result["url"],
            }
            for result in search_results
        ]

        return {
            "answer": answer,
            "web_used": True,
            "sources": sources,
        }

    # -----------------------------------------------------
    # NORMAL QUESTION
    # -----------------------------------------------------

    print(
        f"ConBOT: Local answer: {question}"
    )

    full_prompt = (
        CONBOT_SYSTEM_PROMPT.strip()
        + "\n\nUser question:\n"
        + question
    )

    answer = ask_ollama(
        full_prompt,
        request.model,
    )

    return {
        "answer": answer,
        "web_used": False,
        "sources": [],
    }