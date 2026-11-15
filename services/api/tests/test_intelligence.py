import hashlib
import json
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.api.dependencies import get_db, get_tenant
from app.api.v1.router import router
from app.db.base import Base
from app.models import CrisisAlert, Location, Review, ReviewAnalysis, Tenant
from app.services.crisis import scan_crisis
from app.services.intelligence import (
    AspectPrediction,
    SentimentPrediction,
    analyze_reviews,
    assess_urgency,
    classify_aspects_batch,
    classify_sentiments,
    detect_language_script,
    deterministic_sentiment,
)
from app.services.location_analytics import location_intelligence


def isolated_store():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine, factory


def add_review(db, tenant, location, text, rating, review_date, status="new", sentiment=None):
    review = Review(
        tenant_id=tenant.id,
        location_id=location.id,
        review_text=text,
        rating=rating,
        author_name="Aditi Sharma",
        review_date=review_date,
        source_name="DEMO fixture",
        external_review_id=None,
        dedupe_key=hashlib.sha256((text + str(review_date)).encode()).hexdigest(),
        status=status,
        priority="normal",
        sentiment=sentiment,
        is_synthetic=True,
        ingestion_source="demo_csv",
    )
    db.add(review)
    db.flush()
    return review


def add_analysis(db, review, sentiment, categories, severity="low"):
    analysis = ReviewAnalysis(
        tenant_id=review.tenant_id,
        review_id=review.id,
        content_hash=hashlib.sha256(review.review_text.encode()).hexdigest(),
        pipeline_version="test-model@1|aspects=rules@1",
        provider="deterministic_fallback",
        model_name="test-rules",
        model_revision="1",
        sentiment=sentiment,
        confidence=0.7,
        confidence_kind="rule_strength_not_calibrated_probability",
        language="English",
        script="Latin",
        language_method="test",
        aspect_provider="interpretable_rules",
        categories_json=json.dumps([
            {"category": category, "confidence": 0.7, "method": "interpretable_multilingual_rules", "evidence": review.review_text[:60]}
            for category in categories
        ]),
        severity=severity,
        urgency_confidence=0.7,
        urgency_reason="Test signal.",
        recommended_action="Review this.",
        evidence_json="[]",
        latency_ms=1.0,
        is_current=True,
    )
    db.add(analysis)
    db.flush()
    return analysis


def test_multilingual_sentiment_output_and_confidence_are_explicit_fallback(monkeypatch):
    import app.services.intelligence as service

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(revio_sentiment_provider="fallback", revio_aspect_provider="rules"))
    samples = [
        "Staff were helpful, khana mast tha.",
        "PhonePe se payment ho gaya, par refund pending hai.",
        "सेवा ठीक थी, कोई खास बात नहीं।",
    ]
    predictions, warning = classify_sentiments(samples)
    assert warning is None
    assert [item.sentiment for item in predictions] == ["positive", "negative", "neutral"]
    assert all(0 <= item.confidence <= 1 for item in predictions)
    assert all(item.provider == "deterministic_fallback" for item in predictions)
    assert all(item.confidence_kind == "rule_strength_not_calibrated_probability" for item in predictions)
    assert detect_language_script(samples[0])[0] == "Hinglish"
    assert detect_language_script(samples[2])[1] == "Devanagari"


def test_transformer_batch_mapping_and_missing_model_fallback(monkeypatch):
    import app.services.intelligence as service

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(revio_sentiment_provider="transformers", revio_aspect_provider="rules"))

    class FakeClassifier:
        model = SimpleNamespace(config=SimpleNamespace(id2label={0: "negative", 1: "neutral", 2: "positive"}))

        def __call__(self, texts, **_kwargs):
            return [
                [{"label": "LABEL_2", "score": 0.93}],
                [{"label": "LABEL_0", "score": 0.81}],
            ]

    monkeypatch.setattr(service, "_load_transformer_pipeline", lambda *_args: FakeClassifier())
    predictions, warning = classify_sentiments(["Good service", "Refund pending"])
    assert warning is None
    assert [item.sentiment for item in predictions] == ["positive", "negative"]
    assert all(item.provider == "transformers" for item in predictions)

    monkeypatch.setattr(service, "_load_transformer_pipeline", lambda *_args: (_ for _ in ()).throw(OSError("model offline")))
    fallback, warning = classify_sentiments(["बिल्कुल खराब"])
    assert warning and "OSError" in warning
    assert fallback[0].provider == "deterministic_fallback"


