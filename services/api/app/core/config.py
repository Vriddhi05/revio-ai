from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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
    knowledge_vector_path: str = str(API_ROOT / "chroma_data")
    knowledge_vector_backend: Literal["auto", "chroma", "sqlite"] = "auto"
    knowledge_embedding_model: str = "intfloat/multilingual-e5-small"
    knowledge_embedding_revision: str = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
    knowledge_upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    knowledge_chunk_chars: int = Field(default=900, ge=250, le=3000)
    knowledge_chunk_overlap: int = Field(default=140, ge=0, le=1000)
    knowledge_chunk_max_tokens: int = Field(default=480, ge=64, le=512)
    knowledge_chunk_token_overlap: int = Field(default=64, ge=0, le=256)
    # Calibrated on the committed synthetic Indian-policy evaluation set. This
    # is a starting threshold, not a production-calibrated confidence score.
    knowledge_min_similarity: float = Field(default=0.822045, ge=0, le=1)
    knowledge_max_extracted_chars: int = Field(default=2_000_000, ge=1000, le=10_000_000)
    response_llm_provider: Literal["demo", "openai_compatible"] = "demo"
    response_llm_base_url: str = "https://api.openai.com/v1"
    response_llm_api_key: str | None = None
    response_llm_model: str = "gpt-4.1-mini"
    response_llm_timeout_seconds: int = Field(default=30, ge=5, le=120)
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3100,http://127.0.0.1:3100,"
        "http://localhost:3101,http://127.0.0.1:3101"
    )

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_knowledge_chunk_settings(self):
        if self.knowledge_chunk_overlap >= self.knowledge_chunk_chars:
            raise ValueError("Knowledge chunk overlap must be smaller than the character chunk size.")
        if self.knowledge_chunk_token_overlap >= self.knowledge_chunk_max_tokens:
            raise ValueError("Knowledge token overlap must be smaller than the token chunk size.")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins; wildcard origins are not allowed.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return list(dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ))


@lru_cache
def get_settings() -> Settings:
    return Settings()
