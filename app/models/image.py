from typing import Optional

from pydantic import BaseModel, Field


class ImageGenerationRequest(BaseModel):
    """Request for image generation."""
    prompt: str = Field(..., min_length=1, max_length=1000)
    model: str = Field(default="lykon/dreamshaper-8-lcm", max_length=80)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
    # Pollinations treats this as a 32-bit RNG seed; bound it so a client
    # can't hand upstream an arbitrarily huge integer.
    seed: Optional[int] = Field(default=None, ge=0, le=2**32 - 1)


class ImageGenerationResponse(BaseModel):
    """Response from image generation."""
    url: str
    prompt: str
    model: str
    width: int
    height: int
    cost: float