def test_aspects_are_multilabel_and_include_exact_evidence(monkeypatch):
    import app.services.intelligence as service

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(revio_sentiment_provider="fallback", revio_aspect_provider="rules"))
    text = "PhonePe payment went through, but refund pending; paneer was cold and delivery was late."
    predictions, provider, warning = classify_aspects_batch([text])
    categories = {item.category for item in predictions[0]}
    assert {"upi_payment", "billing_refunds", "food_product_quality", "delivery_order_accuracy", "waiting_time"} <= categories
    assert provider == "interpretable_rules"
    assert warning is None
    assert all(item.evidence and item.method == "interpretable_multilingual_rules" for item in predictions[0])


def test_urgency_does_not_make_a_one_star_review_a_crisis():
    category = [AspectPrediction("staff_service", 0.7, "interpretable_multilingual_rules", "staff")]
    low_star = assess_urgency("Service was disappointing.", 1, category)
    crisis = assess_urgency("I had food poisoning and had to go to hospital.", 4, [])
    payment = assess_urgency("PhonePe charged twice and refund pending.", 3, [
        AspectPrediction("upi_payment", 0.7, "rules", "PhonePe"),
        AspectPrediction("billing_refunds", 0.7, "rules", "refund pending"),
    ])
    assert low_star.severity == "medium"
    assert "rating alone" in low_star.reason
    assert crisis.severity == "critical"
    assert crisis.evidence
    assert payment.severity == "high"
    assert payment.recommended_action


def test_analysis_cache_reuses_current_version_and_reanalyzes_on_version_change(monkeypatch):
    import app.services.intelligence as service

    settings = SimpleNamespace(revio_sentiment_provider="fallback", revio_aspect_provider="rules", crisis_minimum_sample=3)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            db.add(tenant); db.flush()
            location = Location(tenant_id=tenant.id, name="Jaipur, Rajasthan, India", normalized_name="jaipur")
            db.add(location); db.flush()
            add_review(db, tenant, location, "PhonePe refund pending.", 2, date(2026, 11, 14))
            db.commit()

            first = analyze_reviews(db, tenant.id)
            assert first["created"] == 1 and first["analyzed"] == 1
            second = analyze_reviews(db, tenant.id)
            assert second["skipped_cached"] == 1 and second["analyzed"] == 0
            forced = analyze_reviews(db, tenant.id, force=True)
            assert forced["updated"] == 1
            assert db.scalar(select(func.count()).select_from(ReviewAnalysis)) == 1

            settings.revio_sentiment_provider = "transformers"
            monkeypatch.setattr(service, "classify_sentiments", lambda texts: (
                [SentimentPrediction("negative", 0.8, "transformers", "fake-muril", "rev-2", "model_softmax_score_not_calibrated_probability") for _ in texts],
                None,
            ))
            changed = analyze_reviews(db, tenant.id)
            assert changed["created"] == 1
            assert db.scalar(select(func.count()).select_from(ReviewAnalysis)) == 2
            assert db.scalar(select(func.count()).select_from(ReviewAnalysis).where(ReviewAnalysis.is_current.is_(True))) == 1
    finally:
        engine.dispose()


def test_analysis_is_tenant_scoped():
    engine, factory = isolated_store()
    try:
        with factory() as db:
            first_tenant = Tenant(name="First", slug="first", is_demo=False)
            second_tenant = Tenant(name="Second", slug="second", is_demo=False)
            db.add_all([first_tenant, second_tenant]); db.flush()
            first_location = Location(tenant_id=first_tenant.id, name="Jaipur, Rajasthan, India", normalized_name="jaipur")
            second_location = Location(tenant_id=second_tenant.id, name="Chandigarh, India", normalized_name="chandigarh")
            db.add_all([first_location, second_location]); db.flush()
            add_review(db, first_tenant, first_location, "Great service.", 5, date(2026, 11, 14))
            add_review(db, second_tenant, second_location, "Bad service.", 1, date(2026, 11, 14))
            db.commit()
            analyze_reviews(db, first_tenant.id)
            assert db.scalar(select(func.count()).select_from(ReviewAnalysis).where(ReviewAnalysis.tenant_id == first_tenant.id)) == 1
            assert db.scalar(select(func.count()).select_from(ReviewAnalysis).where(ReviewAnalysis.tenant_id == second_tenant.id)) == 0
    finally:
        engine.dispose()


