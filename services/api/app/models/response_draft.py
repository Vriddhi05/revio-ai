import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResponseDraft(Base):
    __tablename__ = "response_drafts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "review_id", "version", name="uq_response_tenant_review_version"),
        Index("ix_response_tenant_review_created", "tenant_id", "review_id", "created_at"),
        Index("ix_response_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_response_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_provider: Mapped[str] = mapped_column(String(48), nullable=False)
    generation_model: Mapped[str] = mapped_column(String(240), nullable=False)
    citations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    analysis_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workflow_trace_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    needs_human_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    review: Mapped["Review"] = relationship()
    audit_events: Mapped[list["ResponseAuditEvent"]] = relationship(back_populates="draft", cascade="all, delete-orphan", order_by="ResponseAuditEvent.created_at")


class ResponseAuditEvent(Base):
    __tablename__ = "response_audit_events"
    __table_args__ = (
        Index("ix_response_audit_tenant_draft", "tenant_id", "draft_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("response_drafts.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    draft: Mapped[ResponseDraft] = relationship(back_populates="audit_events")
