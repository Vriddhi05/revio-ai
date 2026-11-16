# REVIO knowledge retrieval report — Milestone 4

## Implemented scope

REVIO accepts PDF files with extractable text, UTF-8 TXT, and Markdown. Upload validation checks the extension, byte limit, empty/invalid content, PDF parsing, and a two-million-character extraction ceiling. Filenames are reduced to safe basenames. Text is normalized before hashing. A content hash makes repeated uploads idempotent within a tenant; changing the content creates the next version for that tenant/source filename. PDF passages retain page numbers. Scanned PDFs without a text layer are rejected; OCR is not implemented.

Indexing runs as a FastAPI in-process background task. SQLite/Alembic stores tenant-scoped document metadata and status. Startup marks interrupted `processing` records failed and reindexable. This is useful for a local single-process assessment but is not a durable queue: a process can stop mid-job, and multiple API workers do not coordinate these tasks. Queue-backed processing is a production scaling improvement.

The complete flow is:

1. Upload is validated, normalized, hashed, and saved as a tenant-scoped document version.
2. A background task splits each page at paragraph/sentence/word boundaries into 900-character windows with 140-character overlap.
3. Tokenizer-aware splitting caps each passage, including the model prefix, at 480 tokens with 64-token overlap. Stable chunk IDs include document/version/source position and content.
4. Passages are embedded and saved with tenant, document, version, hash, title, source filename/reference, page, chunk index, and advisory risk flags.
5. Search embeds the query, restricts candidates to the current tenant's ready documents, ranks by cosine similarity, applies the configured relevance threshold, and returns cited passages or abstains.

Deletion and reindex routes first resolve the document using both its ID and current tenant. Vector deletion and search also carry a tenant constraint. Chroma collection names are derived from tenant IDs and results are additionally filtered by tenant/document metadata. The local SQLite vector fallback always constrains SQL queries by tenant before ranking.

## Embedding model selection

