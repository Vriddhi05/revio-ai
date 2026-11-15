import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CrisisAlert(Base):
    __tablename__ = "crisis_alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "signal_key", name="uq_crisis_alert_tenant_signal"),
        Index("ix_crisis_alerts_tenant_status", "tenant_id", "status"),
        Index("ix_crisis_alerts_tenant_detected", "tenant_id", "detected_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    signal_key: Mapped[str] = mapped_column(String(240), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    supporting_review_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    location: Mapped["Location | None"] = relationship(foreign_keys=[location_id])
