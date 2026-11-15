import hashlib
import importlib.util
import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.api.dependencies import CurrentTenant, DbSession
from app.core.config import get_settings
from app.models import CrisisAlert, Location, Review, ReviewImportJob, Tenant
from app.schemas.intelligence import (
    AlertStatusUpdate,
    AnalyzeOut,
    CrisisAlertOut,
    IntelligenceStatusOut,
    LocationAnalyticsOut,
)
from app.schemas.reviews import (
    AnalyticsSummaryOut,
    ImportJobOut,
    ImportPreviewOut,
    LocationOut,
    PreviewRowOut,
    ReviewImportMetadataOut,
    ReviewOut,
    ReviewPageOut,
    ReviewStatusUpdate,
    RowIssueSummaryOut,
    RowIssueOut,
    TrendPointOut,
)
from app.services.crisis import list_crisis_alerts, scan_crisis
from app.services.intelligence import (
    ASPECT_MODEL,
    MURIL_MODEL,
    MURIL_REVISION,
    RULE_MODEL,
    RULE_VERSION,
    analyze_reviews,
    configured_aspect_provider,
    serialize_current_analysis,
)
from app.services.location_analytics import location_intelligence
from app.services.review_csv import CsvImportError, mark_duplicates, parse_review_csv

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)


@router.get("/demo/reviews.csv", include_in_schema=False)
def download_fictional_demo_csv() -> FileResponse:
    sample_path = Path(__file__).resolve().parents[5] / "data" / "demo" / "reviews.csv"
    return FileResponse(sample_path, media_type="text/csv", filename="revio-india-demo-synthetic-reviews.csv")


def _job_out(job: ReviewImportJob) -> ImportJobOut:
    errors = json.loads(job.error_summary) if job.error_summary else []
    return ImportJobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        total_rows=job.total_rows,
        accepted_rows=job.accepted_rows,
        rejected_rows=job.rejected_rows,
        created_at=job.created_at,
        errors=errors,
    )


def _review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        review_text=review.review_text,
        rating=review.rating,
        author_name=review.author_name,
        review_date=review.review_date,
        source_name=review.source_name,
        external_review_id=review.external_review_id,
        location=LocationOut(id=review.location.id, name=review.location.name),
        status=review.status,
        priority=review.priority,
        sentiment=review.sentiment,
        is_synthetic=review.is_synthetic,
        import_metadata=ReviewImportMetadataOut(
            filename=review.import_job.filename if review.import_job else None,
            imported_at=review.imported_at,
            ingestion_source=review.ingestion_source,
            record_origin="DEMO / SYNTHETIC DATA" if review.is_synthetic else "CSV import",
        ),
        analysis=serialize_current_analysis(review),
    )


def _parse_error(exc: CsvImportError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": exc.code, "message": str(exc), "details": exc.details},
    )


def _preview_out(filename: str, preview) -> ImportPreviewOut:
    issue_counts = Counter(
        (issue.code, issue.message)
        for row in preview.rows
        for issue in row.issues
    )
    return ImportPreviewOut(
        filename=filename,
        headers=preview.headers,
        total_rows=preview.total_rows,
        accepted_rows=preview.accepted_rows,
        rejected_rows=preview.rejected_rows,
        preview_rows=[
            PreviewRowOut(
                row_number=row.row_number,
                accepted=row.accepted,
                review_text=row.review_text[:180],
                rating=row.rating if row.rating else None,
                author_name=row.author_name,
                review_date=row.review_date,
                location=row.location,
                source=row.source,
                is_synthetic=row.is_synthetic,
                issues=[RowIssueOut(code=issue.code, message=issue.message) for issue in row.issues],
            )
            for row in preview.rows[:12]
        ],
        issue_summary=[
            RowIssueSummaryOut(code=code, message=message, count=count)
            for (code, message), count in issue_counts.items()
        ],
    )


async def _read_csv(file: UploadFile) -> tuple[str, bytes]:
    filename = Path(file.filename or "reviews.csv").name[:255]
    content = await file.read(10 * 1024 * 1024 + 1)
    return filename, content


@router.post("/reviews/imports/preview", response_model=ImportPreviewOut)
async def preview_reviews_csv(
    tenant: CurrentTenant,
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportPreviewOut:
    filename, content = await _read_csv(file)
    try:
        preview = mark_duplicates(parse_review_csv(content), db, tenant.id)
    except CsvImportError as exc:
        raise _parse_error(exc) from exc
    return _preview_out(filename, preview)


@router.post("/reviews/imports", response_model=ImportJobOut, status_code=201)
async def import_reviews_csv(
    tenant: CurrentTenant,
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportJobOut:
    filename, content = await _read_csv(file)
    try:
        preview = mark_duplicates(parse_review_csv(content), db, tenant.id)
    except CsvImportError as exc:
        raise _parse_error(exc) from exc

    issues = [
        {"row_number": row.row_number, "code": issue.code, "message": issue.message}
        for row in preview.rows
        for issue in row.issues
    ]
    job = ReviewImportJob(
        tenant_id=tenant.id,
        filename=filename,
        status="completed",
        total_rows=preview.total_rows,
        accepted_rows=preview.accepted_rows,
        rejected_rows=preview.rejected_rows,
        error_summary=json.dumps(issues, ensure_ascii=False) if issues else None,
        file_sha256=hashlib.sha256(content).hexdigest(),
    )
    db.add(job)
    try:
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

            status = "needs_attention" if row.rating <= 2 else "new"
            priority = "high" if row.rating <= 2 else "medium" if row.rating <= 3 else "normal"
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
                    status=status,
                    priority=priority,
                    is_synthetic=row.is_synthetic,
                    ingestion_source="demo_csv" if row.is_synthetic else "csv",
                )
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate_import", "message": "A duplicate review was detected while importing. Please preview the file again."},
        ) from exc
    db.refresh(job)
    return _job_out(job)


