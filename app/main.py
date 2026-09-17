from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.logging_config import logger
from app.api.routes import ask, health, image, stream


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """One line at boot that says whether this instance can answer at all."""
    if config.GEMINI_API_KEY:
        logger.info(
            "startup gemini=configured model=%s key_suffix=...%s web_search=%s "
            "client_ip_header=%s proxy_hops=%d",
            config.GEMINI_MODEL_MAP["text"], config.GEMINI_API_KEY[-4:],
            "brave" if config.BRAVE_SEARCH_API_KEY else "duckduckgo",
            config.CLIENT_IP_HEADER or "-", config.TRUSTED_PROXY_HOPS,
        )
    else:
        logger.error(
            "startup gemini=MISSING — every request will fail until "
            "GEMINI_API_KEY is set."
        )
    yield


app = FastAPI(
    title="ConBOT API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


app.include_router(health.router)
app.include_router(ask.router)
app.include_router(stream.router)
app.include_router(image.router)