def test_crisis_thresholds_patterns_and_acknowledgement_are_idempotent(monkeypatch):
    import app.services.crisis as crisis_service

    monkeypatch.setattr(crisis_service, "get_settings", lambda: SimpleNamespace(
        crisis_window_days=14, crisis_minimum_sample=3, crisis_negative_rate_rise=0.25,
        crisis_similar_complaint_minimum=3, crisis_cross_location_minimum=2, crisis_customer_repeat_minimum=2,
    ))
    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            db.add(tenant); db.flush()
            jaipur = Location(tenant_id=tenant.id, name="Jaipur, Rajasthan, India", normalized_name="jaipur")
            chandigarh = Location(tenant_id=tenant.id, name="Chandigarh, India", normalized_name="chandigarh")
            db.add_all([jaipur, chandigarh]); db.flush()
            for offset in (1, 2, 3):
                review = add_review(db, tenant, jaipur, "Payment refund pending at Jaipur counter.", 1, date(2026, 11, 15 - offset))
                add_analysis(db, review, "negative", ["billing_refunds", "upi_payment"], "high")
            for offset in (8, 9, 10):
                review = add_review(db, tenant, jaipur, "Good service and clean dining room.", 5, date(2026, 11, 15 - offset))
                add_analysis(db, review, "positive", ["staff_service"], "low")
            other = add_review(db, tenant, chandigarh, "Payment charged twice; refund pending.", 2, date(2026, 11, 13))
            add_analysis(db, other, "negative", ["billing_refunds", "upi_payment"], "high")
            db.commit()

            result = scan_crisis(db, tenant.id, window_days=14, today=date(2026, 11, 15))
            assert result["signals"] >= 2
            alerts = db.scalars(select(CrisisAlert).where(CrisisAlert.tenant_id == tenant.id)).all()
            assert any(alert.signal_type == "negative_review_rise" for alert in alerts)
            assert any(alert.signal_type == "repeated_unresolved_complaint" for alert in alerts)
            assert not any("staff service" in alert.title for alert in alerts)
            assert not any(alert.signal_type == "severe_cross_location_issue" and "staff service" in alert.title for alert in alerts)
            alert = alerts[0]
            alert.status = "acknowledged"
            db.commit()
            scan_crisis(db, tenant.id, window_days=14, today=date(2026, 11, 15))
            db.refresh(alert)
            assert alert.status == "acknowledged"
            assert all(not item.confirmed for item in alerts)
    finally:
        engine.dispose()


def test_crisis_scan_does_not_escalate_positive_mentions_across_locations(monkeypatch):
    import app.services.crisis as crisis_service

    monkeypatch.setattr(crisis_service, "get_settings", lambda: SimpleNamespace(
        crisis_window_days=14, crisis_minimum_sample=3, crisis_negative_rate_rise=0.25,
        crisis_similar_complaint_minimum=3, crisis_cross_location_minimum=2, crisis_customer_repeat_minimum=2,
    ))
    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            db.add(tenant); db.flush()
            jaipur = Location(tenant_id=tenant.id, name="Jaipur, Rajasthan, India", normalized_name="jaipur")
            chandigarh = Location(tenant_id=tenant.id, name="Chandigarh, India", normalized_name="chandigarh")
            db.add_all([jaipur, chandigarh]); db.flush()
            for index, location in enumerate((jaipur, jaipur, chandigarh)):
                review = add_review(db, tenant, location, f"Helpful staff and quick service, visit {index}.", 5, date(2026, 11, 14))
                add_analysis(db, review, "positive", ["staff_service"], "high")
            db.commit()
            result = scan_crisis(db, tenant.id, window_days=14, today=date(2026, 11, 15))
            assert result["signals"] == 0
            assert db.scalar(select(func.count()).select_from(CrisisAlert)) == 0
    finally:
        engine.dispose()


