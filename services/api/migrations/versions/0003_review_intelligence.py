"""Persist review intelligence and crisis signals."""

from alembic import op
import sqlalchemy as sa


revision = "0003_review_intelligence"
down_revision = "0002_review_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=240), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("model_name", sa.String(length=240), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=False),
        sa.Column("sentiment", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_kind", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("script", sa.String(length=24), nullable=False),
        sa.Column("language_method", sa.String(length=48), nullable=False),
        sa.Column("aspect_provider", sa.String(length=48), nullable=False),
        sa.Column("categories_json", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("urgency_confidence", sa.Float(), nullable=False),
        sa.Column("urgency_reason", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "review_id", "content_hash", "pipeline_version", name="uq_review_analysis_version"),
    )
    op.create_index("ix_review_analyses_tenant_id", "review_analyses", ["tenant_id"])
    op.create_index("ix_review_analyses_review_id", "review_analyses", ["review_id"])
    op.create_index("ix_review_analyses_is_current", "review_analyses", ["is_current"])
    op.create_index("ix_review_analyses_tenant_current", "review_analyses", ["tenant_id", "is_current"])
    op.create_index("ix_review_analyses_tenant_sentiment", "review_analyses", ["tenant_id", "sentiment"])
    op.create_index("ix_review_analyses_tenant_severity", "review_analyses", ["tenant_id", "severity"])

    op.create_table(
        "crisis_alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("signal_key", sa.String(length=240), nullable=False),
        sa.Column("signal_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("supporting_review_ids_json", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "signal_key", name="uq_crisis_alert_tenant_signal"),
    )
    op.create_index("ix_crisis_alerts_tenant_id", "crisis_alerts", ["tenant_id"])
    op.create_index("ix_crisis_alerts_tenant_status", "crisis_alerts", ["tenant_id", "status"])
    op.create_index("ix_crisis_alerts_tenant_detected", "crisis_alerts", ["tenant_id", "detected_at"])


def downgrade() -> None:
    op.drop_index("ix_crisis_alerts_tenant_detected", table_name="crisis_alerts")
    op.drop_index("ix_crisis_alerts_tenant_status", table_name="crisis_alerts")
    op.drop_index("ix_crisis_alerts_tenant_id", table_name="crisis_alerts")
    op.drop_table("crisis_alerts")
    op.drop_index("ix_review_analyses_tenant_severity", table_name="review_analyses")
    op.drop_index("ix_review_analyses_tenant_sentiment", table_name="review_analyses")
    op.drop_index("ix_review_analyses_tenant_current", table_name="review_analyses")
    op.drop_index("ix_review_analyses_is_current", table_name="review_analyses")
    op.drop_index("ix_review_analyses_review_id", table_name="review_analyses")
    op.drop_index("ix_review_analyses_tenant_id", table_name="review_analyses")
    op.drop_table("review_analyses")
