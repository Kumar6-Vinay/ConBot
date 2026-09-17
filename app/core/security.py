import re
from typing import Optional

from fastapi import HTTPException

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# data:image/png;base64,AAAA...  — capture the mime type and confirm base64.
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,[A-Za-z0-9+/=\s]+$")


def clip(text: str, limit: int) -> str:
    """Keep the start of a long message — that is where its point usually is."""
    return text if len(text) <= limit else text[:limit].rstrip() + " …[trimmed]"


def validate_image(image: Optional[str]) -> Optional[str]:
    """Return the data URL if it is a well-formed, allowed image, else raise.

    The Pydantic ceiling already bounds the length; here we confirm it is a
    base64 image data URL of a type the vision models accept.
    """
    if not image:
        return None
    match = _DATA_URL_RE.match(image.strip())
    if not match or match.group(1).lower() not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="That image could not be read. Please attach a PNG, JPEG, WebP or GIF.",
        )
    return image.strip()
