"""Review analysis with an optional multilingual transformer and an explicit rules fallback."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import Review, ReviewAnalysis

logger = logging.getLogger(__name__)

MURIL_MODEL = "airzipm/sentiment-analysis-muril-v2"
MURIL_REVISION = "e3f3404276e85565d38649d5a4f35f58b1f255b7"
RULE_MODEL = "revio-multilingual-rules"
RULE_VERSION = "v3"
URGENCY_RULE_VERSION = "v1"
ASPECT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ASPECT_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
ASPECT_RULE_VERSION = "v2"


@dataclass(frozen=True)
class SentimentPrediction:
    sentiment: str
    confidence: float
    provider: str
    model_name: str
    model_revision: str
    confidence_kind: str


@dataclass(frozen=True)
class AspectPrediction:
    category: str
    confidence: float
    method: str
    evidence: str


@dataclass(frozen=True)
class UrgencyPrediction:
    severity: str
    confidence: float
    reason: str
    recommended_action: str
    evidence: tuple[str, ...]


ASPECT_TERMS: dict[str, tuple[str, ...]] = {
    "staff_service": (
        "staff", "server", "waiter", "reception", "rude", "polite", "helpful", "service", "behaviour",
        "behavior", "staff ne", "staff ka behaviour", "सेवा", "स्टाफ", "बदतमीज़", "व्यवहार",
    ),
    "waiting_time": (
        "wait", "waiting", "late", "delay", "long queue", "too long", "40 minutes", "45 minutes",
        "der se", "bahut der", "intezaar", "इंतज़ार", "देर", "लाइन में", "waiting time",
    ),
    "billing_refunds": (
        "bill", "billing", "invoice", "gst invoice", "refund", "refunded", "charged twice", "double charged",
        "refund pending", "bill galat", "paisa wapas", "refund nahi", "रिफंड", "पैसे वापस", "बिल",
    ),
    "upi_payment": (
        "upi", "phonepe", "google pay", "gpay", "payment failed", "payment went through", "paid twice",
        "transaction reference", "payment reference", "scan and pay", "online payment", "पेमेंट", "यूपीआई",
    ),
    "food_product_quality": (
        "food", "taste", "stale", "cold", "undercooked", "overcooked", "fresh", "quality", "product quality",
        "kachori", "paneer", "roti", "खाना", "स्वाद", "बासी", "ठंडा खाना", "गुणवत्ता",
    ),
    "cleanliness_hygiene": (
        "cleanliness", "hygiene", "dirty", "unclean", "cockroach", "insect", "smell", "washroom", "toilet",
        "safai", "ganda", "गंदा", "सफाई", "साफ नहीं", "कीड़ा", "कॉकरोच",
    ),
    "facilities_maintenance": (
        "parking", "ac not working", "air conditioning", "maintenance", "broken", "facility", "lift", "gym equipment",
        "locker", "wifi", "पार्किंग", "एसी काम नहीं", "मरम्मत", "लिफ्ट",
    ),
    "reservations_booking": (
        "reservation", "booked", "booking", "table booking", "room booking", "appointment", "waitlist",
        "reservation cancelled", "booking cancel", "बुकिंग", "टेबल बुक", "कमरा बुक",
    ),
    "delivery_order_accuracy": (
        "delivery", "delivered", "missing item", "wrong order", "wrong item", "order was late", "order arrived",
        "swiggy", "zomato", "roti missing", "item missing", "डिलीवरी", "ऑर्डर गलत", "सामान नहीं आया",
    ),
    "packaging": (
        "packaging", "packed", "packing", "leaked", "spilled", "container", "sealed", "packaging was",
        "पैकिंग", "पैकेट", "डिब्बा", "लीक",
    ),
    "pricing_value": (
        "price", "pricing", "overpriced", "expensive", "value for money", "worth the price", "costly", "too costly",
        "महंगा", "कीमत", "पैसे वसूल", "वैल्यू",
    ),
    "customer_support": (
        "customer support", "support team", "helpline", "no response", "nobody replied", "called support", "complaint ticket",
        "support se", "कोई जवाब नहीं", "हेल्पलाइन", "शिकायत",
    ),
}

ASPECT_LABELS: dict[str, tuple[str, ...]] = {
    "staff_service": ("staff service and employee behaviour", "staff ka behaviour aur seva", "स्टाफ का व्यवहार और सेवा"),
    "waiting_time": ("waiting time, queue or delays", "intezaar aur der", "इंतज़ार का समय और देरी"),
    "billing_refunds": ("billing, invoice or refund issue", "bill ya refund ki dikkat", "बिल या रिफंड की समस्या"),
    "upi_payment": ("UPI, PhonePe, Google Pay or digital payment issue", "UPI ya online payment ki dikkat", "यूपीआई या ऑनलाइन भुगतान की समस्या"),
    "food_product_quality": ("food or product quality, taste, freshness", "khane ya product ki quality", "खाने या उत्पाद की गुणवत्ता"),
    "cleanliness_hygiene": ("cleanliness and hygiene", "safai aur hygiene", "सफाई और स्वच्छता"),
    "facilities_maintenance": ("facilities, parking or maintenance", "suvidha, parking ya maintenance", "सुविधा, पार्किंग या रखरखाव"),
    "reservations_booking": ("reservations, appointments or booking", "reservation ya booking", "रिज़र्वेशन या बुकिंग"),
    "delivery_order_accuracy": ("delivery or wrong and missing order items", "delivery ya galat order", "डिलीवरी या गलत ऑर्डर"),
    "packaging": ("packaging, containers or leakage", "packing aur packaging", "पैकेजिंग या पैकिंग"),
    "pricing_value": ("pricing, expense or value for money", "kimat aur paise ki value", "कीमत और पैसे की वैल्यू"),
    "customer_support": ("customer support and complaint response", "customer support aur shikayat ka jawab", "ग्राहक सहायता और शिकायत का जवाब"),
}

POSITIVE_TERMS = (
    "excellent", "great", "good", "amazing", "fresh", "helpful", "friendly", "quick", "smooth", "clean", "delicious",
    "worth it", "loved", "recommend", "lovely", "crisp", "tidy", "tasty", "neatly", "full of flavour",
    "full of flavor", "made up for it", "small gesture", "appreciated", "paisa vasool", "acha", "achha", "accha",
    "bahut accha", "bohot acha", "mast", "shandar", "badiya", "kaafi badiya", "sahi tha", "seva fast",
    "अच्छा", "बहुत अच्छा", "शानदार",
    "स्वादिष्ट", "मददगार", "बढ़िया", "पसंद आया", "विनम्र", "जल्दी मिली",
)
NEGATIVE_TERMS = (
    "bad", "poor", "terrible", "worst", "rude", "late", "cold", "stale", "dirty", "broken", "missing", "wrong",
    "refund pending", "charged twice", "not worth", "disappointed", "never again", "bakwas", "bekar", "kharab",
    "bahut bura", "paise wapas", "refund nahi", "ganda", "gandi", "late aaya", "galat", "निराश", "खराब", "गंदा",
    "बहुत बुरा", "पैसे वापस", "गलत", "देर से", "रद्द",
)
CRITICAL_TERMS = (
    "food poisoning", "allergic reaction", "hospital", "hospitalised", "hospitalized", "unsafe to eat", "unsafe food",
    "fell ill", "got sick", "चोट लगी", "बीमार पड़", "फूड पॉइजनिंग", "एलर्जी की वजह से", "अस्पताल",
)
HIGH_RISK_TERMS = (
    "charged twice", "paid twice", "refund pending", "refund still pending", "money not returned", "double charged",
    "consumer court", "police complaint", "cockroach", "rat in food", "insect in food", "unsafe", "no refund",
    "पैसे वापस नहीं", "रिफंड नहीं मिला", "दो बार पैसे", "कीड़ा मिला", "चूहा", "consumer forum",
)


def hash_review(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def configured_sentiment_pipeline_version() -> str:
    settings = get_settings()
    sentiment = f"{RULE_MODEL}@{RULE_VERSION}" if settings.revio_sentiment_provider == "fallback" else f"{MURIL_MODEL}@{MURIL_REVISION}"
    aspects = f"interpretable_rules@{ASPECT_RULE_VERSION}" if settings.revio_aspect_provider == "rules" else f"{ASPECT_MODEL}@{ASPECT_REVISION}"
    return f"{sentiment}|aspects={aspects}|urgency=revio-urgency@{URGENCY_RULE_VERSION}"


def configured_aspect_provider() -> str:
    mode = get_settings().revio_aspect_provider
    if mode == "sentence-transformers" and importlib.util.find_spec("sentence_transformers") is None:
        return "interpretable_rules (semantic dependency unavailable)"
    return "multilingual_semantic" if mode == "sentence-transformers" else "interpretable_rules"


@lru_cache(maxsize=2)
def _load_transformer_pipeline(model_name: str, revision: str):
    from transformers import pipeline

    return pipeline(
        "text-classification",
        model=model_name,
        tokenizer=model_name,
        revision=revision,
        truncation=True,
        device=-1,
    )


def _term_matches(text: str, terms: tuple[str, ...]) -> list[tuple[str, int, int]]:
    lowered = text.casefold()
    found: list[tuple[str, int, int]] = []
    for term in terms:
        needle = term.casefold()
        start_at = 0
        while True:
            start = lowered.find(needle, start_at)
            if start < 0:
                break
            end = start + len(needle)
            left_ok = not needle[0].isascii() or not needle[0].isalnum() or start == 0 or not lowered[start - 1].isalnum()
            right_ok = not needle[-1].isascii() or not needle[-1].isalnum() or end == len(lowered) or not lowered[end].isalnum()
            if left_ok and right_ok:
                found.append((text[start:end], start, end))
            start_at = start + max(len(needle), 1)
    return found


def detect_language_script(text: str) -> tuple[str, str, str]:
    devanagari_count = sum("\u0900" <= char <= "\u097f" for char in text)
    latin_count = sum(char.isascii() and char.isalpha() for char in text)
    script = "Mixed" if devanagari_count and latin_count else "Devanagari" if devanagari_count else "Latin" if latin_count else "Other"
    latin_tokens = set(re.findall(r"[a-z]+", text.casefold()))
    roman_hindi = {"hai", "tha", "nahi", "nahin", "bahut", "bohot", "acha", "achha", "accha", "bekar", "kharab", "paisa", "paise", "mera", "mujhe", "karna", "kiya", "seva"}
    has_hinglish = bool(latin_tokens & roman_hindi)
    language = "Hindi-English mixed" if devanagari_count and latin_count else "Hindi" if devanagari_count else "Hinglish" if has_hinglish else "English" if latin_count else "Unknown"
    return language, script, "unicode-script-and-lexicon-heuristic"


def deterministic_sentiment(text: str) -> SentimentPrediction:
    positive = _term_matches(text, POSITIVE_TERMS)
    negative = _term_matches(text, NEGATIVE_TERMS)
    if positive and negative:
        if len(positive) >= 2 * len(negative) + 1:
            sentiment = "positive"
            confidence = min(0.78, 0.55 + 0.05 * len(positive))
        elif len(negative) >= 2 * len(positive) + 1:
            sentiment = "negative"
            confidence = min(0.78, 0.55 + 0.05 * len(negative))
        else:
            sentiment = "neutral"
            confidence = 0.52
    elif len(positive) > len(negative):
        sentiment = "positive"
        confidence = min(0.9, 0.54 + 0.1 * len(positive) + 0.04 * max(0, len(positive) - len(negative) - 1))
    elif negative:
        sentiment = "negative"
        confidence = min(0.9, 0.54 + 0.1 * len(negative) + 0.04 * max(0, len(negative) - len(positive) - 1))
    else:
        sentiment = "neutral"
        confidence = 0.52
    return SentimentPrediction(
        sentiment, round(confidence, 3), "deterministic_fallback", RULE_MODEL, RULE_VERSION,
        "rule_strength_not_calibrated_probability",
    )


def _normalize_transformer_output(raw: Any, classifier: Any) -> tuple[str, float]:
    rows = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], list) else raw
    if isinstance(rows, dict):
        rows = [rows]
    mapped: list[tuple[str, float]] = []
    id2label = getattr(getattr(getattr(classifier, "model", None), "config", None), "id2label", {}) or {}
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().casefold()
        score = float(item.get("score", 0))
        if label.startswith("label_"):
            try:
                label = str(id2label.get(int(label.split("_", 1)[1]), label)).casefold()
            except (TypeError, ValueError):
                pass
        if "pos" in label:
            mapped.append(("positive", score))
        elif "neg" in label:
            mapped.append(("negative", score))
        elif "neu" in label:
            mapped.append(("neutral", score))
    if not mapped:
        raise ValueError("MuRIL returned labels that could not be mapped to positive, negative, or neutral.")
    return max(mapped, key=lambda row: row[1])


def classify_sentiments(texts: list[str]) -> tuple[list[SentimentPrediction], str | None]:
    settings = get_settings()
    if settings.revio_sentiment_provider == "fallback":
        return [deterministic_sentiment(text) for text in texts], None
    try:
        classifier = _load_transformer_pipeline(MURIL_MODEL, MURIL_REVISION)
        outputs = classifier(texts, batch_size=8, truncation=True, max_length=128, top_k=None)
        predictions = []
        for output in outputs:
            sentiment, confidence = _normalize_transformer_output(output, classifier)
            predictions.append(SentimentPrediction(
                sentiment=sentiment, confidence=round(max(0.0, min(1.0, confidence)), 4),
                provider="transformers", model_name=MURIL_MODEL, model_revision=MURIL_REVISION,
                confidence_kind="model_softmax_score_not_calibrated_probability",
            ))
        return predictions, None
    except Exception as exc:
        reason = f"MuRIL unavailable ({type(exc).__name__}); deterministic multilingual rules used."
        logger.warning("%s", reason)
        return [deterministic_sentiment(text) for text in texts], reason


def _excerpt_for(text: str, matches: list[tuple[str, int, int]]) -> str:
    if matches:
        _, start, end = matches[0]
        return text[max(0, start - 70): min(len(text), end + 100)].strip()
    return text[:220].strip()


def detect_rule_aspects(text: str) -> list[AspectPrediction]:
    results = []
    for category, terms in ASPECT_TERMS.items():
        matches = _term_matches(text, terms)
        if matches:
            unique = {match[0].casefold() for match in matches}
            confidence = min(0.96, 0.64 + 0.08 * (len(unique) - 1))
            results.append(AspectPrediction(category, round(confidence, 3), "interpretable_multilingual_rules", _excerpt_for(text, matches)))
    return results


@lru_cache(maxsize=1)
def _load_sentence_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(ASPECT_MODEL, revision=ASPECT_REVISION, device="cpu")


def detect_semantic_aspects_batch(texts: list[str]) -> tuple[list[list[AspectPrediction]], str | None]:
    try:
        model = _load_sentence_model()
        category_order = list(ASPECT_LABELS)
        prototypes = ["; ".join(ASPECT_LABELS[key]) for key in category_order]
        vectors = model.encode(texts + prototypes, normalize_embeddings=True, convert_to_numpy=True, batch_size=32)
        review_vectors = vectors[:len(texts)]
        prototype_vectors = vectors[len(texts):]
        results: list[list[AspectPrediction]] = []
        for text, vector in zip(texts, review_vectors):
            scores = [(key, float(vector @ prototype_vectors[index])) for index, key in enumerate(category_order)]
            selected = sorted(((key, score) for key, score in scores if score >= 0.36), key=lambda item: item[1], reverse=True)
            output = []
            for key, score in selected[:4]:
                exact_matches = _term_matches(text, ASPECT_TERMS[key])
                output.append(AspectPrediction(
                    category=key, confidence=round(max(0.0, min(1.0, score)), 3),
                    method="multilingual_sentence_similarity", evidence=_excerpt_for(text, exact_matches),
                ))
            results.append(output)
        return results, None
    except Exception as exc:
        reason = f"Multilingual semantic model unavailable ({type(exc).__name__}); interpretable rules used."
        logger.warning("%s", reason)
        return [detect_rule_aspects(text) for text in texts], reason


def classify_aspects_batch(texts: list[str]) -> tuple[list[list[AspectPrediction]], str, str | None]:
    if get_settings().revio_aspect_provider == "sentence-transformers":
        predictions, warning = detect_semantic_aspects_batch(texts)
        return predictions, "multilingual_semantic" if warning is None else "interpretable_rules_fallback", warning
    return [detect_rule_aspects(text) for text in texts], "interpretable_rules", None


def assess_urgency(text: str, rating: float, categories: list[AspectPrediction], repeated_categories: set[str] | None = None) -> UrgencyPrediction:
    lowered = text.casefold()
    matched_critical = [phrase for phrase, _, _ in _term_matches(text, CRITICAL_TERMS)]
    matched_high = [phrase for phrase, _, _ in _term_matches(text, HIGH_RISK_TERMS)]
    category_names = {item.category for item in categories}
    repeated = repeated_categories or set()
    evidence = list(dict.fromkeys(matched_critical + matched_high))

    if matched_critical:
        return UrgencyPrediction(
            "critical", 0.97,
            "The customer alleges a possible health or physical-safety impact; this is an unverified review signal requiring immediate human assessment.",
            "Escalate to the on-duty manager now, verify the allegation, and follow the business safety and customer-contact procedures.",
            tuple(evidence),
        )
    if matched_high and ({"upi_payment", "billing_refunds", "cleanliness_hygiene"} & category_names or "payment" in lowered):
        return UrgencyPrediction(
            "high", 0.88,
            "The review contains explicit payment, unresolved refund, or hygiene risk language that needs prompt human follow-up.",
            "Assign to the location lead today; verify transaction or hygiene records and update the customer through an approved channel.",
            tuple(evidence),
        )
    if repeated and any(category.category in repeated for category in categories):
        names = ", ".join(sorted(repeated))
        return UrgencyPrediction(
            "high", 0.82,
            f"This review is part of a repeated unresolved location pattern ({names}); recurrence is a signal for review, not proof of an incident.",
            "Have the location lead review the linked cases together, identify a shared cause, and assign a corrective follow-up.",
            tuple(sorted(repeated)),
        )
    escalation = _term_matches(text, ("consumer court", "police complaint", "nobody replied", "no response", "never again", "किसी ने जवाब नहीं"))
    if escalation and rating <= 3 and category_names:
        return UrgencyPrediction(
            "high", 0.78,
            "The customer describes an unresolved escalation or failed follow-up alongside a service issue.",
            "Route to customer support today, review prior contact history, and assign a named owner for response.",
            tuple(match[0] for match in escalation),
        )
    if rating <= 2:
        return UrgencyPrediction(
            "medium", 0.66, "The low rating needs a timely response; rating alone does not establish a crisis.",
            "Review the complaint details and respond within one business day.",
            tuple(item.evidence for item in categories[:3]),
        )
    if category_names:
        return UrgencyPrediction(
            "medium" if rating <= 3 else "low", 0.62 if rating <= 3 else 0.58,
            "A specific service or product issue is present without an explicit high-risk trigger.",
            "Route to the relevant location or service owner and follow up through the normal response process.",
            tuple(item.evidence for item in categories[:3]),
        )
    return UrgencyPrediction("low", 0.56, "No explicit urgent issue was detected by the configured rules.", "Reply through the normal service queue if a response is appropriate.", ())


def _analysis_payload(analysis: ReviewAnalysis) -> dict[str, Any]:
    return {
        "id": analysis.id, "sentiment": analysis.sentiment, "confidence": analysis.confidence,
        "confidence_kind": analysis.confidence_kind, "provider": analysis.provider, "model_name": analysis.model_name,
        "model_revision": analysis.model_revision, "language": analysis.language, "script": analysis.script,
        "language_method": analysis.language_method, "categories": json.loads(analysis.categories_json),
        "aspect_provider": analysis.aspect_provider, "severity": analysis.severity,
        "urgency_confidence": analysis.urgency_confidence, "urgency_reason": analysis.urgency_reason,
        "recommended_action": analysis.recommended_action, "evidence": json.loads(analysis.evidence_json),
        "latency_ms": analysis.latency_ms, "analyzed_at": analysis.created_at,
    }


def serialize_current_analysis(review: Review) -> dict[str, Any] | None:
    for analysis in review.analysis_records:
        if analysis.is_current:
            return _analysis_payload(analysis)
    return None


def analyze_reviews(db: Session, tenant_id: str, limit: int = 250, force: bool = False) -> dict[str, Any]:
    reviews = db.scalars(
        select(Review).options(selectinload(Review.analysis_records))
        .where(Review.tenant_id == tenant_id)
        .order_by(Review.review_date.desc().nullslast(), Review.imported_at.desc()).limit(limit)
    ).all()
    target_version = configured_sentiment_pipeline_version()
    pending: list[Review] = []
    skipped = 0
    content_hashes: dict[str, str] = {}

    for review in reviews:
        content_hash = hash_review(review.review_text)
        content_hashes[review.id] = content_hash
        existing = db.scalar(select(ReviewAnalysis).where(
            ReviewAnalysis.tenant_id == tenant_id, ReviewAnalysis.review_id == review.id,
            ReviewAnalysis.content_hash == content_hash, ReviewAnalysis.pipeline_version == target_version,
        ))
        if existing and not force:
            for old in review.analysis_records:
                old.is_current = old.id == existing.id
            existing.is_current = True
            review.sentiment = existing.sentiment
            skipped += 1
        else:
            pending.append(review)

    started = time.perf_counter()
    sentiment_predictions, sentiment_warning = classify_sentiments([review.review_text for review in pending]) if pending else ([], None)
    aspect_predictions, aspect_provider, aspect_warning = classify_aspects_batch([review.review_text for review in pending]) if pending else ([], configured_aspect_provider(), None)
    classify_ms = (time.perf_counter() - started) * 1000

    categories_by_review: dict[str, list[AspectPrediction]] = {}
    for review in reviews:
        current = next((record for record in review.analysis_records if record.is_current), None)
        if current is not None:
            categories_by_review[review.id] = [
                AspectPrediction(item["category"], float(item["confidence"]), item["method"], item["evidence"])
                for item in json.loads(current.categories_json)
            ]
    for review, categories in zip(pending, aspect_predictions):
        categories_by_review[review.id] = categories

    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
    repeat_counts: dict[tuple[str, str], int] = {}
    for review in reviews:
        if review.status == "resolved":
            continue
        review_day = review.review_date or review.imported_at.date()
        if review_day < cutoff:
            continue
        current_record = next((record for record in review.analysis_records if record.is_current), None)
        pending_index = next((index for index, item in enumerate(pending) if item.id == review.id), None)
        effective_sentiment = sentiment_predictions[pending_index].sentiment if pending_index is not None else (
            current_record.sentiment if current_record else review.sentiment
        )
        if effective_sentiment != "negative" and review.rating > 2:
            continue
        for category in categories_by_review.get(review.id, []):
            key = (review.location_id, category.category)
            repeat_counts[key] = repeat_counts.get(key, 0) + 1

    created = updated = 0
    for index, review in enumerate(pending):
        sentiment = sentiment_predictions[index]
        categories = aspect_predictions[index]
        repeated = {
            category.category for category in categories
            if review.status != "resolved" and repeat_counts.get((review.location_id, category.category), 0) >= 3
        }
        urgency = assess_urgency(review.review_text, review.rating, categories, repeated)
        language, script, language_method = detect_language_script(review.review_text)
        content_hash = content_hashes[review.id]
        existing = db.scalar(select(ReviewAnalysis).where(
            ReviewAnalysis.tenant_id == tenant_id, ReviewAnalysis.review_id == review.id,
            ReviewAnalysis.content_hash == content_hash, ReviewAnalysis.pipeline_version == target_version,
        ))
        for old in review.analysis_records:
            old.is_current = False
        payload = {
            "provider": sentiment.provider, "model_name": sentiment.model_name, "model_revision": sentiment.model_revision,
            "sentiment": sentiment.sentiment, "confidence": sentiment.confidence, "confidence_kind": sentiment.confidence_kind,
            "language": language, "script": script, "language_method": language_method,
            "aspect_provider": aspect_provider,
            "categories_json": json.dumps([item.__dict__ for item in categories], ensure_ascii=False),
            "severity": urgency.severity, "urgency_confidence": urgency.confidence, "urgency_reason": urgency.reason,
            "recommended_action": urgency.recommended_action,
            "evidence_json": json.dumps(list(urgency.evidence), ensure_ascii=False),
            "latency_ms": round(classify_ms / max(1, len(pending)), 2), "is_current": True,
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.created_at = datetime.now(timezone.utc)
            updated += 1
        else:
            db.add(ReviewAnalysis(
                tenant_id=tenant_id, review_id=review.id, content_hash=content_hash,
                pipeline_version=target_version, **payload,
            ))
            created += 1
        review.sentiment = sentiment.sentiment
        if urgency.severity in {"high", "critical"} and review.status == "new":
            review.status = "needs_attention"
        if urgency.severity in {"high", "critical"}:
            review.priority = "high"
        elif urgency.severity == "medium" and review.priority == "normal":
            review.priority = "medium"

    db.commit()
    warnings = [warning for warning in (sentiment_warning, aspect_warning) if warning]
    first_prediction = sentiment_predictions[0] if sentiment_predictions else None
    return {
        "requested": len(reviews), "analyzed": len(pending), "skipped_cached": skipped, "created": created, "updated": updated,
        "provider": first_prediction.provider if first_prediction else ("cached" if skipped else "none"),
        "model_name": first_prediction.model_name if first_prediction else (MURIL_MODEL if get_settings().revio_sentiment_provider == "transformers" else RULE_MODEL),
        "pipeline_version": target_version, "aspect_provider": aspect_provider, "warnings": warnings,
    }
