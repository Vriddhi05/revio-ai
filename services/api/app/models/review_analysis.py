import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReviewAnalysis(Base):
    __tablename__ = "review_analyses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "review_id", "content_hash", "pipeline_version", name="uq_review_analysis_version"),
        Index("ix_review_analyses_tenant_current", "tenant_id", "is_current"),
        Index("ix_review_analyses_tenant_sentiment", "tenant_id", "sentiment"),
        Index("ix_review_analyses_tenant_severity", "tenant_id", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(240), nullable=False)
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    model_name: Mapped[str] = mapped_column(String(240), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    script: Mapped[str] = mapped_column(String(24), nullable=False)
    language_method: Mapped[str] = mapped_column(String(48), nullable=False)
    aspect_provider: Mapped[str] = mapped_column(String(48), nullable=False)
    categories_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    urgency_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    urgency_reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    review: Mapped["Review"] = relationship(back_populates="analysis_records")
