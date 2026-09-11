from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests


app = FastAPI(
    title="CONBOT API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

DEFAULT_MODEL = "llama3:latest"

AVAILABLE_MODELS = {
    "llama3:latest",
    "mistral:latest",
}


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://conbot.in",
        "https://www.conbot.in",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/ask")
def ask(request: ChatRequest):

    # Validate model
    if request.model not in AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported model.",
        )

    payload = {
        "model": request.model,
        "prompt": request.prompt,
        "stream": False,
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        answer = data.get("response")

        if not answer:
            raise HTTPException(
                status_code=502,
                detail="AI service returned an invalid response.",
            )

        return {
            "answer": answer
        }

    except requests.Timeout:
        print("Ollama request timed out.")

        raise HTTPException(
            status_code=504,
            detail="AI service timed out. Please try again.",
        )

    except requests.RequestException as error:
        print(f"Ollama request failed: {error}")

        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable.",
        )

    except HTTPException:
        raise

    except Exception as error:
        print(f"Unexpected server error: {error}")

        raise HTTPException(
            status_code=500,
            detail="Something went wrong. Please try again.",
        )