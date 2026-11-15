# REVIO

Reputation intelligence for teams that care about every customer conversation.

## Current milestone: Review ingestion and inbox

REVIO now supports CSV review preview and import, persistent tenant-scoped review storage, duplicate detection, a searchable and filterable Reviews Inbox, review details and status updates, and database-backed Overview metrics. The API seeds 45 clearly labeled DEMO / SYNTHETIC DATA reviews across Jaipur, Rajasthan, India; Chandigarh, India; and Ludhiana, Punjab, India. The fictional examples use Indian customer names and cover restaurants, cafes, hotels, fitness centres, retail, and food delivery. No live review integrations are connected.

Sentiment classification, RAG, response generation, and crisis monitoring are not implemented in this milestone. The sentiment filter is present but returns no matches until reviews are classified. Urgency is currently a simple rating-based review status/priority rule, not an AI assessment.

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
cd services/api
uvicorn app.main:app --reload
```

SQLite is the default and creates `services/api/revio.db` automatically. To use another local SQLite path, set `DATABASE_URL` in `services/api/.env`, for example `sqlite:///./revio.db`. Alembic applies migrations at API startup. To apply them manually from `services/api`, run `alembic upgrade head`.

The first startup creates the `revio-demo` workspace, its local demo membership, locations, and fictional seed reviews. Startup synchronizes the 45 managed synthetic rows in this demo tenant in place, so repeated startup is idempotent and upgrades the previous demo fixture without changing migrations or overwriting non-demo CSV-imported records. The sample CSV is also available at [`data/demo/reviews.csv`](data/demo/reviews.csv) and through `GET /api/v1/demo/reviews.csv`.

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

CSV imports require `review_text` and `rating`. Optional columns include `author_name`, `review_date`, `location`, `source`, `external_review_id`, and `is_synthetic`. UTF-8 CSV files up to 10 MB and 10,000 rows are supported. Ratings must be between 1 and 5 in half-star increments. The importer validates the full file, shows an upload preview, and uses tenant-scoped review fingerprints to prevent repeated rows from being stored twice. The downloadable sample contains 45 fictional Indian reviews, including Indian English, Hinglish, and Hindi text; all rows are marked synthetic.

## Checks

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
data/demo/                Clearly labeled fictional review fixtures
docs/                     Technical and evaluation reports
```

## Data and security boundaries

- The local `revio-demo` tenant and account are fictional bootstrap records, not a production identity system. Tenant scoping is enforced by the API; production authentication remains future work.
- CSV imports are persisted in SQLite. The schema is migration-ready for PostgreSQL, the intended production database.
- The CSV processor runs synchronously in the API process. Queue-backed processing is a future scaling improvement; Redis/Celery are not used here.
- No review-source integrations are connected. CSV imports are distinct from seeded synthetic records.
- Do not place credentials in committed files. Keep real secrets in ignored local `.env` files.
