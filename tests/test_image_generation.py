"""Tests for image generation."""

import pytest
from app.services.image_generation import get_available_models, AVAILABLE_MODELS


def test_get_available_models():
    """Test that models are available."""
    models = get_available_models()
    assert "lykon/dreamshaper-8-lcm" in models
    assert "black-forest-labs/flux.1-schnell" in models
    assert all("cost" in m for m in models.values())


def test_validate_empty_prompt():
    """Empty prompt should raise error."""
    from app.services.image_generation import generate_image
    import asyncio

    with pytest.raises(ValueError, match="empty"):
        asyncio.run(generate_image(""))


def test_validate_prompt_too_long():
    """Prompt over 1000 chars should raise error."""
    from app.services.image_generation import generate_image
    import asyncio

    with pytest.raises(ValueError, match="too long"):
        asyncio.run(generate_image("x" * 2000))


def test_validate_invalid_model():
    """Invalid model should raise error."""
    from app.services.image_generation import generate_image
    import asyncio

    with pytest.raises(ValueError, match="Unknown model"):
        asyncio.run(generate_image("A cat", model="invalid-model"))


def test_validate_width_too_small():
    """Width under 512 should raise error."""
    from app.services.image_generation import generate_image
    import asyncio

    with pytest.raises(ValueError, match="Width must be"):
        asyncio.run(generate_image("A cat", width=256))


def test_validate_height_too_large():
    """Height over 2048 should raise error."""
    from app.services.image_generation import generate_image
    import asyncio

    with pytest.raises(ValueError, match="Height must be"):
        asyncio.run(generate_image("A cat", height=4000))


def test_available_models_have_cost():
    """All models should have a cost."""
    for model_id, model_info in AVAILABLE_MODELS.items():
        assert "cost" in model_info
        assert model_info["cost"] > 0