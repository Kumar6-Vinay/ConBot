import uuid

from fastapi import APIRouter, HTTPException

from app.logging_config import logger
from app.models.image import ImageGenerationRequest, ImageGenerationResponse
from app.services import image_generation

router = APIRouter()


@router.post("/generate-image", response_model=ImageGenerationResponse)
async def generate_image_endpoint(request: ImageGenerationRequest):
    """Generate an image via Pollinations.ai."""
    request_id = uuid.uuid4().hex[:8]

    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    try:
        result = await image_generation.generate_image(
            prompt=request.prompt,
            model=request.model,
            width=request.width,
            height=request.height,
            seed=request.seed,
            request_id=request_id,
        )
        logger.info("[%s] image generation success", request_id)
        return result

    except ValueError as e:
        logger.warning("[%s] image generation validation: %s", request_id, str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[%s] image generation error: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail="Image generation failed")


@router.get("/models/image")
async def list_image_models():
    """List available image generation models."""
    return image_generation.get_available_models()
