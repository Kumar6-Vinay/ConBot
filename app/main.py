from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.core.middleware import MaxBodySizeMiddleware, SecurityHeadersMiddleware
from app.core.request_id import RequestIDMiddleware
from app.logging_config import logger
from app.api.routes import ask, health, image, stream


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Log whether at least one text provider is configured at startup."""
    llm_configured = any((config.GEMINI_API_KEY, config.OPENROUTER_API_KEY, config.NVIDIA_API_KEY))
    if llm_configured:
        logger.info("startup llm=configured client_ip_header=%s proxy_hops=%d",
                    config.CLIENT_IP_HEADER or "-", config.TRUSTED_PROXY_HOPS)
    else:
        logger.error(
            "startup llm=MISSING — set a key for a provider used by PRIMARY_MODEL "
            "or TEXT_FALLBACK_CHAIN."
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
    allow_headers=["Content-Type", "X-Request-ID"],
)

# Request ID first (outermost) so every response carries it.
app.add_middleware(RequestIDMiddleware)
# Added last so it runs first — reject an oversized body before anything else.
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# Versioned API group. All client-facing routes live under /v1 so we can
# break/change later without versioning pain.
api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router)
api_router.include_router(ask.router)
api_router.include_router(stream.router)
api_router.include_router(image.router)

app.include_router(api_router)
