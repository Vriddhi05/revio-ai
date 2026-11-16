# REVIO Technical Approach Report

**As of:** 16 November 2026. **Delivery status:** Milestones 1–5 are implemented and pushed. Deployment configuration is prepared, but the product is not publicly deployed. No live URLs exist. This report describes the implemented demonstration and the proposed assessment hosting topology; it does not claim production security.

## System architecture

```mermaid
flowchart LR
    B[Browser] -->|Next.js UI| V[Vercel project<br/>root: apps/web]
    V -->|HTTPS JSON + X-Tenant-Slug| API[FastAPI<br/>single Render web process]
    API --> DB[(SQLAlchemy + Alembic<br/>SQLite on persistent disk)]
    API --> IDX[(Tenant-filtered exact cosine<br/>SQLite vector index)]
    API --> HF[(Pinned E5 model cache<br/>persistent disk)]
    API --> GRAPH[LangGraph response StateGraph]
    GRAPH --> RET[Shared tenant-scoped RAG retrieval]
    GRAPH --> DEMO[Safe deterministic draft default]
    GRAPH -. optional configured endpoint .-> LLM[OpenAI-compatible chat endpoint]
```

The monorepo uses Next.js with JavaScript-only application files under `apps/web`, Python/FastAPI under `services/api`, SQLAlchemy/Alembic for relational records, and Sentence Transformers for embeddings. The API default is SQLite. The prepared public demo retains SQLite rather than forcing account setup for managed PostgreSQL; its database and vector index share a persistent disk. PostgreSQL remains the intended relational production migration target. See the individual milestone sections in [`technical-report.md`](technical-report.md).

The browser client sends `X-Tenant-Slug: revio-demo`. This selects the fictional workspace; it is not authentication, authorization, or an acceptable production tenancy boundary. The prepared instance is for a clearly labeled synthetic demonstration only.

## Data and APIs

The idempotent API lifespan applies Alembic migrations and seeds/synchronizes exactly 45 committed synthetic reviews across Jaipur, Chandigarh, and Ludhiana. It preserves unrelated imported rows. The domain contains tenants, memberships, locations, reviews, imports, analyses, crisis alerts, knowledge documents, response drafts, and response audit events. Uploaded knowledge metadata and vector rows are tenant-scoped. No review-platform import integration is connected.

The API exposes health; review CSV preview/import/list/detail/status; locations and summary analytics; analysis and crisis scans; knowledge document upload/list/detail/reindex/delete/search; and response generate/list/detail/edit/approve/reject/audit endpoints. `/health` executes `SELECT 1` against the configured relational database. It deliberately does not load the embedding model, so it is a database/readiness check, not a full AI readiness check.

## Review intelligence

The default is a deterministic multilingual rules baseline for sentiment and complaint aspects, plus explainable urgency. Optional MuRIL sentiment and MiniLM semantic aspect inference can be explicitly enabled. Current M3 evaluation results on a 36-row fictional single-annotator set:

| Pipeline | Accuracy / micro metric | Macro F1 | Additional evidence |
| --- | ---: | ---: | --- |
| Rule sentiment fallback | 63.89% accuracy | 65.35% | Negative recall 46.67%; mixed-script accuracy 37.50% |
| Optional MuRIL sentiment | 66.67% accuracy | 59.69% | Neutral recall 16.67%; median/p95 42.698/163.579 ms per record in local CPU run |
| Multilingual aspect rules | 87.88% micro F1 | 88.17% | Cleanliness recall 28.57% |

The rule pipeline measured 0.018 ms median / 0.052 ms p95 per record in its local run. This small evaluation does not establish production quality. The rules remain the default because MuRIL's higher accuracy accompanied lower macro F1 and poor neutral recall. Model details and per-class results are documented in [`model-selection.md`](model-selection.md) and [`evaluation/`](evaluation/).

## Retrieval and response workflow

Knowledge ingestion accepts text-extractable PDF, UTF-8 TXT, and Markdown; stores version/hash/source metadata; creates stable overlapped chunks; and indexes normalized 384-dimensional E5 vectors. Search filters on tenant and ready document IDs, ranks by cosine similarity, applies the configured threshold, and returns cited passages or abstains. Scanned PDF OCR is not implemented.

`intfloat/multilingual-e5-small` is pinned at `fd1525a9fd15316a2d503bf26ab031a61d056e98`. Query/passage prefixes are applied and embeddings normalized. The RAG evaluation used 30 relevant and 6 no-match fictional English/Hindi/Hinglish questions. Measured Recall@1/3/5 was 53.33%/80.00%/100.00%; MRR was 0.7061; thresholded Recall@5 was 93.33%; all six no-match examples abstained. Local warmed CPU query plus retrieval measured 25.19 ms median / 32.54 ms p95. Model RSS after load was 648.07 MB; snapshot files were 470.44 MB. These local measurements are not cloud latency or memory guarantees. See [`knowledge-retrieval-report.md`](knowledge-retrieval-report.md).

