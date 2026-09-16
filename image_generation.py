"""Image generation via Pollinations.ai (gen.pollinations.ai, paid platform)."""

import os
import base64
import logging
import urllib.parse

import httpx

logger = logging.getLogger("conbot")

POLLINATIONS_BASE = "https://gen.pollinations.ai/image"
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "lykon/dreamshaper-8-lcm")
GENERATION_TIMEOUT = 90  # image generation can take a while on some models

# Model IDs exactly as listed on enter.pollinations.ai/models, with pricing
# from that same page (cost is per generation, USD).
AVAILABLE_MODELS = {
    "lykon/dreamshaper-8-lcm": {"name": "DreamShaper 8 LCM", "cost": 0.0001},
    "black-forest-labs/flux.1-schnell": {"name": "FLUX.1 Schnell", "cost": 0.002},
    "tongyi-mai/z-image-turbo": {"name": "Z-Image Turbo", "cost": 0.0004},
    "prunaai/p-image": {"name": "Pruna p-image", "cost": 0.0001},
}


async def generate_image(
    prompt: str,
    model: str = POLLINATIONS_MODEL,
    width: int = 1024,
    height: int = 1024,
    seed: int = None,
    request_id: str = "unknown",
) -> dict:
    """Generate an image via gen.pollinations.ai.

    The API returns raw image bytes for a successful request, authenticated
    with a Bearer token. That token must stay server-side, so this function
    fetches the bytes here and hands the caller a self-contained data: URL
    rather than a link back to Pollinations (which would require leaking
    the key into a client-visible URL).

    Returns:
        {"url": "data:image/...;base64,...", "prompt", "model", "width",
         "height", "cost"}
    """
    if model not in AVAILABLE_MODELS:
        models = ", ".join(AVAILABLE_MODELS.keys())
        raise ValueError(f"Unknown model. Available: {models}")

    if not prompt or len(prompt.strip()) == 0:
        raise ValueError("Prompt cannot be empty")

    if len(prompt) > 1000:
        raise ValueError("Prompt too long (max 1000 characters)")

    if not (512 <= width <= 2048):
        raise ValueError("Width must be 512-2048")

    if not (512 <= height <= 2048):
        raise ValueError("Height must be 512-2048")

    if not POLLINATIONS_API_KEY:
        raise ValueError("Image generation is not configured (missing API key)")

    encoded_prompt = urllib.parse.quote(prompt)
    params = {"model": model, "width": str(width), "height": str(height), "nologo": "true"}
    if seed is not None:
        params["seed"] = str(seed)

    url = f"{POLLINATIONS_BASE}/{encoded_prompt}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            response = await client.get(url, headers=headers)

            if response.status_code >= 400:
                body = response.text[:300]
                logger.error(
                    "[%s] pollinations HTTP %d: %s", request_id, response.status_code, body
                )
                raise ValueError(f"Generation failed: HTTP {response.status_code}")

            content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            if not content_type.startswith("image/"):
                logger.error("[%s] pollinations returned non-image content-type: %s", request_id, content_type)
                raise ValueError("Generation failed: unexpected response from image service")

            encoded = base64.b64encode(response.content).decode("ascii")
            data_url = f"data:{content_type};base64,{encoded}"

        logger.info("[%s] image=generated model=%s bytes=%d", request_id, model, len(response.content))

        return {
            "url": data_url,
            "prompt": prompt,
            "model": model,
            "width": width,
            "height": height,
            "cost": AVAILABLE_MODELS[model]["cost"],
        }

    except httpx.TimeoutException:
        logger.error("[%s] pollinations timeout after %ds", request_id, GENERATION_TIMEOUT)
        raise ValueError("Image generation timed out. Please try again.")
    except ValueError:
        raise
    except Exception as e:
        logger.error("[%s] pollinations error: %s: %s", request_id, type(e).__name__, str(e)[:200])
        raise ValueError("Generation error. Please try again.")


def get_available_models() -> dict:
    """Return list of available models with details."""
    return AVAILABLE_MODELS