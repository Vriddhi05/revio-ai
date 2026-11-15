from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "REVIO API"
    app_env: str = "development"
    database_url: str = f"sqlite:///{(API_ROOT / 'revio.db').as_posix()}"
    revio_sentiment_provider: Literal["fallback", "transformers"] = "fallback"
    revio_aspect_provider: Literal["rules", "sentence-transformers"] = "rules"
    crisis_window_days: int = Field(default=14, ge=7, le=30)
    crisis_minimum_sample: int = Field(default=3, ge=1)
    crisis_negative_rate_rise: float = Field(default=0.25, ge=0, le=1)
    crisis_similar_complaint_minimum: int = Field(default=3, ge=2)
    crisis_cross_location_minimum: int = Field(default=2, ge=2)
    crisis_customer_repeat_minimum: int = Field(default=2, ge=2)

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
