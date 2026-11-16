from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseEditIn(BaseModel):
    response_text: str = Field(min_length=15, max_length=4000)

    @field_validator("response_text", mode="before")
    @classmethod
    def trim_response_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ResponseRejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ResponseCitationOut(BaseModel):
    document_id: str
    document_title: str
    source_filename: str
    source_reference: str
    page_number: int | None = None
    passage: str
    similarity_score: float
    retrieval_metadata: dict[str, Any]
    untrusted_source: bool = True


class ResponseDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    version: int
    status: Literal["draft", "edited", "approved", "rejected"]
    response_text: str
    original_response_text: str
    language: str
    generation_provider: str
    generation_model: str
    citations: list[ResponseCitationOut]
    analysis: dict[str, Any]
    workflow_trace: list[dict[str, Any]]
    validation: dict[str, Any]
    needs_human_escalation: bool
    approved_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResponseAuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    from_status: str | None
    to_status: str
    actor: str
    reason: str | None
    created_at: datetime
