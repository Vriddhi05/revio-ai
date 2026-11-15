"""Run reproducible metrics on the separate hand-labeled Indian evaluation set."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.intelligence import (  # noqa: E402
    ASPECT_MODEL,
    ASPECT_REVISION,
    ASPECT_RULE_VERSION,
    MURIL_MODEL,
    MURIL_REVISION,
    URGENCY_RULE_VERSION,
    assess_urgency,
    classify_aspects_batch,
    classify_sentiments,
    detect_language_script,
)
from app.core.config import get_settings  # noqa: E402


LABELS = ("positive", "neutral", "negative")


def precision_recall_f1(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent * len(ordered)) - 1)]


def evaluate(dataset_path: Path, use_semantic: bool = False) -> dict:
    records = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("Evaluation set contains no records.")
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Evaluation record IDs must be unique.")

    truth = [record["gold_sentiment"] for record in records]
    predicted: list[str] = []
    latencies: list[float] = []
    predictions = []
    for record in records:
        start = time.perf_counter()
        result, _warning = classify_sentiments([record["text"]])
        latencies.append((time.perf_counter() - start) * 1000)
        predictions.append(result[0])
        predicted.append(result[0].sentiment)

    confusion = {actual: {guess: 0 for guess in LABELS} for actual in LABELS}
    for actual, guess in zip(truth, predicted):
        confusion[actual][guess] += 1
    per_class = {}
    for label in LABELS:
        tp = sum(1 for actual, guess in zip(truth, predicted) if actual == label and guess == label)
        fp = sum(1 for actual, guess in zip(truth, predicted) if actual != label and guess == label)
        fn = sum(1 for actual, guess in zip(truth, predicted) if actual == label and guess != label)
        per_class[label] = precision_recall_f1(tp, fp, fn)
    accuracy = sum(actual == guess for actual, guess in zip(truth, predicted)) / len(records)

    grouped: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        grouped.setdefault(record["language_group"], []).append(index)
    per_language = {}
    for group, indices in grouped.items():
        per_language[group] = {
            "sample_count": len(indices),
            "accuracy": round(sum(truth[i] == predicted[i] for i in indices) / len(indices), 4),
            "mean_rule_or_model_score": round(statistics.mean(predictions[i].confidence for i in indices), 4),
        }

    texts = [record["text"] for record in records]
    if use_semantic:
        categories, aspect_provider, aspect_warning = classify_aspects_batch(texts)
    else:
        from app.services.intelligence import detect_rule_aspects

        categories = [detect_rule_aspects(text) for text in texts]
        aspect_provider, aspect_warning = "interpretable_rules", None
    category_names = sorted({category for record in records for category in record["gold_categories"]})
    category_metrics = {}
    category_true_positive = 0
    category_false_positive = 0
    category_false_negative = 0
    for category in category_names:
        tp = fp = fn = 0
        for record, inferred in zip(records, categories):
            actual_has = category in record["gold_categories"]
            predicted_has = any(item.category == category for item in inferred)
            tp += int(actual_has and predicted_has)
            fp += int(not actual_has and predicted_has)
            fn += int(actual_has and not predicted_has)
        category_metrics[category] = precision_recall_f1(tp, fp, fn)
        category_true_positive += tp
        category_false_positive += fp
        category_false_negative += fn
    category_micro = precision_recall_f1(category_true_positive, category_false_positive, category_false_negative)
    category_macro_f1 = statistics.mean(item["f1"] for item in category_metrics.values()) if category_metrics else 0.0

    critical_tp = critical_fp = critical_fn = critical_tn = 0
    for record, inferred in zip(records, categories):
        urgency = assess_urgency(record["text"], float(record.get("rating", 3)), inferred)
        predicted_critical = urgency.severity == "critical"
        actual_critical = bool(record["gold_critical"])
        critical_tp += int(actual_critical and predicted_critical)
        critical_fp += int(not actual_critical and predicted_critical)
        critical_fn += int(actual_critical and not predicted_critical)
        critical_tn += int(not actual_critical and not predicted_critical)
    critical_recall = critical_tp / (critical_tp + critical_fn) if critical_tp + critical_fn else 0.0
    critical_fpr = critical_fp / (critical_fp + critical_tn) if critical_fp + critical_tn else 0.0

    model_name = predictions[0].model_name
    model_revision = predictions[0].model_revision
    provider = predictions[0].provider
    sentiment_mode = get_settings().revio_sentiment_provider
    aspect_version = ASPECT_REVISION if use_semantic else ASPECT_RULE_VERSION
    pipeline_version = (
        f"{MURIL_MODEL}@{MURIL_REVISION}" if sentiment_mode == "transformers" else f"{model_name}@{model_revision}"
    ) + f"|aspects={ASPECT_MODEL if use_semantic else 'multilingual-rules'}@{aspect_version}|urgency=revio-urgency@{URGENCY_RULE_VERSION}"
    return {
        "dataset": str(dataset_path.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
        "dataset_size": len(records),
        "hand_labeled": True,
        "sentiment": {
            "provider": provider,
            "model_name": model_name,
            "model_version": model_revision,
            "configured_mode": sentiment_mode,
            "pipeline_version": pipeline_version,
            "accuracy": round(accuracy, 4),
            "per_class_precision_recall_f1": per_class,
            "macro_f1": round(statistics.mean(item["f1"] for item in per_class.values()), 4),
            "confusion_matrix_rows_actual_columns_predicted": confusion,
            "per_language_group": per_language,
            "latency_ms": {
                "median": round(statistics.median(latencies), 3),
                "p95": round(percentile(latencies, 0.95), 3),
                "measurement": "per-record wall-clock classification call in the current local environment",
            },
        },
        "aspects": {
            "provider": aspect_provider,
            "model_name": ASPECT_MODEL if use_semantic else "multilingual keyword rules v1",
            "model_version": aspect_version,
            "macro_f1": round(category_macro_f1, 4),
            "micro_precision_recall_f1": category_micro,
            "per_category_precision_recall_f1": category_metrics,
            "warning": aspect_warning,
        },
        "urgency": {
            "critical_issue_recall": round(critical_recall, 4),
            "critical_false_positive_rate": round(critical_fpr, 4),
            "critical_true_positive": critical_tp,
            "critical_false_positive": critical_fp,
            "critical_false_negative": critical_fn,
            "critical_true_negative": critical_tn,
        },
        "limitations": [
            "This is a small, manually labeled development set, not a representative sample of Indian customer reviews.",
            "Labels are single-annotator gold labels; mixed and sarcastic language can be ambiguous.",
            "Confidence and rule-strength values are not calibrated probabilities.",
            "Measurements apply only to this local environment and the model/provider recorded above.",
            "The optional semantic approach was only run if explicitly requested; no unavailable model result is imputed.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=REPOSITORY_ROOT / "data/evaluation/indian_review_intelligence.jsonl")
    parser.add_argument("--semantic", action="store_true", help="Run optional sentence-transformer aspect inference.")
    parser.add_argument("--output", type=Path, help="Write the actual report JSON to this path.")
    args = parser.parse_args()
    report = evaluate(args.dataset, use_semantic=args.semantic)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
