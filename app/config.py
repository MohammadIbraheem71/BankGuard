"""Mode enum and environment-backed settings. Owner: Ibraheem.

LLM temperature is deliberately not configurable: CONTRACT.md fixes it at 0.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_KEY = "dev-only-secret-do-not-use-in-production"


class Mode(str, Enum):
    """The three comparable gateway configurations from CONTRACT.md."""

    baseline = "baseline"
    detector_only = "detector_only"
    full = "full"


class Settings:
    """Simple container for values read from the environment / .env file."""

    def __init__(self) -> None:
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "mock").strip().lower()
        self.llm_model: str = os.getenv("LLM_MODEL", "mock-chat")
        self.db_path: str = os.getenv("DB_PATH", "data/bankguard.db")
        self.secret_key: str = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
        self.llm_temperature: float = 0.0  # fixed by CONTRACT.md; never read from .env
        self.openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
        self.google_api_key: str | None = os.getenv("GOOGLE_API_KEY")
        self.groq_api_key: str | None = os.getenv("GROQ_API_KEY")
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def load_settings() -> Settings:
    """Load .env from the repository root, then build the settings object."""
    load_dotenv(BASE_DIR / ".env")
    return Settings()


settings = load_settings()


def using_default_secret() -> bool:
    """True when the demo fallback SECRET_KEY is active."""
    return settings.secret_key == DEFAULT_SECRET_KEY


def require_secret_from_env() -> bool:
    """True when startup must refuse the demo fallback SECRET_KEY."""
    return os.getenv("BANKGUARD_REQUIRE_SECRET", "").strip().lower() in {"1", "true", "yes", "on"}
