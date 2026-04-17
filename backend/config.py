"""Environment-driven configuration for LLM-RANK."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment."""

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")

    db_path: str = os.getenv("LLM_RANK_DB_PATH", str(ROOT / "llm_rank.db"))
    host: str = os.getenv("LLM_RANK_HOST", "127.0.0.1")
    port: int = int(os.getenv("LLM_RANK_PORT", "8000"))

    claude_model: str = "claude-sonnet-4-20250514"
    perplexity_model: str = "sonar-pro"
    gemini_model: str = os.getenv("LLM_RANK_GEMINI_MODEL", "gemini-2.5-flash")

    # Comma-separated list of models to query per scan. Valid: "gemini", "perplexity".
    enabled_models_raw: str = os.getenv("LLM_RANK_ENABLED_MODELS", "gemini")

    @property
    def enabled_models(self) -> tuple[str, ...]:
        return tuple(
            m.strip().lower()
            for m in self.enabled_models_raw.split(",")
            if m.strip()
        )

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger once with a structured format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