@router.get("/reviews/imports/{job_id}", response_model=ImportJobOut)
def get_import_job(job_id: str, tenant: CurrentTenant, db: DbSession) -> ImportJobOut:
    job = db.scalar(select(ReviewImportJob).where(ReviewImportJob.id == job_id, ReviewImportJob.tenant_id == tenant.id))
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "import_not_found", "message": "Import job not found."})
    return _job_out(job)


@router.get("/locations", response_model=list[LocationOut])
def list_locations(tenant: CurrentTenant, db: DbSession) -> list[LocationOut]:
    locations = db.scalars(
        select(Location).where(Location.tenant_id == tenant.id).order_by(Location.name.asc())
    ).all()
    return [LocationOut(id=location.id, name=location.name) for location in locations]


@router.get("/reviews", response_model=ReviewPageOut)
def list_reviews(
    tenant: CurrentTenant,
    db: DbSession,
    search: str | None = Query(default=None, max_length=160),
    location_id: str | None = None,
    rating: float | None = Query(default=None, ge=1, le=5),
    sentiment: Literal["positive", "neutral", "negative"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: Literal["new", "needs_attention", "resolved"] | None = None,
    sort: Literal["newest", "priority"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReviewPageOut:
    query = select(Review).options(
        joinedload(Review.location), joinedload(Review.import_job), selectinload(Review.analysis_records)
    ).where(Review.tenant_id == tenant.id)
    count_query = select(func.count(Review.id)).where(Review.tenant_id == tenant.id)
    filters = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(or_(Review.review_text.ilike(term), Review.author_name.ilike(term)))
    if location_id:
        filters.append(Review.location_id == location_id)
    if rating is not None:
        filters.append(Review.rating == rating)
    if sentiment:
        filters.append(Review.sentiment == sentiment)
    if date_from:
        filters.append(Review.review_date >= date_from)
    if date_to:
        filters.append(Review.review_date <= date_to)
    if status:
        filters.append(Review.status == status)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    if sort == "priority":
        priority_rank = case((Review.priority == "high", 0), (Review.priority == "medium", 1), else_=2)
        query = query.order_by(priority_rank, Review.review_date.desc().nullslast(), Review.imported_at.desc())
    else:
        query = query.order_by(Review.review_date.desc().nullslast(), Review.imported_at.desc())

    total = db.scalar(count_query) or 0
    reviews = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return ReviewPageOut(
        items=[_review_out(review) for review in reviews],
        page=page,
        page_size=page_size,
        total=total,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/reviews/{review_id}", response_model=ReviewOut)
def get_review(review_id: str, tenant: CurrentTenant, db: DbSession) -> ReviewOut:
    review = db.scalar(
        select(Review)
        .options(joinedload(Review.location), joinedload(Review.import_job), selectinload(Review.analysis_records))
        .where(Review.id == review_id, Review.tenant_id == tenant.id)
    )
    if review is None:
        raise HTTPException(status_code=404, detail={"code": "review_not_found", "message": "Review not found."})
    return _review_out(review)


@router.patch("/reviews/{review_id}/status", response_model=ReviewOut)
def update_review_status(
    review_id: str,
    payload: ReviewStatusUpdate,
    tenant: CurrentTenant,
    db: DbSession,
) -> ReviewOut:
    review = db.scalar(
        select(Review)
        .options(joinedload(Review.location), joinedload(Review.import_job), selectinload(Review.analysis_records))
        .where(Review.id == review_id, Review.tenant_id == tenant.id)
    )
    if review is None:
        raise HTTPException(status_code=404, detail={"code": "review_not_found", "message": "Review not found."})
    review.status = payload.status
    db.commit()
    db.refresh(review)
    return _review_out(review)


@router.get("/analytics/summary", response_model=AnalyticsSummaryOut)
def analytics_summary(
    tenant: CurrentTenant,
    db: DbSession,
    days: int = Query(default=30, ge=7, le=90),
) -> AnalyticsSummaryOut:
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=days - 1)
    total = db.scalar(select(func.count(Review.id)).where(Review.tenant_id == tenant.id)) or 0
    average = db.scalar(select(func.avg(Review.rating)).where(Review.tenant_id == tenant.id))
    needs_attention = db.scalar(
        select(func.count(Review.id)).where(Review.tenant_id == tenant.id, Review.status == "needs_attention")
    ) or 0
    locations = db.scalar(select(func.count(Location.id)).where(Location.tenant_id == tenant.id)) or 0
    grouped = db.execute(
        select(Review.review_date, func.count(Review.id))
        .where(Review.tenant_id == tenant.id, Review.review_date >= start_day, Review.review_date <= today)
        .group_by(Review.review_date)
    ).all()
    by_day = {day: count for day, count in grouped if day}
    trend = [TrendPointOut(day=start_day + timedelta(days=index), count=by_day.get(start_day + timedelta(days=index), 0)) for index in range(days)]
    return AnalyticsSummaryOut(
        total_reviews=total,
        average_rating=round(float(average), 2) if average is not None else None,
        needs_attention=needs_attention,
        locations=locations,
        trend=trend,
    )


@router.get("/intelligence/status", response_model=IntelligenceStatusOut)
def intelligence_status() -> IntelligenceStatusOut:
    settings = get_settings()
    return IntelligenceStatusOut(
        sentiment_provider=settings.revio_sentiment_provider,
        sentiment_model=MURIL_MODEL if settings.revio_sentiment_provider == "transformers" else RULE_MODEL,
        sentiment_revision=MURIL_REVISION if settings.revio_sentiment_provider == "transformers" else RULE_VERSION,
        sentiment_mode=settings.revio_sentiment_provider,
        aspect_provider=configured_aspect_provider(),
        aspect_model=ASPECT_MODEL if settings.revio_aspect_provider == "sentence-transformers" else "multilingual rules v1",
        transformer_dependency_installed=importlib.util.find_spec("transformers") is not None,
        sentence_transformers_dependency_installed=importlib.util.find_spec("sentence_transformers") is not None,
        limitations=[
            "Rule fallback scores are heuristic strength indicators, not calibrated probabilities.",
            "The multilingual aspect rules are interpretable phrase matches; optional semantic similarity is experimental.",
            "No model-card benchmark is treated as a REVIO evaluation result.",
        ],
    )


@router.post("/intelligence/analyze", response_model=AnalyzeOut)
def analyze_workspace_reviews(
    tenant: CurrentTenant,
    db: DbSession,
    limit: int = Query(default=250, ge=1, le=1000),
    force: bool = Query(default=False),
) -> AnalyzeOut:
    try:
        return AnalyzeOut(**analyze_reviews(db, tenant.id, limit=limit, force=force))
    except Exception as exc:
        db.rollback()
        logger.exception("Review analysis failed for tenant %s", tenant.slug)
        raise HTTPException(
            status_code=503,
            detail={"code": "analysis_unavailable", "message": "Review analysis could not be completed. Retry after checking the configured model provider."},
        ) from exc


@router.get("/crisis/alerts", response_model=list[CrisisAlertOut])
def get_crisis_alerts(
    tenant: CurrentTenant,
    db: DbSession,
    status: Literal["open", "acknowledged", "resolved", "stale"] | None = None,
) -> list[CrisisAlertOut]:
    return [CrisisAlertOut(**alert) for alert in list_crisis_alerts(db, tenant.id, status=status)]


@router.post("/crisis/scan")
def run_crisis_scan(
    tenant: CurrentTenant,
    db: DbSession,
    window_days: int = Query(default=14, ge=7, le=30),
) -> dict[str, int]:
    try:
        return scan_crisis(db, tenant.id, window_days=window_days)
    except Exception as exc:
        db.rollback()
        logger.exception("Crisis signal scan failed for tenant %s", tenant.slug)
        raise HTTPException(
            status_code=503,
            detail={"code": "crisis_scan_failed", "message": "Crisis signal scan failed. Retry after checking the analysis data."},
        ) from exc


@router.patch("/crisis/alerts/{alert_id}/status", response_model=CrisisAlertOut)
def update_crisis_alert_status(
    alert_id: str,
    payload: AlertStatusUpdate,
    tenant: CurrentTenant,
    db: DbSession,
) -> CrisisAlertOut:
    alert = db.scalar(select(CrisisAlert).where(CrisisAlert.id == alert_id, CrisisAlert.tenant_id == tenant.id))
    if alert is None:
        raise HTTPException(status_code=404, detail={"code": "alert_not_found", "message": "Crisis signal not found."})
    alert.status = payload.status
    alert.updated_at = datetime.now(timezone.utc)
    db.commit()
    refreshed = next((item for item in list_crisis_alerts(db, tenant.id) if item["id"] == alert_id), None)
    if refreshed is None:
        raise HTTPException(status_code=404, detail={"code": "alert_not_found", "message": "Crisis signal not found."})
    return CrisisAlertOut(**refreshed)


@router.get("/analytics/location-intelligence", response_model=LocationAnalyticsOut)
def analytics_by_location(
    tenant: CurrentTenant,
    db: DbSession,
    days: int = Query(default=30, ge=7, le=90),
) -> LocationAnalyticsOut:
    return LocationAnalyticsOut(**location_intelligence(db, tenant.id, days=days))
