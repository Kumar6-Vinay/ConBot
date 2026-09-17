from typing import List, Optional

from pydantic import BaseModel, Field

from app.config import (
    DEFAULT_MODEL,
    HISTORY_ITEM_CEILING,
    HISTORY_LEN_CEILING,
    MAX_IMAGE_CHARS,
    MAX_PROMPT_CHARS,
)


class Turn(BaseModel):
    """One prior exchange. Sent by the client; the server keeps no state."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=HISTORY_ITEM_CEILING)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    model: str = Field(default=DEFAULT_MODEL, max_length=50)
    history: List[Turn] = Field(default_factory=list, max_length=HISTORY_LEN_CEILING)
    # Optional image as a base64 data URL. Sent to the model with this one
    # question only; never stored in history. Pydantic checks the ceiling so
    # an oversized body is rejected before it reaches any handler.
    image: Optional[str] = Field(default=None, max_length=MAX_IMAGE_CHARS)
    # Sent by the browser. Neither is precise location and neither needs a
    # permission prompt — a timezone is city-level at best.
    timezone: Optional[str] = Field(default=None, max_length=64)
    language: Optional[str] = Field(default=None, max_length=32)