Response drafting is a six-node LangGraph StateGraph:

1. `load_review` resolves the review inside the current tenant.
2. `analyze_review` runs/reuses persisted review intelligence for the selected review.
3. `retrieve_policy_evidence` calls the shared tenant-scoped RAG path and retains source citations; flagged chunks are excluded from generation with flags treated as advisory.
4. `generate_response` uses either the safe deterministic template or a configured OpenAI-compatible chat-completions provider.
5. `validate_response` checks selected unsupported amount, timeline, and promise patterns and substitutes a cautious fallback when a pattern is found.
6. `save_draft` persists a versioned draft, analysis snapshot, citations, provider label, validation record, workflow trace, and audit event.

Humans can edit, approve for internal use, or reject. No publish endpoint exists. The demo provider is the default; no live hosted LLM call or response-quality benchmark has been made. Hosted mode sends review text and retrieved policy passages to the configured provider and requires a separate privacy and cost decision.

## Guardrails and privacy boundary

- Review and policy data is treated as untrusted input. Retrieved snippets are cited and labeled untrusted. Heuristic phrase flags do not constitute complete prompt-injection defense.
- Output validation covers selected high-risk claim types only; it is not semantic factuality proof.
- No evidence causes a cautious, non-committal draft; similarity scores are not factual confidence.
- High/critical urgency signals request a human review but do not notify a team.
- Tenant filters are tested for the demo selector. Since the selector is a caller-controlled header, there is no authenticated tenant membership boundary.
- The public assessment service must contain synthetic information only. It is not a secure customer-data service; unauthenticated writes and missing rate limits remain risks.
- No live integrations, OCR, external publishing, authentication, rate limiting, or durable queue are part of the implementation.

## Proposed deployment and operations

The prepared configuration is `render.yaml` plus the Render build/start scripts. Render Python is pinned to `3.12.16` to keep the verified 3.12 dependency series and avoid the provider's changing default. The local test interpreter is 3.12.6; the newer cloud patch has not yet been deployed or runtime-verified. Build installs base, RAG, and agent dependencies. Start runs one Uvicorn worker on Render's `PORT`; FastAPI lifespan applies Alembic and idempotent synthetic seed logic. The health check uses `/health`.

The Render service explicitly uses `KNOWLEDGE_VECTOR_BACKEND=sqlite`, with database at `/var/data/revio.db`, vectors below `/var/data/knowledge-index`, and model cache under `/var/data/huggingface`. These paths require the attached `/var/data` persistent disk. The E5 model remains lazy; indexing may cause a one-time model download and memory warm-up. The deployment is single instance because the data disk is service-local. Render auto-deploy is off.

The web project is configured in the Vercel dashboard with monorepo root `apps/web`. `NEXT_PUBLIC_API_BASE_URL` is a build-time browser setting and must be set to the actual API HTTPS origin before the Vercel production build. `CORS_ALLOWED_ORIGINS` is a comma-separated explicit-origin allowlist set to the actual Vercel origin after it exists. Wildcard origins are rejected by application settings. CORS does not replace authentication.

As of 16 November 2026, the current Render listing is $85/month for the `2c-4g` web plan; a 2 GB disk at $0.25/GB/month adds $0.50/month. The proposed backend total is therefore **$85.50/month**, before taxes and other usage. Vercel plan and any future hosted LLM charges are excluded. This is a published-price estimate, not an invoice. No hosting account action or paid service has been created. See [`deployment.md`](deployment.md) for owner setup steps and verified URL capture.

Render's disk-backed single-instance arrangement cannot be horizontally scaled, shared with another instance, or redeployed with zero downtime. Production scaling should migrate the relational database to managed PostgreSQL, file uploads to durable object storage, and vectors to a server-backed vector database; then add authenticated tenant membership, durable queue-backed indexing, backups, observability, request limits, and independent evaluation sets before broad use.

## Local verification and evaluation references

Final local verification after deployment preparation: 52 backend tests passed, frontend ESLint passed, and the Next.js production build passed. Headless Chrome rendered the local production Response Studio against synthetic data. These are local checks, not public deployment validation. Public page, mobile browser, cross-origin, and end-to-end checks remain pending owner provisioning.

Evaluation artifacts: [`milestone-3-evaluation.json`](evaluation/milestone-3-evaluation.json), [`milestone-3-muril-evaluation.json`](evaluation/milestone-3-muril-evaluation.json), and [`knowledge_retrieval_results.json`](../data/evaluation/knowledge_retrieval_results.json). The exact external Cynbit rubric was not included with the current task, so this report maps to the assessment categories explicitly listed by the owner rather than claiming rubric-by-rubric certification.
