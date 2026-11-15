import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config

from app.core.config import API_ROOT
from app.db.session import SessionLocal
from app.models import Location, Membership, Review, ReviewImportJob, Tenant, User
from app.services.review_csv import mark_duplicates, parse_review_csv


def initialize_database() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        tenant = ensure_demo_workspace(db)
        seed_demo_reviews(db, tenant)


def ensure_demo_workspace(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == "revio-demo"))
    if tenant is None:
        tenant = Tenant(name="Revio Demo", slug="revio-demo", is_demo=True)
        db.add(tenant)
        db.flush()

    user = db.scalar(select(User).where(User.email == "demo@revio.local"))
    if user is None:
        user = User(display_name="Demo Account", email="demo@revio.local")
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
    )
    if membership is None:
        db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))

    db.commit()
    db.refresh(tenant)
    return tenant


def seed_demo_reviews(db: Session, tenant: Tenant) -> None:
    """Ensure the fictional fixture exists without duplicating existing workspace reviews."""
    if tenant.slug != "revio-demo":
        return
    repo_root = Path(__file__).resolve().parents[4]
    sample_path = repo_root / "data" / "demo" / "reviews.csv"
    content = sample_path.read_bytes()
    preview = mark_duplicates(parse_review_csv(content), db, tenant.id)
    if preview.accepted_rows == 0:
        return
    issues = [
        {"row_number": row.row_number, "code": issue.code, "message": issue.message}
        for row in preview.rows
        for issue in row.issues
    ]
    job = ReviewImportJob(
        tenant_id=tenant.id,
        filename="reviews.csv — fictional demo data",
        status="completed",
        total_rows=preview.total_rows,
        accepted_rows=preview.accepted_rows,
        rejected_rows=preview.rejected_rows,
        error_summary=json.dumps(issues) if issues else None,
        file_sha256=hashlib.sha256(content).hexdigest(),
    )
    db.add(job)
    db.flush()
    location_cache: dict[str, Location] = {}
    for row in preview.rows:
        if not row.accepted:
            continue
        normalized = " ".join(row.location.casefold().split())
        location = location_cache.get(normalized)
        if location is None:
            location = db.scalar(
                select(Location).where(Location.tenant_id == tenant.id, Location.normalized_name == normalized)
            )
            if location is None:
                location = Location(tenant_id=tenant.id, name=row.location, normalized_name=normalized)
                db.add(location)
                db.flush()
            location_cache[normalized] = location
        db.add(
            Review(
                tenant_id=tenant.id,
                location_id=location.id,
                import_job_id=job.id,
                review_text=row.review_text,
                rating=row.rating,
                author_name=row.author_name,
                review_date=row.review_date,
                source_name=row.source,
                external_review_id=row.external_review_id,
                dedupe_key=row.dedupe_key,
                status="needs_attention" if row.rating <= 2 else "new",
                priority="high" if row.rating <= 2 else "medium" if row.rating <= 3 else "normal",
                is_synthetic=True,
                ingestion_source="demo_csv",
            )
        )
    db.commit()
