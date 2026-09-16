"""Image generation via Pollinations.ai"""

import os
import httpx
import logging

logger = logging.getLogger("conbot")

POLLINATIONS_BASE = "https://api.pollinations.ai/v1"
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "dreamshaper-8")
GENERATION_TIMEOUT = 60

# Available models from Pollinations.ai with pricing
AVAILABLE_MODELS = {
    "dreamshaper-8": {"name": "DreamShaper 8 LCM", "cost": 0.0001, "rpm": 10},
    "flux-1-schnell": {"name": "FLUX.1 Schnell", "cost": 0.002, "rpm": 5},
    "z-image-turbo": {"name": "Z-Image Turbo", "cost": 0.0004, "rpm": 15},
    "pruna-p-image": {"name": "Pruna p-image", "cost": 0.0001, "rpm": 10},
}


async def generate_image(
    prompt: str,
    model: str = POLLINATIONS_MODEL,
    width: int = 1024,
    height: int = 1024,
    seed: int = None,
    request_id: str = "unknown",
) -> dict:
    """Generate an image via Pollinations.ai.
    
    Args:
        prompt: Image description (max 1000 chars)
        model: Model ID (dreamshaper-8, flux-1-schnell, etc)
        width: Image width (512-2048)
        height: Image height (512-2048)
        seed: Optional random seed for reproducibility
        request_id: For logging
        
    Returns:
        {
            "url": "image_url",
            "prompt": "...",
            "model": "...",
            "width": 1024,
            "height": 1024,
            "cost": 0.0001
        }
    """
    # Validation
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
    
    # Build the image URL with parameters
    params = {
        "prompt": prompt.replace(" ", "%20"),
        "model": model,
        "width": width,
        "height": height,
    }
    
    if seed is not None:
        params["seed"] = seed
    
    # Build query string
    query_parts = []
    for key, value in params.items():
        query_parts.append(f"{key}={value}")
    
    query_string = "&".join(query_parts)
    image_url = f"{POLLINATIONS_BASE}/image?{query_string}"
    
    try:
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT) as client:
            # Make a HEAD request to verify the URL is valid
            response = await client.head(image_url)
            if response.status_code >= 400:
                logger.error(f"[{request_id}] pollinations HTTP {response.status_code}")
                raise ValueError(f"Generation failed: HTTP {response.status_code}")
            
            logger.info(f"[{request_id}] image=generated model={model} cost=${AVAILABLE_MODELS[model]['cost']}")
            
            return {
                "url": image_url,
                "prompt": prompt,
                "model": model,
                "width": width,
                "height": height,
                "cost": AVAILABLE_MODELS[model]["cost"],
            }
    
    except httpx.TimeoutException:
        logger.error(f"[{request_id}] pollinations timeout after {GENERATION_TIMEOUT}s")
        raise ValueError("Image generation timed out")
    except Exception as e:
        logger.error(f"[{request_id}] pollinations error: {str(e)}")
        raise ValueError(f"Generation error: {str(e)}")


def get_available_models() -> dict:
    """Return list of available models with details."""
    return AVAILABLE_MODELS