# REVIO

Reputation intelligence for teams that care about every customer conversation.

## Completed scope: Milestones 1–5

## Assessment documents

- [AI Opportunity Report](docs/ai-opportunity-report.md)
- [Technical Approach Report](docs/technical-approach-report.md)
- [Deployment readiness and owner setup steps](docs/deployment.md)
- [Detailed milestone and evaluation record](docs/technical-report.md)

## Deployment status

**Public assessment demo status (17 November 2026):** the frontend is deployed at [https://revio-ai-smoky.vercel.app](https://revio-ai-smoky.vercel.app); direct HTTP checks returned 200 for its six product routes. The API URL is [https://expert-space-orbit-5vqwjw76v5p37p95-8000.app.github.dev](https://expert-space-orbit-5vqwjw76v5p37p95-8000.app.github.dev). The latest public `/health` check redirected to GitHub sign-in (302), and the Vercel-origin CORS preflight was rejected by the tunnel (401). The repository had explicitly defaulted port 8000 to `private`, matching the tunnel response; `.devcontainer/devcontainer.json` now defaults it to `public`, as previously authorized. The existing Codespace must pull this change and may need a one-time Ports-panel update. FastAPI health and CORS could not be checked publicly. The deployed Overview previously showed `Failed to fetch`, and its database-backed data is not verified. Latest local source also restricts demo writes to the fixed synthetic workspace and committed fixtures; those changes are not active on the Codespace until it pulls and restarts from `main`. See [deployment instructions and current verification](docs/deployment.md). Use fictional data only; never enter real customer reviews or private policies.

## Evaluator walkthrough

When the API is reachable, use this sequence to see the implemented workflow: **Overview** for database-derived review totals and trends; **Reviews Inbox** to filter Indian demo locations and open a PhonePe/UPI complaint; **Crisis Monitor** to inspect explainable, unconfirmed signals; **Location Analytics** to compare Jaipur, Chandigarh, and Ludhiana; **Knowledge Base** to search synthetic policies and inspect source citations; then **Response Studio** to draft from a review, inspect the six LangGraph steps and citations, edit the draft, and approve it for internal use. Drafting uses the visibly labeled deterministic demo provider; approval does not publish a reply.

At the time of this report the public API tunnel requires GitHub sign-in, so this sequence cannot be completed on the submitted public URLs. Use the [local setup](#local-setup) for a working demonstration while the existing Codespace is restarted and port 8000 is made Public. All listed reviews and policies are synthetic.

REVIO supports CSV review preview and import, persistent tenant-scoped review storage, duplicate detection, a searchable Reviews Inbox, review details and status updates, database-backed Overview metrics, persisted multilingual review analysis, signal-only crisis monitoring, and location analytics. The API seeds 45 clearly labeled DEMO / SYNTHETIC DATA reviews across Jaipur, Rajasthan, India; Chandigarh, India; and Ludhiana, Punjab, India. The fictional examples use Indian customer names and cover restaurants, cafes, hotels, fitness centres, retail, and food delivery. No live review integrations are connected.

Review analysis stores positive, neutral, or negative sentiment; confidence metadata; heuristic language and script; multi-label complaint categories with text evidence; and explainable urgency with a recommended action. The local default uses a deterministic multilingual phrase baseline and identifies itself as fallback/rules output. Optional pinned MuRIL sentiment inference and multilingual semantic aspect similarity are available after installing optional AI requirements. See the model selection and limitations report in docs/model-selection.md.

The Crisis Monitor identifies configured changes and recurrence patterns from persisted analyses. It clearly labels them as unconfirmed signals. Location analytics are calculated from stored reviews and current analysis records. Results are cached by tenant, review text hash, and model pipeline version.

The Knowledge Base accepts extractable-text PDF, UTF-8 TXT, and Markdown policy documents, versions and hashes their normalized contents, chunks them with overlap, and indexes persistent embeddings. Search returns tenant-scoped passages with source, page, version, similarity, and retrieval metadata; it abstains when nothing meets the configured threshold. Six clearly labeled fictional Indian policy examples can be added to the demo workspace from the UI. The Response Studio uses a typed LangGraph StateGraph to load and analyze one review, retrieve tenant-scoped policy evidence, draft a language-matched reply, validate selected factuality risks, and persist a versioned draft. The UI exposes source citations, workflow step status and timing, editing, approval or rejection, and an audit trail. Approval is internal only; REVIO does not publish replies to review platforms. Scanned PDFs are not OCR-supported, and no live review integrations are connected.

## Requirements

- Node.js 20.9 or newer and npm
- Python 3.11 or newer

## Local setup

### 1. Configure and start the API

```powershell
Copy-Item services/api/.env.example services/api/.env
py -3 -m venv services/api/.venv
services/api/.venv/Scripts/python.exe -m pip install --upgrade pip
services/api/.venv/Scripts/python.exe -m pip install -r services/api/requirements.txt
services/api/.venv/Scripts/python.exe -m pip install -r services/api/requirements-rag.txt
services/api/.venv/Scripts/python.exe -m pip install -r services/api/requirements-agent.txt
cd services/api
uvicorn app.main:app --reload
```

SQLite is the default and creates `services/api/revio.db` automatically. To use another local SQLite path, set `DATABASE_URL` in `services/api/.env`, for example `sqlite:///./revio.db`. Alembic applies migrations at API startup. To apply them manually from `services/api`, run `alembic upgrade head`.

The first startup creates the `revio-demo` workspace, its local demo membership, locations, and fictional seed reviews. Startup synchronizes the 45 managed synthetic rows in this demo tenant in place, so repeated startup is idempotent and upgrades the previous demo fixture without changing migrations or overwriting non-demo CSV-imported records. The sample CSV is also available at [`data/demo/reviews.csv`](data/demo/reviews.csv) and through `GET /api/v1/demo/reviews.csv`.

The RAG stack is installed separately with `requirements-rag.txt`. On first indexing, Sentence Transformers downloads the pinned embedding model to the local Hugging Face cache; API startup itself does not download model weights. Set `KNOWLEDGE_VECTOR_BACKEND` in `services/api/.env` to `auto`, `chroma`, or `sqlite`. `auto` uses persistent Chroma on non-Windows hosts. On Windows, REVIO uses its persistent exact-cosine SQLite vector fallback because Chroma's local vector write stalled in the verified Python 3.12 environment. The fallback is intended for local development and small demos; Linux production should use Chroma. The limitation and measurements are recorded in [`docs/knowledge-retrieval-report.md`](docs/knowledge-retrieval-report.md).

After opening the app, go to **Knowledge base**. Upload a PDF with selectable text, TXT, or Markdown file (10 MB maximum), or add the six fictional Indian sample policies. Search in Indian English, Hindi, or Hinglish. The demo data is clearly titled `DEMO / SYNTHETIC DATA`; remove it with the document delete action when no longer needed. Text-only PDFs are supported; scanned PDFs without extractable text are rejected because OCR is not implemented.

Open **Response studio** or use **Draft a response** from a review detail. By default, drafts use a deterministic, clearly labeled safe demo template. To use a hosted OpenAI-compatible chat-completions endpoint, set `RESPONSE_LLM_PROVIDER=openai_compatible`, `RESPONSE_LLM_API_KEY`, `RESPONSE_LLM_BASE_URL`, and `RESPONSE_LLM_MODEL` in the ignored local `services/api/.env`. Review text and retrieved policy passages will then be sent to that configured provider. With no key, generation stays on the demo template. Drafts remain local to the workspace; human approval never sends or publishes them. The guardrail check is heuristic and is not a proof of factuality, so reviewers must verify the source passages and final wording.

- Health: <http://127.0.0.1:8000/health>
- API docs: <http://127.0.0.1:8000/docs>

### 2. Configure and start the web app

In a second terminal:

```powershell
Copy-Item apps/web/.env.example apps/web/.env.local
cd apps/web
npm ci
npm run dev
```

Open <http://localhost:3000>. `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` configures the API URL; it defaults to `http://127.0.0.1:8000`.

## API overview

All workspace endpoints accept `X-Tenant-Slug`; the local demo client uses `revio-demo`. Errors share an `error` envelope with a stable code, message, and field/row details where applicable.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/reviews/imports/preview` | Validate a CSV and preview accepted/rejected rows and issue counts |
| `POST` | `/api/v1/reviews/imports` | Persist accepted reviews and create an import job |
| `GET` | `/api/v1/reviews/imports/{job_id}` | Read import job status and row errors |
| `GET` | `/api/v1/reviews` | Search, filter, sort, and paginate reviews |
| `GET` | `/api/v1/reviews/{review_id}` | Read tenant-scoped review detail and import metadata |
| `PATCH` | `/api/v1/reviews/{review_id}/status` | Update review status (`new`, `needs_attention`, `resolved`) |
| `GET` | `/api/v1/locations` | List workspace locations for filters |
| `GET` | `/api/v1/analytics/summary` | Read total, average rating, attention count, locations, and daily volume |
| `GET` | `/api/v1/demo/reviews.csv` | Download the Indian DEMO / SYNTHETIC DATA sample CSV |
| `POST` | `/api/v1/knowledge/documents` | Validate and index a tenant-scoped PDF, TXT, or Markdown source |
| `GET` | `/api/v1/knowledge/documents` | List tenant-scoped documents and processing state |
| `GET` | `/api/v1/knowledge/documents/{document_id}` | Read source metadata and processing status |
| `DELETE` | `/api/v1/knowledge/documents/{document_id}` | Delete a tenant-scoped document and its vectors |
| `POST` | `/api/v1/knowledge/documents/{document_id}/reindex` | Rebuild stable chunks and embeddings for one document version |
| `POST` | `/api/v1/knowledge/search` | Retrieve relevant passages with citations or abstain |
| `POST` | `/api/v1/knowledge/demo-documents` | Idempotently add fictional Indian policy examples to the demo workspace |
| `POST` | `/api/v1/reviews/{review_id}/responses/generate` | Run the LangGraph workflow and save a versioned tenant-scoped response draft |
| `GET` | `/api/v1/reviews/{review_id}/responses` | List tenant-scoped drafts for a review, newest first |
| `GET` | `/api/v1/responses/{draft_id}` | Read a tenant-scoped response draft, workflow trace, analysis and citations |
| `PATCH` | `/api/v1/responses/{draft_id}` | Save a human edit while the response remains a draft |
| `POST` | `/api/v1/responses/{draft_id}/approve` | Mark a draft approved for internal use (does not publish) |
| `POST` | `/api/v1/responses/{draft_id}/reject` | Reject a draft and retain the decision in its audit history |
| `GET` | `/api/v1/responses/{draft_id}/audit` | Read tenant-scoped generation, edit and decision events |

CSV imports require `review_text` and `rating`. Optional columns include `author_name`, `review_date`, `location`, `source`, `external_review_id`, and `is_synthetic`. UTF-8 CSV files up to 10 MB and 10,000 rows are supported. Ratings must be between 1 and 5 in half-star increments. The importer validates the full file, shows an upload preview, and uses tenant-scoped review fingerprints to prevent repeated rows from being stored twice. The downloadable sample contains 45 fictional Indian reviews, including Indian English, Hinglish, and Hindi text; all rows are marked synthetic.

## AI model configuration and new APIs

The API starts without model downloads. The default sentiment and aspect modes are deterministic multilingual rules. To request local MuRIL sentiment and Sentence Transformers semantic aspect inference, install services/api/requirements-ai.txt and set REVIO_SENTIMENT_PROVIDER=transformers and REVIO_ASPECT_PROVIDER=sentence-transformers in services/api/.env. On first inference, pinned model checkpoints are downloaded and cached. Missing dependencies, download failures, and inference errors use the labeled fallback.

The Milestone 3 endpoints are:

- POST /api/v1/intelligence/analyze — analyze a tenant's reviews in a batch; use the force query option to recompute the configured model version.
- GET /api/v1/intelligence/status — inspect model mode and optional dependency availability.
- GET /api/v1/crisis/alerts — read signal alerts and tenant-scoped supporting review references.
- POST /api/v1/crisis/scan — scan the configured time window for negative rises, recurring complaint themes, and severe cross-location patterns.
- PATCH /api/v1/crisis/alerts/{alert_id}/status — acknowledge or resolve a signal.
- GET /api/v1/analytics/location-intelligence — compare stored ratings, sentiment, complaint categories, urgency, and negative trends by location.

### Response Studio workflow

The LangGraph StateGraph runs six visible steps in order: `load_review`, `analyze_review`, `retrieve_policy_evidence`, `generate_response`, `validate_response`, and `save_draft`. It reuses the saved review-intelligence pipeline and the same multilingual semantic retrieval service as Knowledge Base search. The graph stores per-step state, duration, safe error codes, and warnings with the draft. If no relevant policy passage is found, the response uses a cautious acknowledgement and avoids a policy claim, refund promise, amount, or timeline. High and critical reviews are marked for human escalation; the graph does not claim that an escalation action has already happened.

Response drafts are versioned by tenant and review. Human edits and approval/rejection transitions create audit events. Only drafts or edited drafts can be approved or rejected. The UI makes no external publish call. The local `demo-operator` audit identity is a placeholder because the demo tenant header is not production authentication; production must bind the actor to verified identity and authorization.

## Checks

The separate manually labeled review intelligence corpus is `data/evaluation/indian_review_intelligence.jsonl`. The knowledge retrieval evaluation uses `data/evaluation/knowledge_retrieval.jsonl`, with 30 known relevant questions across Indian English, Hindi, and Hinglish plus 6 no-match questions. To run the actual embedding comparison from `services/api`, use:

```powershell
.venv/Scripts/python.exe scripts/evaluate_knowledge.py --model both
```

The first run downloads the two pinned checkpoints. It evaluates the actual installed store on CPU and writes `data/evaluation/knowledge_retrieval_results.json`. The script measures Recall@1/3/5, MRR, warmed query+retrieval median/p95 latency, model load time, model snapshot bytes, process RSS, and synthetic no-match abstention. It also records tenant isolation. Scores are from a small synthetic development set, not production guarantees. The 17 November 2026 local rerun is recorded in the JSON and [retrieval report](docs/knowledge-retrieval-report.md). The separate review intelligence evaluation can be rerun with `python scripts/evaluate_intelligence.py --output ../../docs/evaluation/milestone-3-evaluation.json` from `services/api`.

Milestone 4 model comparison, architecture, evaluation measurements, Windows Chroma limitation, and guardrail boundaries are documented in [`docs/knowledge-retrieval-report.md`](docs/knowledge-retrieval-report.md).

From the repository root, run the backend tests, then the frontend checks:

```powershell
cd services/api
.venv\Scripts\python.exe -m pytest -q
cd ..\..\apps\web
npm run lint
npm run build
```

## Visual system

- Cream: `#F1EEE8`
- Deep Teal: `#0E4F4A`
- Coral: `#FF6F5E`

The interface keeps the approved editorial serif headings, clean sans-serif controls, existing sidebar and top navigation, and responsive layout.

## Repository layout

```text
apps/web/                 JavaScript-only Next.js frontend
services/api/             FastAPI, SQLAlchemy, Alembic and tests
data/demo/                Clearly labeled fictional reviews and Indian policy documents
data/evaluation/           Separate synthetic evaluation corpora and measured outputs
docs/                     Technical and evaluation reports
```

## Data and security boundaries

- The local `revio-demo` tenant and account are fictional bootstrap records, not a production identity system. Tenant scoping is enforced by the API; production authentication remains future work.
- Knowledge document text and vectors are filtered on the server by tenant ID. The demo `X-Tenant-Slug` header selects a workspace but is not authentication; production must bind tenant selection to a verified identity before exposing real customer or business data.
- When `APP_ENV=demo`, only the fixed synthetic workspace and committed sample CSV/policy files are accepted for ingestion; policy deletion is disabled and reindex is restricted to verified synthetic fixtures. Local development retains the normal import workflow.
- CSV imports are persisted in SQLite. The schema is migration-ready for PostgreSQL, the intended production database.
- The CSV processor runs synchronously in the API process. Queue-backed processing is a future scaling improvement; Redis/Celery are not used here.
- Knowledge indexing uses FastAPI in-process background tasks, with no Redis/Celery dependency. A durable queue and a server-backed Chroma deployment are scaling improvements; interrupted local jobs are retried through Reindex after marking the document failed.
- No review-source integrations are connected. CSV imports are distinct from seeded synthetic records.
- Do not place credentials in committed files. Keep real secrets in ignored local `.env` files.
