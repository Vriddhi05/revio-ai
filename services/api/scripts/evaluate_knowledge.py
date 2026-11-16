"""Run real multilingual retrieval evaluation on the synthetic Indian policy corpus.

Run from services/api with:
  .venv/Scripts/python.exe scripts/evaluate_knowledge.py
The models and Chroma index are temporary evaluation artifacts and are not committed.
"""

import argparse
import ctypes
import gc
import json
import os
import platform
import subprocess
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

from app.services.knowledge_documents import chunk_pages, extract_document, split_chunks_to_token_limit, token_count  # noqa: E402
from app.services.knowledge_vectors import build_knowledge_store  # noqa: E402

MODELS = [
    {
        "name": "intfloat/multilingual-e5-small",
        "revision": "fd1525a9fd15316a2d503bf26ab031a61d056e98",
        "prefix_query": "query: ",
        "prefix_passage": "passage: ",
        "model_family": "multilingual E5 retrieval",
    },
    {
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        "prefix_query": "",
        "prefix_passage": "",
        "model_family": "multilingual MiniLM semantic similarity",
    },
]


def read_samples():
    samples = [json.loads(line) for line in (REPO_ROOT / "data/evaluation/knowledge_retrieval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    positives = [item for item in samples if item["should_match"]]
    negatives = [item for item in samples if not item["should_match"]]
    if len(positives) != 30 or len(negatives) != 6:
        raise ValueError(f"Expected 30 positive and 6 no-match questions, got {len(positives)} and {len(negatives)}.")
    return samples


def build_corpus(tenant_id: str):
    chunks = []
    documents = []
    sources = sorted(source for source in (REPO_ROOT / "data/demo/knowledge").glob("*.md") if source.name.casefold() != "readme.md")
    for source in sources:
        raw = source.read_bytes()
        extracted = extract_document(source.name, raw)
        document_id = f"eval-{source.stem}"
        doc_chunks = chunk_pages(
            document_id,
            tenant_id,
            extracted.content_sha256,
            1,
            extracted.filename,
            extracted.pages,
            900,
            140,
        )
        for chunk in doc_chunks:
            chunk["risk_flags"] = []
            chunks.append(chunk)
        documents.append({
            "id": document_id,
            "title": extracted.title,
            "source_filename": extracted.filename,
            "content_sha256": extracted.content_sha256,
            "chunks": doc_chunks,
        })
    return chunks, documents


def percentile(values, q):
    return float(np.percentile(np.asarray(values, dtype=np.float64), q)) if values else 0.0


def current_rss_mb():
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        if platform.system() == "Windows":
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            process_handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize / (1024 * 1024)
        else:
            try:
                import resource

                # Linux reports KiB; macOS reports bytes.
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                return peak / (1024 * 1024 if platform.system() == "Darwin" else 1024)
            except ImportError:
                pass
    return None


def evaluate_model(model_spec, samples, documents):
    from sentence_transformers import SentenceTransformer

    rss_before_model_load = current_rss_mb()
    started = time.perf_counter()
    hub_cache = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    model_cache_dir = hub_cache / f"models--{model_spec['name'].replace('/', '--')}" / "snapshots" / model_spec["revision"]
    if (model_cache_dir / "model.safetensors").is_file() and (model_cache_dir / "modules.json").is_file():
        model = SentenceTransformer(str(model_cache_dir), device="cpu")
    else:
        model = SentenceTransformer(model_spec["name"], revision=model_spec["revision"], device="cpu")
    load_seconds = time.perf_counter() - started
    load_rss_mb = current_rss_mb()
    snapshot_size_bytes = sum(path.stat().st_size for path in model_cache_dir.rglob("*") if path.is_file()) if model_cache_dir.exists() else None
    dimensions = int(model.get_embedding_dimension())
    max_sequence_length = int(model.max_seq_length)
    token_limit = min(480, max_sequence_length)
    token_overlap = min(64, max(8, token_limit // 4))
    prepared_documents = []
    for document in documents:
        prepared = dict(document)
        prepared["chunks"] = split_chunks_to_token_limit(
            document["chunks"], model.tokenizer, token_limit, token_overlap, model_spec["prefix_passage"]
        )
        prepared_documents.append(prepared)
    corpus_chunks = [chunk for document in prepared_documents for chunk in document["chunks"]]
    chunk_token_counts = [chunk["token_count"] for chunk in corpus_chunks]
    passage_inputs = [model_spec["prefix_passage"] + chunk["text"] for chunk in corpus_chunks]
    embed_started = time.perf_counter()
    passage_vectors = model.encode(
        passage_inputs,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        batch_size=32,
    )
    corpus_embed_seconds = time.perf_counter() - embed_started

    tenant_id = "synthetic-evaluation-tenant"
    with tempfile.TemporaryDirectory(prefix="revio-rag-eval-") as temp_dir:
        store = build_knowledge_store(path=temp_dir)
        target_document_ids = [document["id"] for document in prepared_documents]
        vector_matrix = np.asarray(passage_vectors, dtype=np.float32)
        vector_offset = 0
        for document in prepared_documents:
            count = len(document["chunks"])
            store.upsert(
                tenant_id,
                document["id"],
                document["chunks"],
                vector_matrix[vector_offset:vector_offset + count].tolist(),
                {
                    "title": document["title"],
                    "source_filename": document["source_filename"],
                    "version": 1,
                    "content_sha256": document["content_sha256"],
                },
            )
            vector_offset += count

        # Warm one query outside the recorded set.
        warm = model.encode([model_spec["prefix_query"] + samples[0]["query"]], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)[0]
        store.search(tenant_id, target_document_ids, np.asarray(warm, dtype=np.float32).tolist(), 5)

        latencies_ms = []
        evaluated = []
        for sample in samples:
            query_token_count = token_count(model.tokenizer, model_spec["prefix_query"] + sample["query"], add_special_tokens=True)
            if query_token_count > max_sequence_length:
                evaluated.append({
                    **sample,
                    "rank": None,
                    "top_score": 0.0,
                    "query_token_count": query_token_count,
                    "query_rejected_too_long": True,
                    "top_hits": [],
                })
                continue
            query_started = time.perf_counter()
            vector = model.encode(
                [model_spec["prefix_query"] + sample["query"]],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
            hits = store.search(tenant_id, target_document_ids, np.asarray(vector, dtype=np.float32).tolist(), 5)
            latencies_ms.append((time.perf_counter() - query_started) * 1000)
            expected_source = sample.get("expected_source_filename")
            expected_phrase = sample.get("expected_passage_contains")
            rank = next((index + 1 for index, hit in enumerate(hits) if hit["metadata"].get("source_filename") == expected_source and expected_phrase.casefold() in hit["text"].casefold()), None) if sample["should_match"] else None
            evaluated.append({
                **sample,
                "rank": rank,
                "top_score": hits[0]["similarity"] if hits else 0.0,
                "query_token_count": query_token_count,
                "query_rejected_too_long": False,
                "top_hits": hits,
            })

        positive_ranks = [item["rank"] for item in evaluated if item["should_match"]]
        no_match_scores = [item["top_score"] for item in evaluated if not item["should_match"] and not item["query_rejected_too_long"]]
        positive_scores = [item["top_score"] for item in evaluated if item["should_match"] and not item["query_rejected_too_long"]]
        threshold_candidates = sorted({0.0, 1.0, *positive_scores, *no_match_scores})
        best_threshold = 0.5
        best_balanced_accuracy = -1.0
        for threshold in threshold_candidates:
            tpr = sum(score >= threshold for score in positive_scores) / max(1, len(positive_scores))
            tnr = sum(score < threshold for score in no_match_scores) / max(1, len(no_match_scores))
            balanced = (tpr + tnr) / 2
            if balanced > best_balanced_accuracy:
                best_threshold = threshold
                best_balanced_accuracy = balanced
        metrics = {}
        thresholded_ranks = []
        thresholded_abstentions = 0
        for item in evaluated:
            accepted = [hit for hit in item["top_hits"] if hit["similarity"] >= best_threshold]
            expected_source = item.get("expected_source_filename")
            expected_phrase = item.get("expected_passage_contains")
            thresholded_rank = next((index + 1 for index, hit in enumerate(accepted) if hit["metadata"].get("source_filename") == expected_source and expected_phrase and expected_phrase.casefold() in hit["text"].casefold()), None) if item["should_match"] else None
            if item["should_match"]:
                thresholded_ranks.append(thresholded_rank)
                if not accepted:
                    thresholded_abstentions += 1
            item["thresholded_rank"] = thresholded_rank
        for k in (1, 3, 5):
            metrics[f"recall_at_{k}"] = sum(rank is not None and rank <= k for rank in positive_ranks) / max(1, len(positive_ranks))
            metrics[f"thresholded_recall_at_{k}"] = sum(rank is not None and rank <= k for rank in thresholded_ranks) / max(1, len(thresholded_ranks))
        metrics["mrr"] = statistics.mean(1 / rank if rank else 0 for rank in positive_ranks)
        metrics["thresholded_mrr"] = statistics.mean(1 / rank if rank else 0 for rank in thresholded_ranks)
        abstained_no_match = sum(item["top_score"] < best_threshold for item in evaluated if not item["should_match"] and not item["query_rejected_too_long"])
        false_positive_no_match = sum(item["top_score"] >= best_threshold for item in evaluated if not item["should_match"] and not item["query_rejected_too_long"])
        tenant_probe = store.search("other-synthetic-tenant", target_document_ids, np.asarray(warm, dtype=np.float32).tolist(), 5)
        metrics.update({
            "positive_questions": len(positive_ranks),
            "processable_positive_questions": sum(item["should_match"] and not item["query_rejected_too_long"] for item in evaluated),
            "positive_hits_at_5": sum(rank is not None and rank <= 5 for rank in positive_ranks),
            "queries_rejected_for_model_length": sum(item["query_rejected_too_long"] for item in evaluated),
            "median_retrieval_latency_ms": statistics.median(latencies_ms) if latencies_ms else None,
            "p95_retrieval_latency_ms": percentile(latencies_ms, 95),
            "no_match_questions": sum(not item["should_match"] for item in evaluated),
            "no_match_query_rejections": sum(not item["should_match"] and item["query_rejected_too_long"] for item in evaluated),
            "no_match_abstentions": abstained_no_match,
            "no_match_false_positives": false_positive_no_match,
            "synthetic_balanced_accuracy_threshold": best_threshold,
            "synthetic_balanced_accuracy": best_balanced_accuracy,
            "positive_query_abstentions_at_threshold": thresholded_abstentions,
            "tenant_isolation_passed": len(tenant_probe) == 0,
        })

    del model
    gc.collect()
    return {
        "model": model_spec["name"],
        "revision": model_spec["revision"],
        "model_family": model_spec["model_family"],
        "dimensions": dimensions,
        "normalization": "L2 normalized by Sentence Transformers encode(normalize_embeddings=True)",
        "query_prefix": model_spec["prefix_query"] or None,
        "passage_prefix": model_spec["prefix_passage"] or None,
        "device": "CPU",
        "max_sequence_length": max_sequence_length,
        "vector_store_backend": store.backend_name if hasattr(store, "backend_name") else "chromadb-persistent",
        "model_load_seconds": load_seconds,
        "model_snapshot_files_mb": round(snapshot_size_bytes / (1024 * 1024), 2) if snapshot_size_bytes is not None else None,
        "process_rss_mb_before_model_load": rss_before_model_load,
        "process_rss_mb_after_model_load": load_rss_mb,
        "process_rss_delta_mb_for_model_load": round(load_rss_mb - rss_before_model_load, 2) if load_rss_mb is not None and rss_before_model_load is not None else None,
        "corpus_passage_count": len(corpus_chunks),
        "maximum_observed_passage_tokens_including_prefix": max(chunk_token_counts, default=0),
        "passages_over_model_limit": sum(count > max_sequence_length for count in chunk_token_counts),
        "corpus_embedding_seconds": corpus_embed_seconds,
        "corpus_embedding_chunks_per_second": len(corpus_chunks) / max(corpus_embed_seconds, 1e-9),
        "similarity_metric": "cosine similarity (exact in local SQLite mode; Chroma stores cosine distance, score = 1 - distance)",
        "chunking": {"strategy": "900-character windows at paragraph/sentence/word boundaries, then tokenizer-aware cap", "size_chars": 900, "overlap_chars": 140, "max_tokens_including_prefix": token_limit, "token_overlap": token_overlap},
        "metrics": metrics,
        "per_query": [
            {"id": item["id"], "language": item["language"], "should_match": item["should_match"], "expected_rank": item["rank"], "thresholded_rank": item["thresholded_rank"], "top_score": round(item["top_score"], 6), "query_token_count": item["query_token_count"], "query_rejected_too_long": item["query_rejected_too_long"]}
            for item in evaluated
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(REPO_ROOT / "data/evaluation/knowledge_retrieval_results.json"))
    parser.add_argument("--model", choices=["e5", "minilm", "both"], default="both")
    args = parser.parse_args()
    samples = read_samples()
    corpus_chunks, documents = build_corpus("synthetic-evaluation-tenant")
    if args.model == "both":
        reports = []
        with tempfile.TemporaryDirectory(prefix="revio-model-comparison-") as temp_dir:
            for key in ("e5", "minilm"):
                model_report = Path(temp_dir) / f"{key}.json"
                subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--model", key, "--report", str(model_report)],
                    cwd=API_ROOT,
                    check=True,
                )
                reports.extend(json.loads(model_report.read_text(encoding="utf-8"))["models"])
    else:
        selected = [MODELS[0] if args.model == "e5" else MODELS[1]]
        reports = [evaluate_model(spec, samples, documents) for spec in selected]
    result = {
        "evaluation_set": "data/evaluation/knowledge_retrieval.jsonl",
        "corpus": "data/demo/knowledge/*.md",
        "sample_count": len(samples),
        "known_relevant_passage_questions": sum(item["should_match"] for item in samples),
        "no_match_questions": sum(not item["should_match"] for item in samples),
        "corpus_chunk_count": len(corpus_chunks),
        "models": reports,
        "limitations": [
            "Small, curated synthetic dataset; results are not production guarantees or a general multilingual benchmark.",
            "Threshold is selected on this same synthetic set and is not independently calibrated.",
            "Latency includes query embedding and the configured local vector lookup after model warm-up; excludes request/network overhead.",
            "Memory is process RSS after model load and includes Python, PyTorch, and shared runtime allocations.",
        ],
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "models": [{"model": item["model"], "metrics": item["metrics"], "rss_mb": item["process_rss_mb_after_model_load"]} for item in reports]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
