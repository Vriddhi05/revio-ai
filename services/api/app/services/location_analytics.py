import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Location, Review


def location_intelligence(db: Session, tenant_id: str, days: int = 30, today: date | None = None) -> dict:
    anchor = today or datetime.now(timezone.utc).date()
    start = anchor - timedelta(days=days - 1)
    locations = db.scalars(
        select(Location).where(Location.tenant_id == tenant_id).order_by(Location.name)
    ).all()
    reviews = db.scalars(
        select(Review).options(selectinload(Review.analysis_records))
        .where(Review.tenant_id == tenant_id)
    ).all()
    grouped: dict[str, list[Review]] = defaultdict(list)
    for review in reviews:
        grouped[review.location_id].append(review)

    location_results = []
    for location in locations:
        rows = grouped.get(location.id, [])
        sentiment_counts = Counter({"positive": 0, "neutral": 0, "negative": 0, "unclassified": 0})
        category_counts: Counter[str] = Counter()
        negative_by_day: Counter[date] = Counter()
        ratings: list[float] = []
        analyzed = complaint_reviews = urgent = 0
        for review in rows:
            ratings.append(float(review.rating))
            current = next((analysis for analysis in review.analysis_records if analysis.is_current), None)
            if not current:
                sentiment_counts["unclassified"] += 1
                continue
            analyzed += 1
            sentiment_counts[current.sentiment] += 1
            categories = json.loads(current.categories_json)
            is_complaint_review = current.sentiment == "negative" or review.rating <= 3
            if categories and is_complaint_review:
                complaint_reviews += 1
            if is_complaint_review:
                for item in categories:
                    category_counts[item["category"]] += 1
            if current.severity in {"high", "critical"}:
                urgent += 1
            review_day = review.review_date or review.imported_at.date()
            if start <= review_day <= anchor and current.sentiment == "negative":
                negative_by_day[review_day] += 1
        trend = [
            {"day": start + timedelta(days=index), "count": negative_by_day.get(start + timedelta(days=index), 0)}
            for index in range(days)
        ]
        location_results.append({
            "id": location.id,
            "name": location.name,
            "total_reviews": len(rows),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "sentiment_counts": dict(sentiment_counts),
            "complaint_review_count": complaint_reviews,
            "urgent_issue_count": urgent,
            "top_categories": [{"category": category, "count": count} for category, count in category_counts.most_common(6)],
            "negative_trend": trend,
            "analyzed_reviews": analyzed,
        })
    return {
        "days": days,
        "generated_at": datetime.now(timezone.utc),
        "total_reviews": sum(len(rows) for rows in grouped.values()),
        "analyzed_reviews": sum(item["analyzed_reviews"] for item in location_results),
        "locations": location_results,
    }
