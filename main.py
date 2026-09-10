from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL = "llama3:latest"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str


@app.get("/")
def home():
    return {"message": "Llama Chatbot API"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/ask")
def ask(request: ChatRequest):

    payload = {
        "model": MODEL,
        "prompt": request.prompt,
        "stream": False
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120
        )

        response.raise_for_status()

        data = response.json()

        return {
            "answer": data["response"]
        }

    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM service unavailable: {e}"
        )