def test_crisis_scan_detects_repeated_unresolved_customer_problem(monkeypatch):
    import app.services.crisis as crisis_service

    monkeypatch.setattr(crisis_service, "get_settings", lambda: SimpleNamespace(
        crisis_window_days=14, crisis_minimum_sample=3, crisis_negative_rate_rise=0.25,
        crisis_similar_complaint_minimum=3, crisis_cross_location_minimum=2, crisis_customer_repeat_minimum=2,
    ))
    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            db.add(tenant); db.flush()
            location = Location(tenant_id=tenant.id, name="Ludhiana, Punjab, India", normalized_name="ludhiana")
            db.add(location); db.flush()
            for day in (date(2026, 11, 12), date(2026, 11, 14)):
                review = add_review(db, tenant, location, "PhonePe refund is still pending.", 2, day)
                add_analysis(db, review, "negative", ["billing_refunds"], "high")
            db.commit()
            result = scan_crisis(db, tenant.id, window_days=14, today=date(2026, 11, 15))
            assert result["signals"] == 1
            alert = db.scalar(select(CrisisAlert))
            assert alert.signal_type == "repeated_unresolved_customer_problem"
            assert alert.affected_count == 2
    finally:
        engine.dispose()


def test_location_analytics_use_persisted_review_analysis():
    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            db.add(tenant); db.flush()
            jaipur = Location(tenant_id=tenant.id, name="Jaipur, Rajasthan, India", normalized_name="jaipur")
            db.add(jaipur); db.flush()
            positive = add_review(db, tenant, jaipur, "Great food.", 5, date(2026, 11, 14))
            negative = add_review(db, tenant, jaipur, "Refund pending.", 1, date(2026, 11, 13))
            add_analysis(db, positive, "positive", ["food_product_quality"])
            add_analysis(db, negative, "negative", ["billing_refunds"], "high")
            db.commit()

            result = location_intelligence(db, tenant.id, days=30, today=date(2026, 11, 15))
            item = result["locations"][0]
            assert result["total_reviews"] == 2
            assert item["average_rating"] == 3.0
            assert item["sentiment_counts"]["positive"] == 1
            assert item["sentiment_counts"]["negative"] == 1
            assert item["complaint_review_count"] == 1
            assert item["urgent_issue_count"] == 1
    finally:
        engine.dispose()


def test_review_api_pagination_filtering_tenant_isolation_and_analysis_failure(monkeypatch):
    import app.api.v1.router as router_module

    engine, factory = isolated_store()
    try:
        with factory() as db:
            tenant = Tenant(name="Demo", slug="revio-demo", is_demo=True)
            other_tenant = Tenant(name="Other", slug="other", is_demo=False)
            db.add_all([tenant, other_tenant]); db.flush()
            location = Location(tenant_id=tenant.id, name="Ludhiana, Punjab, India", normalized_name="ludhiana")
            other_location = Location(tenant_id=other_tenant.id, name="Pune, India", normalized_name="pune")
            db.add_all([location, other_location]); db.flush()
            target = None
            for index in range(5):
                sentiment = "positive" if index % 2 == 0 else "negative"
                review = add_review(db, tenant, location, f"{sentiment} feedback {index}", 5 if sentiment == "positive" else 1, date(2026, 11, 15 - index), sentiment=sentiment)
                if index == 2:
                    target = review
            foreign = add_review(db, other_tenant, other_location, "Foreign tenant review.", 1, date(2026, 11, 14))
            db.commit()

            api = FastAPI()
            api.include_router(router)

            def db_override():
                yield db

            api.dependency_overrides[get_db] = db_override
            api.dependency_overrides[get_tenant] = lambda: tenant
            with TestClient(api) as client:
                page = client.get("/api/v1/reviews", params={"page": 2, "page_size": 2, "sentiment": "positive"})
                assert page.status_code == 200
                assert page.json()["total"] == 3
                assert len(page.json()["items"]) == 1
                assert client.get("/api/v1/reviews/" + foreign.id).status_code == 404

                monkeypatch.setattr(router_module, "analyze_reviews", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
                failure = client.post("/api/v1/intelligence/analyze")
                assert failure.status_code == 503
                assert failure.json()["detail"]["code"] == "analysis_unavailable"

            assert target is not None
    finally:
        engine.dispose()
