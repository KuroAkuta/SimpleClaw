"""
Configuration settings loaded from environment variables.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application configuration."""

    # Model provider selection
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")

    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Model names
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Custom model configuration
    CUSTOM_MODEL_NAME = os.getenv("CUSTOM_MODEL_NAME", "")
    CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL", "")
    CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")

    # Embedding configuration
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

    # Reranker configuration
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "")
    RERANKER_BASE_URL = os.getenv("RERANKER_BASE_URL", "")
    RERANKER_API_KEY = os.getenv("RERANKER_API_KEY", "")

    # Agent limits
    MAX_TURNS = int(os.getenv("MAX_TURNS", "50"))

    # Paths
    BACKEND_DIR = Path(__file__).parent.parent
    PROJECT_DIR = BACKEND_DIR.parent
    # Skills directory is in backend/.agents/skills/ (not project root)
    SKILLS_DIR = BACKEND_DIR / ".agents" / "skills"

    # Server
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))


settings = Settings()
