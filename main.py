from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI()

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

class AskRequest(BaseModel):
    prompt: str

@app.get("/")
def home():
    return {"message": "AI application is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
@app.post("/ask")
def ask_question(prompt: str):

    payload = {
        "model": "llama3:latest",
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)

    return response.json()