"""Set fake credentials before any test module imports app.config."""
import os

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("OPENROUTER_API_KEY", "sk-test")
