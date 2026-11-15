# REVIO

Reputation intelligence for teams that care about every customer conversation.

## Milestone 1 status

This milestone establishes the local development foundation: a JavaScript-only Next.js application with the REVIO visual system and Overview shell, a FastAPI service, SQLite persistence through SQLAlchemy, Alembic migrations, and a seeded fictional demo workspace. The dashboard intentionally contains no fabricated activity metrics. Review ingestion, analytics, RAG and response generation are planned for later milestones and are not implemented yet.

## Requirements

- Node.js 20.9 or newer and npm
- Python 3.11 or newer

## Local setup

### 1. Configure the API

```powershell
Copy-Item services/api/.env.example services/api/.env
py -3 -m venv services/api/.venv
services/api/.venv/Scripts/python.exe -m pip install --upgrade pip
services/api/.venv/Scripts/python.exe -m pip install -r services/api/requirements.txt
```

SQLite is the default and creates `services/api/revio.db` automatically. To use a different local path, set `DATABASE_URL` in `services/api/.env`, for example:

```dotenv
DATABASE_URL=sqlite:///./revio.db
```

The API creates the schema and the fictional `revio-demo` workspace at startup. For explicit schema operations, run from `services/api`:

```powershell
alembic upgrade head
```

Start the API from its service directory so relative SQLite overrides resolve predictably:

```powershell
cd services/api
uvicorn app.main:app --reload
```

API health: <http://127.0.0.1:8000/health>

Interactive API docs: <http://127.0.0.1:8000/docs>

### 2. Configure the web app

```powershell
Copy-Item apps/web/.env.example apps/web/.env.local
cd apps/web
npm install
npm run dev
```

Open <http://localhost:3000>. The API URL is configured with `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` and defaults to `http://127.0.0.1:8000`.

### 3. Run checks

From the repository root, run backend tests from the service directory, then build the frontend:

```powershell
cd services/api
.venv\Scripts\python.exe -m pytest tests
cd ..\..\apps\web
npm run build
```

## Design system

- Cream: `#F1EEE8`
- Deep Teal: `#0E4F4A`
- Coral: `#FF6F5E`

The interface pairs editorial serif display headings with a clean sans-serif UI, restrained color, generous spacing, and clear empty/loading/error states.

## Repository layout

```text
apps/web/                 Next.js JavaScript frontend
services/api/             FastAPI, SQLAlchemy, Alembic and tests
data/demo/                Reserved for clearly labeled fictional fixtures
docs/                     Technical and evaluation reports
```

## Current limits

- The demo workspace and membership are fictional local bootstrap records, not customer data or a production identity system.
- No review-source integration is connected. The shell does not show fake live data.
- PostgreSQL is the intended production database; SQLite is used for local assessment setup.
- Milestone 1 does not yet implement review import, analytics, ChromaDB, embeddings, or AI workflows.

Never put credentials in committed files. Keep actual secrets in local ignored `.env` files.
