from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AspectOut(BaseModel):
    category: Literal[
        "staff_service", "waiting_time", "billing_refunds", "upi_payment", "food_product_quality",
        "cleanliness_hygiene", "facilities_maintenance", "reservations_booking",
        "delivery_order_accuracy", "packaging", "pricing_value", "customer_support",
    ]
    confidence: float = Field(ge=0, le=1)
    method: str
    evidence: str


class ReviewAnalysisOut(BaseModel):
    id: str
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float = Field(ge=0, le=1)
    confidence_kind: str
    provider: str
    model_name: str
    model_revision: str
    language: str
    script: str
    language_method: str
    categories: list[AspectOut]
    aspect_provider: str
    severity: Literal["low", "medium", "high", "critical"]
    urgency_confidence: float = Field(ge=0, le=1)
    urgency_reason: str
    recommended_action: str
    evidence: list[str]
    latency_ms: float
    analyzed_at: datetime


class RowIssueOut(BaseModel):
    code: str
    message: str


class PreviewRowOut(BaseModel):
    row_number: int
    accepted: bool
    review_text: str
    rating: float | None
    author_name: str | None
    review_date: date | None
    location: str
    source: str
    is_synthetic: bool
    issues: list[RowIssueOut]


class RowIssueSummaryOut(BaseModel):
    code: str
    message: str
    count: int


class ImportPreviewOut(BaseModel):
    filename: str
    headers: list[str]
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    preview_rows: list[PreviewRowOut]
    issue_summary: list[RowIssueSummaryOut]


class ImportJobOut(BaseModel):
    id: str
    filename: str
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    created_at: datetime
    errors: list[dict]


class LocationOut(BaseModel):
    id: str
    name: str


class ReviewImportMetadataOut(BaseModel):
    filename: str | None
    imported_at: datetime
    ingestion_source: str
    record_origin: str


class ReviewOut(BaseModel):
    id: str
    review_text: str
    rating: float
    author_name: str | None
    review_date: date | None
    source_name: str
    external_review_id: str | None
    location: LocationOut
    status: str
    priority: str
    sentiment: str | None
    is_synthetic: bool
    import_metadata: ReviewImportMetadataOut
    analysis: ReviewAnalysisOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ReviewPageOut(BaseModel):
    items: list[ReviewOut]
    page: int
    page_size: int
    total: int
    pages: int


class ReviewStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|needs_attention|resolved)$")


class TrendPointOut(BaseModel):
    day: date
    count: int


class AnalyticsSummaryOut(BaseModel):
    total_reviews: int
    average_rating: float | None
    needs_attention: int
    locations: int
    trend: list[TrendPointOut]
