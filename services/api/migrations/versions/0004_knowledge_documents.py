"""Add tenant-scoped knowledge documents for RAG."""

from alembic import op
import sqlalchemy as sa


revision = "0004_knowledge_documents"
down_revision = "0003_review_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("source_filename", sa.String(length=240), nullable=False),
        sa.Column("source_key", sa.String(length=240), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_chars", sa.Integer(), nullable=False),
        sa.Column("extracted_pages_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=240), nullable=False),
        sa.Column("embedding_revision", sa.String(length=128), nullable=False),
        sa.Column("chunking_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "content_sha256", name="uq_knowledge_tenant_content"),
        sa.UniqueConstraint("tenant_id", "source_key", "version", name="uq_knowledge_tenant_source_version"),
    )
    op.create_index("ix_knowledge_documents_tenant_id", "knowledge_documents", ["tenant_id"])
    op.create_index("ix_knowledge_tenant_status", "knowledge_documents", ["tenant_id", "status"])
    op.create_index("ix_knowledge_tenant_source", "knowledge_documents", ["tenant_id", "source_key"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_tenant_source", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_tenant_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
