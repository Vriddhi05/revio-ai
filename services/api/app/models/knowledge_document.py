import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_sha256", name="uq_knowledge_tenant_content"),
        UniqueConstraint("tenant_id", "source_key", "version", name="uq_knowledge_tenant_source_version"),
        Index("ix_knowledge_tenant_status", "tenant_id", "status"),
        Index("ix_knowledge_tenant_source", "tenant_id", "source_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(240), nullable=False)
    source_key: Mapped[str] = mapped_column(String(240), nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_pages_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_model: Mapped[str] = mapped_column(String(240), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(64), nullable=False, default="chars-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="knowledge_documents")
