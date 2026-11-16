# REVIO Technical Approach Report

**As of:** 16 November 2026. **Delivery status:** Milestones 1–5 are implemented and pushed. Deployment configuration is prepared, but the product is not publicly deployed. No live URLs exist. This report describes the implemented demonstration and the proposed assessment hosting topology; it does not claim production security.

## System architecture

```mermaid
flowchart LR
    B[Browser] -->|Next.js UI| V[Vercel project<br/>root: apps/web]
    V -->|HTTPS JSON + X-Tenant-Slug| API[FastAPI<br/>temporary GitHub Codespace]
    API --> DB[(SQLAlchemy + Alembic<br/>SQLite in Codespace workspace)]
    API --> IDX[(Tenant-filtered exact cosine<br/>SQLite vector index)]
    API --> HF[(Pinned E5 model cache<br/>Codespace home directory)]
    API --> GRAPH[LangGraph response StateGraph]
    GRAPH --> RET[Shared tenant-scoped RAG retrieval]
    GRAPH --> DEMO[Safe deterministic draft default]
    GRAPH -. optional configured endpoint .-> LLM[OpenAI-compatible chat endpoint]
```

The monorepo uses Next.js with JavaScript-only application files under `apps/web`, Python/FastAPI under `services/api`, SQLAlchemy/Alembic for relational records, and Sentence Transformers for embeddings. The API default is SQLite. The prepared time-bounded assessment demo uses SQLite and the persistent exact-cosine vector fallback in a personal Codespace workspace; PostgreSQL remains the intended relational production migration target. See the individual milestone sections in [`technical-report.md`](technical-report.md).

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

## Proposed zero-budget deployment and operations

The prepared backend configuration is .devcontainer/devcontainer.json, services/api/requirements-codespaces.txt, and services/api/scripts/codespaces_bootstrap.py. It requests a 4-core, 16 GB GitHub Codespace, uses one Uvicorn worker, and keeps SQLite plus the exact-cosine vector index in the workspace. FastAPI lifespan applies Alembic and synchronizes the 45 committed synthetic reviews. The bootstrap adds the six committed synthetic policy files and verifies or rebuilds missing vector rows with the existing embedding pipeline. Codespaces stop/start preserves workspace files; deleting or rebuilding the Codespace loses user-uploaded data, while the committed fictional fixture can be reconstructed.

Render Free is not selected. Its published 512 MB memory cap is lower than REVIO's 648.07 MB E5 model RSS measurement, and it provides no persistent disk. A full local API diagnostic with multilingual MiniLM L12 measured 689.89 MB after query embedding. These are local measurements, not Render benchmarks; the current service cannot be shown to fit Render Free safely. No smaller or mock retriever is substituted. The model, scores, latency, and model-file size remain in the committed retrieval evaluation.

The frontend remains a Vercel Hobby project with monorepo root apps/web. NEXT_PUBLIC_API_BASE_URL is compiled into the browser bundle and must be set to the actual public Codespaces API origin before the production build. After Vercel assigns a URL, restart the API with VERCEL_ORIGIN set so CORS_ALLOWED_ORIGINS contains that exact HTTPS origin. Wildcard origins are rejected; CORS does not replace authentication.

The plan uses only included personal GitHub Codespaces quota and Vercel Hobby usage. No public service has been created and no live URLs are known. Codespaces have a 12-hour maximum lifetime and idle shutdown; this is temporary assessment compute, not reliable public hosting. GitHub Free personal accounts list 120 Codespaces core-hours and 15 GB-month storage. At 4 cores, 11 hours would use about 44 core-hours before setup; the owner's remaining allowance is unknown and must be checked before creation. Vercel Hobby is personal and non-commercial; the owner must confirm assessment use qualifies. Do not add a payment method, create a paid trial, or exceed the included allowance. See deployment.md for owner setup steps.

Production scaling should move relational data to managed PostgreSQL, uploaded content to object storage, and vectors to a server-backed vector database; then add authenticated tenant membership, durable queued processing, backups, observability, request limits, and independent evaluation sets before broad use.

## Local verification and evaluation references

Final zero-budget preparation checks passed locally: 52 backend tests, frontend ESLint, and the Next.js production build. An isolated API smoke check returned database health, 45 reviews across three Indian locations, six ready synthetic policies, a real UPI source citation, and a six-node LangGraph Response Studio draft that was approved and audited. A prior headless Chrome check rendered the local Response Studio; no public browser, mobile, cross-origin, or live deployment checks have been performed.

Evaluation artifacts: [`milestone-3-evaluation.json`](evaluation/milestone-3-evaluation.json), [`milestone-3-muril-evaluation.json`](evaluation/milestone-3-muril-evaluation.json), and [`knowledge_retrieval_results.json`](../data/evaluation/knowledge_retrieval_results.json). The exact external Cynbit rubric was not included with the current task, so this report maps to the assessment categories explicitly listed by the owner rather than claiming rubric-by-rubric certification.
