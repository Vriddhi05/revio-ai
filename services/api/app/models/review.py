import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_review_tenant_dedupe"),
        Index("ix_reviews_tenant_date", "tenant_id", "review_date"),
        Index("ix_reviews_tenant_location", "tenant_id", "location_id"),
        Index("ix_reviews_tenant_status", "tenant_id", "status"),
        Index("ix_reviews_tenant_rating", "tenant_id", "rating"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False)
    import_job_id: Mapped[str | None] = mapped_column(ForeignKey("review_import_jobs.id", ondelete="SET NULL"))
    review_text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(160))
    review_date: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str] = mapped_column(String(80), default="CSV import", nullable=False)
    external_review_id: Mapped[str | None] = mapped_column(String(180))
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    sentiment: Mapped[str | None] = mapped_column(String(16))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ingestion_source: Mapped[str] = mapped_column(String(24), default="csv", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="reviews")
    location: Mapped["Location"] = relationship(back_populates="reviews")
    import_job: Mapped["ReviewImportJob | None"] = relationship(back_populates="reviews")
