import hashlib
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config

from app.core.config import API_ROOT
from app.db.session import SessionLocal
from app.models import KnowledgeDocument, Location, Membership, Review, ReviewImportJob, Tenant, User
from app.services.review_csv import parse_review_csv

DEMO_IMPORT_FILENAME = "REVIO DEMO / SYNTHETIC DATA — Indian business reviews"
DEMO_LOCATIONS = {
    "Jaipur, Rajasthan, India",
    "Chandigarh, India",
    "Ludhiana, Punjab, India",
}
LEGACY_REVIEW_ID_PREFIX = "REVIO-DEMO-"
DEMO_REVIEW_ID_PREFIX = "REVIO-IN-DEMO-"


def initialize_database() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        recover_interrupted_knowledge_documents(db)
        tenant = ensure_demo_workspace(db)
        seed_demo_reviews(db, tenant)


def recover_interrupted_knowledge_documents(db: Session) -> int:
    """Make in-process jobs left by an API restart retryable; MVP runs one API process."""
    result = db.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.status == "processing")
        .values(
            status="failed",
            error_message="Processing was interrupted by an API restart. Reindex to retry.",
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return int(result.rowcount or 0)


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
    """Synchronize only REVIO's synthetic fixture, preserving CSV-imported workspace reviews."""
    if tenant.slug != "revio-demo":
        return
    repo_root = Path(__file__).resolve().parents[4]
    sample_path = repo_root / "data" / "demo" / "reviews.csv"
    content = sample_path.read_bytes()
    preview = parse_review_csv(content)
    rows = preview.rows
    review_ids = [row.external_review_id for row in rows]
    if (
        preview.total_rows != 45
        or preview.rejected_rows
        or len(set(review_ids)) != 45
        or not all(row.is_synthetic and row.external_review_id for row in rows)
        or {row.location for row in rows} != DEMO_LOCATIONS
    ):
        raise ValueError("The REVIO demo CSV must contain 45 valid synthetic reviews across the three configured Indian locations.")

    managed_reviews = db.scalars(
        select(Review).where(
            Review.tenant_id == tenant.id,
            Review.is_synthetic.is_(True),
            Review.ingestion_source == "demo_csv",
            or_(
                Review.external_review_id.like(f"{LEGACY_REVIEW_ID_PREFIX}%"),
                Review.external_review_id.like(f"{DEMO_REVIEW_ID_PREFIX}%"),
            ),
        )
    ).all()
    managed_location_ids = {review.location_id for review in managed_reviews}
    by_current_id: dict[str, list[Review]] = {}
    legacy_job_ids: set[str] = set()
    for review in managed_reviews:
        if review.import_job_id:
            legacy_job_ids.add(review.import_job_id)
        external_id = review.external_review_id or ""
        if external_id.startswith(LEGACY_REVIEW_ID_PREFIX):
            suffix = external_id.removeprefix(LEGACY_REVIEW_ID_PREFIX)
            external_id = f"{DEMO_REVIEW_ID_PREFIX}{suffix}"
        by_current_id.setdefault(external_id, []).append(review)

    selected_reviews: dict[str, Review] = {}
    stale_reviews: list[Review] = []
    for row_external_id in review_ids:
        candidates = by_current_id.pop(row_external_id, [])
        if not candidates:
            continue
        selected = next(
            (candidate for candidate in candidates if candidate.external_review_id == row_external_id),
            candidates[0],
        )
        selected_reviews[row_external_id] = selected
        stale_reviews.extend(candidate for candidate in candidates if candidate.id != selected.id)
    stale_reviews.extend(review for candidates in by_current_id.values() for review in candidates)
    for review in stale_reviews:
        db.delete(review)
    db.flush()

    job = db.scalar(
        select(ReviewImportJob).where(
            ReviewImportJob.tenant_id == tenant.id,
            ReviewImportJob.filename == DEMO_IMPORT_FILENAME,
        )
    )
    if job is None:
        job = ReviewImportJob(tenant_id=tenant.id, filename=DEMO_IMPORT_FILENAME, file_sha256="0" * 64)
        db.add(job)
    job.status = "completed"
    job.total_rows = len(rows)
    job.accepted_rows = len(rows)
    job.rejected_rows = 0
    job.error_summary = None
    job.file_sha256 = hashlib.sha256(content).hexdigest()
    db.add(job)
    db.flush()

    location_cache: dict[str, Location] = {}
    for row in rows:
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

        review = selected_reviews.get(row.external_review_id or "")
        if review is None:
            review = Review(
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
            db.add(review)
        else:
            review.location_id = location.id
            review.import_job_id = job.id
            review.review_text = row.review_text
            review.rating = row.rating
            review.author_name = row.author_name
            review.review_date = row.review_date
            review.source_name = row.source
            review.external_review_id = row.external_review_id
            review.dedupe_key = row.dedupe_key
            review.status = "needs_attention" if row.rating <= 2 else "new"
            review.priority = "high" if row.rating <= 2 else "medium" if row.rating <= 3 else "normal"
            review.is_synthetic = True
            review.ingestion_source = "demo_csv"

    db.commit()

    for job_id in legacy_job_ids:
        if job_id == job.id:
            continue
        has_reviews = db.scalar(select(Review.id).where(Review.import_job_id == job_id).limit(1))
        if has_reviews is None:
            obsolete_job = db.get(ReviewImportJob, job_id)
            if obsolete_job is not None:
                db.delete(obsolete_job)

    current_location_keys = {" ".join(location.casefold().split()) for location in DEMO_LOCATIONS}
    for location_id in managed_location_ids:
        old_location = db.get(Location, location_id)
        if old_location is None or old_location.normalized_name in current_location_keys:
            continue
        has_reviews = db.scalar(select(Review.id).where(Review.location_id == old_location.id).limit(1))
        if has_reviews is None:
            db.delete(old_location)
    db.commit()
