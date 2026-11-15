"""Add tenant locations, reviews and CSV import jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0002_review_ingestion"
down_revision = "0001_initial_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_import_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("accepted_rows", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_import_jobs_tenant_id", "review_import_jobs", ["tenant_id"])

    op.create_table(
        "locations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "normalized_name", name="uq_location_tenant_name"),
    )
    op.create_index("ix_locations_tenant_id", "locations", ["tenant_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.Column("import_job_id", sa.String(length=36), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("author_name", sa.String(length=160), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("external_review_id", sa.String(length=180), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("sentiment", sa.String(length=16), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("ingestion_source", sa.String(length=24), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["import_job_id"], ["review_import_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_review_tenant_dedupe"),
    )
    op.create_index("ix_reviews_tenant_id", "reviews", ["tenant_id"])
    op.create_index("ix_reviews_tenant_date", "reviews", ["tenant_id", "review_date"])
    op.create_index("ix_reviews_tenant_location", "reviews", ["tenant_id", "location_id"])
    op.create_index("ix_reviews_tenant_status", "reviews", ["tenant_id", "status"])
    op.create_index("ix_reviews_tenant_rating", "reviews", ["tenant_id", "rating"])


def downgrade() -> None:
    op.drop_index("ix_reviews_tenant_rating", table_name="reviews")
    op.drop_index("ix_reviews_tenant_status", table_name="reviews")
    op.drop_index("ix_reviews_tenant_location", table_name="reviews")
    op.drop_index("ix_reviews_tenant_date", table_name="reviews")
    op.drop_index("ix_reviews_tenant_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_locations_tenant_id", table_name="locations")
    op.drop_table("locations")
    op.drop_index("ix_review_import_jobs_tenant_id", table_name="review_import_jobs")
    op.drop_table("review_import_jobs")
