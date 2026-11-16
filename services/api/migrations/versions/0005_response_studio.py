"""Add tenant-scoped response drafts and approval audit events."""

from alembic import op
import sqlalchemy as sa


revision = "0005_response_studio"
down_revision = "0004_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("original_response_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("generation_provider", sa.String(length=48), nullable=False),
        sa.Column("generation_model", sa.String(length=240), nullable=False),
        sa.Column("citations_json", sa.Text(), nullable=False),
        sa.Column("analysis_snapshot_json", sa.Text(), nullable=False),
        sa.Column("workflow_trace_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("needs_human_escalation", sa.Boolean(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "review_id", "version", name="uq_response_tenant_review_version"),
    )
    op.create_index("ix_response_drafts_tenant_id", "response_drafts", ["tenant_id"])
    op.create_index("ix_response_drafts_review_id", "response_drafts", ["review_id"])
    op.create_index("ix_response_tenant_review_created", "response_drafts", ["tenant_id", "review_id", "created_at"])
    op.create_index("ix_response_tenant_status", "response_drafts", ["tenant_id", "status"])
    op.create_table(
        "response_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["draft_id"], ["response_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_response_audit_events_tenant_id", "response_audit_events", ["tenant_id"])
    op.create_index("ix_response_audit_events_draft_id", "response_audit_events", ["draft_id"])
    op.create_index("ix_response_audit_tenant_draft", "response_audit_events", ["tenant_id", "draft_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_response_audit_tenant_draft", table_name="response_audit_events")
    op.drop_index("ix_response_audit_events_draft_id", table_name="response_audit_events")
    op.drop_index("ix_response_audit_events_tenant_id", table_name="response_audit_events")
    op.drop_table("response_audit_events")
    op.drop_index("ix_response_tenant_status", table_name="response_drafts")
    op.drop_index("ix_response_tenant_review_created", table_name="response_drafts")
    op.drop_index("ix_response_drafts_review_id", table_name="response_drafts")
    op.drop_index("ix_response_drafts_tenant_id", table_name="response_drafts")
    op.drop_table("response_drafts")
