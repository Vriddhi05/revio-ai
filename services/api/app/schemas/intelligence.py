from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.reviews import AspectOut, ReviewAnalysisOut


class AnalyzeOut(BaseModel):
    requested: int
    analyzed: int
    skipped_cached: int
    created: int
    updated: int
    provider: str
    model_name: str
    pipeline_version: str
    aspect_provider: str
    warnings: list[str]


class IntelligenceStatusOut(BaseModel):
    sentiment_provider: str
    sentiment_model: str
    sentiment_revision: str
    sentiment_mode: str
    aspect_provider: str
    aspect_model: str
    transformer_dependency_installed: bool
    sentence_transformers_dependency_installed: bool
    limitations: list[str]


class SupportingReviewOut(BaseModel):
    id: str
    author_name: str | None
    rating: float
    review_date: date | None
    location: str
    text_excerpt: str
    is_synthetic: bool


class CrisisAlertOut(BaseModel):
    id: str
    signal_type: str
    severity: Literal["low", "medium", "high", "critical"]
    title: str
    reason: str
    affected_count: int
    location: str | None
    supporting_reviews: list[SupportingReviewOut]
    recommended_action: str
    status: Literal["open", "acknowledged", "resolved", "stale"]
    confirmed: bool
    signal_only: bool
    window_start: date
    window_end: date
    detected_at: datetime
    updated_at: datetime


class AlertStatusUpdate(BaseModel):
    status: Literal["acknowledged", "resolved"]


class SentimentCountsOut(BaseModel):
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    unclassified: int = 0


class CategoryCountOut(BaseModel):
    category: str
    count: int


class NegativeTrendPointOut(BaseModel):
    day: date
    count: int


class LocationIntelligenceOut(BaseModel):
    id: str
    name: str
    total_reviews: int
    average_rating: float | None
    sentiment_counts: SentimentCountsOut
    complaint_review_count: int
    urgent_issue_count: int
    top_categories: list[CategoryCountOut]
    negative_trend: list[NegativeTrendPointOut]
    analyzed_reviews: int


class LocationAnalyticsOut(BaseModel):
    days: int
    generated_at: datetime
    total_reviews: int
    analyzed_reviews: int
    locations: list[LocationIntelligenceOut]
