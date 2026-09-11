from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests


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

OLLAMA_URL = (
    "http://host.docker.internal:11434/api/generate"
)

DEFAULT_MODEL = "llama3:latest"

AVAILABLE_MODELS = {
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

6. Do not invent facts. If you are uncertain, say so.

7. For questions involving law, tax, finance, health,
   safety, or other high-impact decisions, provide useful
   general information but clearly indicate that important
   decisions should be verified with an appropriate
   authoritative or qualified source.

8. If a question depends on a country, location, date,
   or other important context that has not been provided,
   do not silently assume the answer. Ask a brief
   clarification when the missing context materially
   changes the answer.

9. If the user asks for an explanation, start with the
   simplest explanation and then provide an example when
   useful.

10. Be concise by default. Give more detail when the
    question requires it.

11. Do not unnecessarily repeat the user's question.

12. Do not use fake citations, fake sources, or invented
    references.

13. Be helpful, respectful, and natural.

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
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


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


    # -----------------------------------------------------
    # BUILD PROMPT
    # -----------------------------------------------------

    full_prompt = (
        CONBOT_SYSTEM_PROMPT.strip()
        + "\n\nUser question:\n"
        + request.prompt.strip()
    )


    payload = {
        "model": request.model,
        "prompt": full_prompt,
        "stream": False,
    }


    # -----------------------------------------------------
    # CALL OLLAMA
    # -----------------------------------------------------

    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120,
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


    # -----------------------------------------------------
    # PARSE RESPONSE
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # VALIDATE ANSWER
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # RETURN SAFE APPLICATION RESPONSE
    # -----------------------------------------------------

    return {
        "answer": answer.strip()
    }