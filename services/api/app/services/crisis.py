import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.models import CrisisAlert, Review


def scan_crisis(db: Session, tenant_id: str, window_days: int | None = None, today: date | None = None) -> dict[str, int]:
    settings = get_settings()
    days = window_days or settings.crisis_window_days
    anchor = today or datetime.now(timezone.utc).date()
    recent_start = anchor - timedelta(days=days - 1)
    previous_start = anchor - timedelta(days=days * 2 - 1)
    recent_end = anchor
    previous_end = recent_start - timedelta(days=1)
    reviews = db.scalars(
        select(Review).options(joinedload(Review.location), selectinload(Review.analysis_records))
        .where(Review.tenant_id == tenant_id)
    ).unique().all()

    dated = []
    for review in reviews:
        review_day = review.review_date or review.imported_at.date()
        analysis = next((item for item in review.analysis_records if item.is_current), None)
        if analysis:
            dated.append((review, analysis, review_day))

    signals: list[dict] = []
    locations = {review.location_id: review.location.name for review, _, _ in dated}
    by_location: dict[str, list] = defaultdict(list)
    for review, analysis, day in dated:
        by_location[review.location_id].append((review, analysis, day))

    for location_id, rows in by_location.items():
        current = [(review, analysis, day) for review, analysis, day in rows if recent_start <= day <= recent_end]
        previous = [(review, analysis, day) for review, analysis, day in rows if previous_start <= day <= previous_end]
        negative_current = [row for row in current if row[1].sentiment == "negative"]
        negative_previous = [row for row in previous if row[1].sentiment == "negative"]
        current_rate = len(negative_current) / len(current) if current else 0.0
        previous_rate = len(negative_previous) / len(previous) if previous else 0.0
        rise = current_rate - previous_rate
        enough = len(current) >= settings.crisis_minimum_sample and len(negative_current) >= max(2, settings.crisis_minimum_sample - 1)
        rise_threshold = settings.crisis_negative_rate_rise if previous else max(0.45, settings.crisis_negative_rate_rise)
        if enough and rise >= rise_threshold:
            signals.append({
                "key": f"negative_rise:{location_id}:{recent_start.isoformat()}",
                "type": "negative_review_rise",
                "severity": "high" if current_rate >= 0.6 else "medium",
                "title": f"Negative review rate rising at {locations[location_id]}",
                "location_id": location_id,
                "reason": (
                    f"{len(negative_current)} of {len(current)} analyzed reviews in the last {days} days are negative "
                    f"({current_rate:.0%}), compared with {len(negative_previous)} of {len(previous)} in the prior window "
                    f"({previous_rate:.0%}); a {rise:.0%} rate increase crossed the configured threshold. "
                    "This is an automated signal, not a confirmed incident."
                ),
                "reviews": [row[0] for row in negative_current],
                "action": "Review the linked feedback with the location lead, verify the shared themes, and assign response owners.",
                "start": recent_start,
                "end": recent_end,
            })

    repeated: dict[tuple[str, str], list] = defaultdict(list)
    repeated_customer: dict[tuple[str, str, str], list] = defaultdict(list)
    cross_location: dict[str, list] = defaultdict(list)
    for review, analysis, day in dated:
        if not recent_start <= day <= recent_end:
            continue
        categories = json.loads(analysis.categories_json)
        for item in categories:
            category = item.get("category")
            if not category:
                continue
            if review.status != "resolved" and (analysis.sentiment == "negative" or review.rating <= 2):
                repeated[(review.location_id, category)].append((review, analysis, day))
                if review.author_name and review.author_name.strip():
                    customer_key = (review.location_id, review.author_name.strip().casefold(), category)
                    repeated_customer[customer_key].append((review, analysis, day))
            if analysis.severity in {"high", "critical"} and (analysis.sentiment == "negative" or review.rating <= 2):
                cross_location[category].append((review, analysis, day))

    for (location_id, author_key, category), rows in repeated_customer.items():
        if len(rows) < settings.crisis_customer_repeat_minimum:
            continue
        display_author = next(row[0].author_name for row in rows if row[0].author_name)
        signals.append({
            "key": f"repeat_customer:{location_id}:{author_key}:{category}:{recent_start.isoformat()}",
            "type": "repeated_unresolved_customer_problem",
            "severity": "high" if category in {"upi_payment", "billing_refunds", "cleanliness_hygiene"} else "medium",
            "title": f"Repeated {category.replace('_', ' ')} reports from one customer",
            "location_id": location_id,
            "reason": (
                f"{display_author} has {len(rows)} unresolved reviews mentioning {category.replace('_', ' ')} "
                f"at {locations.get(location_id, 'this location')} within {days} days. Confirm the customer history "
                "and details before treating this as a verified pattern."
            ),
            "reviews": [row[0] for row in rows],
            "action": "Check the linked case history and contact the customer through an approved channel with a named owner.",
            "start": recent_start,
            "end": recent_end,
        })

    for (location_id, category), rows in repeated.items():
        if len(rows) < settings.crisis_similar_complaint_minimum:
            continue
        signals.append({
            "key": f"repeat:{location_id}:{category}:{recent_start.isoformat()}",
            "type": "repeated_unresolved_complaint",
            "severity": "high" if category in {"upi_payment", "billing_refunds", "cleanliness_hygiene"} else "medium",
            "title": f"Recurring {category.replace('_', ' ')} complaints at {locations.get(location_id, 'this location')}",
            "location_id": location_id,
            "reason": (
                f"{len(rows)} unresolved reviews at {locations.get(location_id, 'this location')} mention {category.replace('_', ' ')} "
                f"within {days} days. Recurrence is a pattern for human review, not proof of an incident."
            ),
            "reviews": [row[0] for row in rows],
            "action": "Review these cases together, check for a shared operational cause, and assign a corrective follow-up.",
            "start": recent_start,
            "end": recent_end,
        })

    for category, rows in cross_location.items():
        location_ids = {row[0].location_id for row in rows}
        if len(location_ids) < 2 or len(rows) < settings.crisis_cross_location_minimum:
            continue
        critical_count = sum(row[1].severity == "critical" for row in rows)
        signals.append({
            "key": f"cross_location:{category}:{recent_start.isoformat()}",
            "type": "severe_cross_location_issue",
            "severity": "critical" if critical_count >= 2 else "high",
            "title": f"Severe {category.replace('_', ' ')} signals across locations",
            "location_id": None,
            "reason": (
                f"{len(rows)} high or critical analyses mention {category.replace('_', ' ')} across "
                f"{len(location_ids)} locations during the last {days} days. These are review signals requiring "
                "verification; no real-world incident has been confirmed."
            ),
            "reviews": [row[0] for row in rows],
            "action": "Notify the operations owner, compare location records, and verify whether the reports share a cause.",
            "start": recent_start,
            "end": recent_end,
        })

    created = updated = 0
    active_keys = {signal["key"] for signal in signals}
    for signal in signals:
        alert = db.scalar(select(CrisisAlert).where(
            CrisisAlert.tenant_id == tenant_id, CrisisAlert.signal_key == signal["key"]
        ))
        review_ids = list(dict.fromkeys(review.id for review in signal["reviews"]))
        if alert is None:
            alert = CrisisAlert(
                tenant_id=tenant_id,
                signal_key=signal["key"],
                signal_type=signal["type"],
                status="open",
                confirmed=False,
                detected_at=datetime.now(timezone.utc),
            )
            db.add(alert)
            created += 1
        else:
            updated += 1
            if alert.status == "stale":
                alert.status = "open"
        alert.location_id = signal["location_id"]
        alert.severity = signal["severity"]
        alert.title = signal["title"]
        alert.reason = signal["reason"]
        alert.affected_count = len(review_ids)
        alert.supporting_review_ids_json = json.dumps(review_ids)
        alert.recommended_action = signal["action"]
        alert.window_start = signal["start"]
        alert.window_end = signal["end"]
        alert.updated_at = datetime.now(timezone.utc)
        # Acknowledgement is preserved across repeated deterministic scans.

    stale_alerts = db.scalars(select(CrisisAlert).where(
        CrisisAlert.tenant_id == tenant_id,
        CrisisAlert.window_start == recent_start,
        CrisisAlert.window_end == recent_end,
        CrisisAlert.status == "open",
    )).all()
    for alert in stale_alerts:
        if alert.signal_key not in active_keys:
            alert.status = "stale"
            alert.reason = alert.reason + " The latest scan no longer meets this signal's configured threshold."
            alert.updated_at = datetime.now(timezone.utc)

    db.commit()
    return {"created": created, "updated": updated, "signals": len(signals)}


