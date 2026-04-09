"""
LLM model service for creating and managing model instances.
"""
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from tools import get_all_tools


_model_cache = None
_model_with_tools_cache = None


def create_model() -> ChatOpenAI:
    """
    Create or retrieve a cached LLM model instance.

    Supports:
    - Custom models via OPENAI-compatible API
    - OpenAI models
    - Falls back to default OpenAI model

    Returns:
        ChatOpenAI model instance

    Raises:
        ValueError: If no API key is configured
    """
    global _model_cache

    if _model_cache is not None:
        return _model_cache

    # Custom model configuration takes priority
    if settings.CUSTOM_MODEL_NAME and settings.CUSTOM_BASE_URL:
        _model_cache = ChatOpenAI(
            model=settings.CUSTOM_MODEL_NAME,
            api_key=settings.CUSTOM_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.CUSTOM_BASE_URL,
            temperature=0.7,
        )
        return _model_cache

    # Validate API key for OpenAI
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    _model_cache = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.7,
    )
    return _model_cache


def get_model_with_tools() -> ChatOpenAI:
    """
    Get or create a cached LLM model with tools bound.

    Returns:
        ChatOpenAI model with tools bound
    """
    global _model_with_tools_cache

    if _model_with_tools_cache is not None:
        return _model_with_tools_cache

    model = create_model()
    tools = get_all_tools()
    _model_with_tools_cache = model.bind_tools(tools)
    return _model_with_tools_cache
