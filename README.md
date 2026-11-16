# REVIO

Reputation intelligence for teams that care about every customer conversation.

## Current milestone: RAG knowledge engine

REVIO supports CSV review preview and import, persistent tenant-scoped review storage, duplicate detection, a searchable Reviews Inbox, review details and status updates, database-backed Overview metrics, persisted multilingual review analysis, signal-only crisis monitoring, and location analytics. The API seeds 45 clearly labeled DEMO / SYNTHETIC DATA reviews across Jaipur, Rajasthan, India; Chandigarh, India; and Ludhiana, Punjab, India. The fictional examples use Indian customer names and cover restaurants, cafes, hotels, fitness centres, retail, and food delivery. No live review integrations are connected.

Review analysis stores positive, neutral, or negative sentiment; confidence metadata; heuristic language and script; multi-label complaint categories with text evidence; and explainable urgency with a recommended action. The local default uses a deterministic multilingual phrase baseline and identifies itself as fallback/rules output. Optional pinned MuRIL sentiment inference and multilingual semantic aspect similarity are available after installing optional AI requirements. See the model selection and limitations report in docs/model-selection.md.

The Crisis Monitor identifies configured changes and recurrence patterns from persisted analyses. It clearly labels them as unconfirmed signals. Location analytics are calculated from stored reviews and current analysis records. Results are cached by tenant, review text hash, and model pipeline version.

The Knowledge Base accepts extractable-text PDF, UTF-8 TXT, and Markdown policy documents, versions and hashes their normalized contents, chunks them with overlap, and indexes persistent embeddings. Search returns tenant-scoped passages with source, page, version, similarity, and retrieval metadata; it abstains when nothing meets the configured threshold. Six clearly labeled fictional Indian policy examples can be added to the demo workspace from the UI. This milestone does not generate customer replies, invoke LangGraph, or implement human response approval. Scanned PDFs are not OCR-supported, and no live review integrations are connected.

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
cd services/api
uvicorn app.main:app --reload
```

SQLite is the default and creates `services/api/revio.db` automatically. To use another local SQLite path, set `DATABASE_URL` in `services/api/.env`, for example `sqlite:///./revio.db`. Alembic applies migrations at API startup. To apply them manually from `services/api`, run `alembic upgrade head`.

The first startup creates the `revio-demo` workspace, its local demo membership, locations, and fictional seed reviews. Startup synchronizes the 45 managed synthetic rows in this demo tenant in place, so repeated startup is idempotent and upgrades the previous demo fixture without changing migrations or overwriting non-demo CSV-imported records. The sample CSV is also available at [`data/demo/reviews.csv`](data/demo/reviews.csv) and through `GET /api/v1/demo/reviews.csv`.

The RAG stack is installed separately with `requirements-rag.txt`. On first indexing, Sentence Transformers downloads the pinned embedding model to the local Hugging Face cache; API startup itself does not download model weights. Set `KNOWLEDGE_VECTOR_BACKEND` in `services/api/.env` to `auto`, `chroma`, or `sqlite`. `auto` uses persistent Chroma on non-Windows hosts. On Windows, REVIO uses its persistent exact-cosine SQLite vector fallback because Chroma's local vector write stalled in the verified Python 3.12 environment. The fallback is intended for local development and small demos; Linux production should use Chroma. The limitation and measurements are recorded in [`docs/knowledge-retrieval-report.md`](docs/knowledge-retrieval-report.md).

After opening the app, go to **Knowledge base**. Upload a PDF with selectable text, TXT, or Markdown file (10 MB maximum), or add the six fictional Indian sample policies. Search in Indian English, Hindi, or Hinglish. The demo data is clearly titled `DEMO / SYNTHETIC DATA`; remove it with the document delete action when no longer needed. Text-only PDFs are supported; scanned PDFs without extractable text are rejected because OCR is not implemented.

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

## Checks

The separate manually labeled review intelligence corpus is `data/evaluation/indian_review_intelligence.jsonl`. The knowledge retrieval evaluation uses `data/evaluation/knowledge_retrieval.jsonl`, with 30 known relevant questions across Indian English, Hindi, and Hinglish plus 6 no-match questions. To run the actual embedding comparison from `services/api`, use:

```powershell
.venv/Scripts/python.exe scripts/evaluate_knowledge.py --model both
```

The first run downloads the two pinned checkpoints. It evaluates the actual installed store on CPU and writes `data/evaluation/knowledge_retrieval_results.json`. The script measures Recall@1/3/5, MRR, warmed query+retrieval median/p95 latency, model load time, model snapshot bytes, process RSS, and synthetic no-match abstention. It also records tenant isolation. Scores are from a small synthetic development set, not production guarantees. See the report for actual results and limitations. The review intelligence evaluation can still be run from its existing script.

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
- CSV imports are persisted in SQLite. The schema is migration-ready for PostgreSQL, the intended production database.
- The CSV processor runs synchronously in the API process. Queue-backed processing is a future scaling improvement; Redis/Celery are not used here.
- Knowledge indexing uses FastAPI in-process background tasks, with no Redis/Celery dependency. A durable queue and a server-backed Chroma deployment are scaling improvements; interrupted local jobs are retried through Reindex after marking the document failed.
- No review-source integrations are connected. CSV imports are distinct from seeded synthetic records.
- Do not place credentials in committed files. Keep real secrets in ignored local `.env` files.
