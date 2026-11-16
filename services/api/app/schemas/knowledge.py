from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_filename: str
    media_type: str
    file_size_bytes: int
    content_sha256: str
    version: int
    page_count: int | None
    extracted_chars: int
    status: str
    error_message: str | None
    chunk_count: int
    embedding_model: str
    embedding_revision: str
    created_at: datetime
    updated_at: datetime
    duplicate: bool = False


class KnowledgeSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class KnowledgeSearchHit(BaseModel):
    passage: str
    document_id: str
    document_title: str
    source_filename: str
    source_reference: str
    page_number: int | None = None
    similarity_score: float
    retrieval_metadata: dict
    untrusted_source: bool = True


class KnowledgeSearchOut(BaseModel):
    query: str
    results: list[KnowledgeSearchHit]
    abstained: bool
    abstention_reason: str | None
    retrieval_metadata: dict


class DemoKnowledgeSeedOut(BaseModel):
    added: int
    already_present: int
    documents: list[KnowledgeDocumentOut]