The selected model is `intfloat/multilingual-e5-small`, pinned to Hugging Face revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`. It emits 384-dimensional vectors, accepts up to 512 tokens, and is used with the model's `query: ` and `passage: ` prefixes. Sentence Transformers normalizes both vectors and passages to unit length. Ranking uses cosine similarity (Chroma cosine distance converted as `1 - distance`; exact dot/cosine calculation in the local SQLite fallback). The model card documents multilingual retrieval usage and prefix formatting: [multilingual-e5-small model card](https://huggingface.co/intfloat/multilingual-e5-small).

The comparison candidate was `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, pinned to `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, also 384 dimensions. Its observed maximum sequence length is 128, which required more passages for this corpus. MiniLM was faster and used less measured process memory in this run, but E5 retrieved substantially more expected passages at ranks 1, 3, and 5. E5 is therefore selected for the product's multilingual retrieval use case; this is a result on the small synthetic set below, not a general ranking guarantee.

## Retrieval evaluation

The reproducible, fictional evaluation set is `data/evaluation/knowledge_retrieval.jsonl`: 30 questions with known relevant source passages and six questions with no relevant source. It covers Indian English, Hindi, and Hinglish. The corpus contains six synthetic Indian business-policy documents and was chunked independently for each model. Run `services/api/.venv/Scripts/python.exe services/api/scripts/evaluate_knowledge.py --model both` from the repository root (or `scripts/evaluate_knowledge.py --model both` from `services/api`). It writes the measured output to `data/evaluation/knowledge_retrieval_results.json`.

The latest recorded run used CPU, the persistent exact-cosine SQLite backend on Windows, 13 E5 passages and 24 MiniLM passages. Retrieval latency includes query embedding plus a warmed local vector lookup; it excludes API and network overhead.

| Measurement | multilingual-e5-small | multilingual MiniLM-L12-v2 |
| --- | ---: | ---: |
| Recall@1 / @3 / @5 | 53.33% / 80.00% / 100.00% | 40.00% / 66.67% / 73.33% |
| Mean Reciprocal Rank | 0.7061 | 0.5278 |
| Thresholded Recall@5 | 93.33% | 66.67% |
| Median / p95 warmed query + retrieval | 25.19 / 32.54 ms | 22.10 / 29.14 ms |
| Model snapshot files on disk | 470.44 MB | 457.51 MB |
| Process RSS after model load | 648.07 MB | 451.30 MB |
| Model load time in this run | 1.02 s | 0.87 s |
| Observed max sequence / passage tokens | 512 / 214 | 128 / 128 |
| No-match questions abstained / false positives | 6 / 0 | 6 / 0 |
| Tenant probe returned another tenant's vectors | No | No |

At the E5 threshold selected by balanced accuracy on this same synthetic evaluation set (`0.822045`), all 30 positive questions had at least one accepted result, six of six no-match questions abstained, and thresholded Recall@5 was 93.33%. The MiniLM threshold was `0.415487`, with thresholded Recall@5 of 66.67%. These thresholds are not independently calibrated. Evaluation data informed the defaults and must be replaced or recalibrated on representative, independently labeled business queries before production use.

The exact metrics, pinned revisions, per-question ranks/scores, model sizes, RSS, threshold behavior, and limitations are recorded in `data/evaluation/knowledge_retrieval_results.json`. Results vary with hardware, operating system, package/model revisions, vector backend, and corpus. The dataset is small and curated; it does not establish a broad Hindi or Hinglish benchmark.

The evaluator used local CPU embeddings and made no hosted LLM or embedding API calls, so metered inference charges for this run were **$0.00**. Local CPU time, electricity, storage, and model-download bandwidth are not priced in this measurement.

## Vector storage and runtime constraints

The preferred vector engine is persistent ChromaDB (`chromadb==1.5.9`) with cosine distance, tenant-derived persistent collections, tenant/document metadata filters, and server-side ready-document filtering. `KNOWLEDGE_VECTOR_BACKEND=chroma` explicitly selects it; `auto` selects Chroma on non-Windows hosts. A server-backed Chroma deployment is the intended production option as deployment topology grows. Chroma's own `PersistentClient` documentation describes embedded persistent local use as suitable for development/testing, while server-backed clients are available for deployed services: [Chroma Python client reference](https://docs.trychroma.com/reference/python).

In this verified Windows/Python 3.12 environment, local Chroma vector writes stalled during runtime testing, including the available Python segment fallback. The `auto` setting therefore selects a persistent SQLite exact-cosine vector store on Windows; it is not intended for a large production corpus. This is an environment compatibility fallback, not a replacement decision for production Chroma. Chroma's issue tracker contains a Windows Rust-binding hang report consistent with the observed constraint: [Chroma issue #5937](https://github.com/chroma-core/chroma/issues/5937). Chroma was not claimed as runtime-verified in this environment.

## Guardrails and limitations

- Tenant scoping is enforced in API document queries, ready-document selection, indexing metadata, vector collection/filter selection, search, reindex, and deletion. The evaluation's cross-tenant probe returned no vectors. This verifies the tested store/API paths, not a formal isolation audit.
- The local `X-Tenant-Slug` demo selector is not authentication. Production must derive a tenant from a verified identity and enforce membership authorization server-side.
- Uploaded document text is untrusted. A heuristic flags a small set of instruction-like phrases for display/metadata, but this is not prompt-injection protection. This milestone does not pass retrieved text to an LLM. Any future generation workflow must treat cited passages as untrusted evidence, delimit and instruct against following source instructions, validate outputs, and require human review.
- Search abstains when no ready document exists or no candidate reaches the configured similarity threshold. Similarity is not factual confidence, and a high score does not prove a policy is accurate, current, legal, or applicable.
- No OCR, live integrations, LLM response generation, LangGraph response workflow, or human approval flow was added in this milestone.
- Local model files occupy about 470 MB on disk for E5; the observed model-load process RSS was about 648 MB on this machine. These figures exclude a production server's other services and vary by runtime.
- No hosted embedding or generation provider is called by this milestone. Runtime cost is local compute and storage, not a measured zero-cost production service.

## Reproduction

Install base and RAG requirements, run migrations/API, and open Knowledge base as documented in `README.md`. To reproduce the model comparison with the pinned local weights and synthetic corpus, run:

```powershell
cd services/api
.venv/Scripts/python.exe scripts/evaluate_knowledge.py --model both
```

The evaluator downloads pinned public model weights if they are not already cached. The weights and temporary vector databases are not committed. Its JSON results are synthetic development measurements, not a claim that the application is secure or production-ready.