def list_crisis_alerts(db: Session, tenant_id: str, status: str | None = None) -> list[dict]:
    query = select(CrisisAlert).options(joinedload(CrisisAlert.location)).where(CrisisAlert.tenant_id == tenant_id)
    if status:
        query = query.where(CrisisAlert.status == status)
    else:
        query = query.where(CrisisAlert.status != "stale")
    alerts = db.scalars(query.order_by(CrisisAlert.detected_at.desc())).unique().all()
    review_ids = {review_id for alert in alerts for review_id in json.loads(alert.supporting_review_ids_json)}
    reviews_by_id = {}
    if review_ids:
        supporting = db.scalars(
            select(Review).options(joinedload(Review.location))
            .where(Review.tenant_id == tenant_id, Review.id.in_(review_ids))
        ).unique().all()
        reviews_by_id = {review.id: review for review in supporting}

    result = []
    for alert in alerts:
        refs = []
        for review_id in json.loads(alert.supporting_review_ids_json):
            review = reviews_by_id.get(review_id)
            if review:
                refs.append({
                    "id": review.id,
                    "author_name": review.author_name,
                    "rating": review.rating,
                    "review_date": review.review_date,
                    "location": review.location.name,
                    "text_excerpt": review.review_text[:240],
                    "is_synthetic": review.is_synthetic,
                })
        result.append({
            "id": alert.id,
            "signal_type": alert.signal_type,
            "severity": alert.severity,
            "title": alert.title,
            "reason": alert.reason,
            "affected_count": alert.affected_count,
            "location": alert.location.name if alert.location else None,
            "supporting_reviews": refs,
            "recommended_action": alert.recommended_action,
            "status": alert.status,
            "confirmed": alert.confirmed,
            "signal_only": not alert.confirmed,
            "window_start": alert.window_start,
            "window_end": alert.window_end,
            "detected_at": alert.detected_at,
            "updated_at": alert.updated_at,
        })
    return result
