from typing import Optional

from pydantic import BaseModel, Field


class ImageGenerationRequest(BaseModel):
    """Request for image generation."""
    prompt: str = Field(..., min_length=1, max_length=1000)
    model: str = Field(default="lykon/dreamshaper-8-lcm", max_length=80)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
    seed: Optional[int] = Field(default=None)


class ImageGenerationResponse(BaseModel):
    """Response from image generation."""
    url: str
    prompt: str
    model: str
    width: int
    height: int
    cost: float
