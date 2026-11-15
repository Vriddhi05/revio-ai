# REVIO technical report — Milestone 2

## Implemented

- Preserved the approved JavaScript-only Next.js shell, editorial serif headings, clean sans-serif controls, responsive layout, and REVIO brand palette.
- Connected Overview cards, location list, attention list, and 30-day review trend to SQL-backed API aggregates.
- Added CSV upload, full-file preview validation, accepted/rejected counts, issue summaries, repeated-review detection, and persistent import job status.
- Added SQLAlchemy review, tenant location, and import job models with Alembic migration `0002_review_ingestion`.
- Added tenant-scoped, paginated review search/filter/sort and detail/status APIs. The client inbox supports location, rating, sentiment, date, status, and sort filters plus review detail metadata.
- Added 45 fictional Juniper & Co. sample reviews across three locations in `data/demo/reviews.csv`. Rows are marked synthetic and shown as fictional demo records in the product. The CSV is downloadable from the import dialog and API.
- Updated README local setup, API, data boundary, and test instructions.

## Current behavior and limits

- SQLite is used for local development; Alembic and SQLAlchemy retain the intended PostgreSQL migration path.
- Import jobs run synchronously in the API process. Queue-based scaling is deferred; Redis and Celery are not present.
- Tenant scope is selected with `X-Tenant-Slug`. The local demo workspace is safe for demonstration, but production authentication and authorization remain future work.
- Review urgency is assigned by rating (`1–2` needs attention, `3` medium priority); it is not an AI urgency assessment.
- Sentiment fields and filters are wired, but classification is not implemented in this milestone.
- No RAG, ChromaDB, Sentence Transformers, LangGraph, response generation, crisis monitoring, or live review-source integrations are implemented.

## Verification

- Backend test suite: 18 passed. The current environment reports one Starlette deprecation warning related to its TestClient/httpx integration.
- Frontend ESLint: passed.
- Next.js production build: passed.
- Live FastAPI checks: `/health`, CSV preview/import, duplicate re-import, import status, review search/list/detail, analytics, and location listing passed. The temporary verification tenant and its records were removed afterward.
- Production frontend returned HTTP 200 for Overview and Reviews Inbox routes. Port 3000 was already occupied, so the production server was run on port 3100 for this check.
- Interactive browser/screenshot review was not completed because computer-use approval timed out; production routes and API workflows were verified over HTTP instead.
- Security review in this milestone focused on avoiding committed secrets and untrusted CSV persistence issues; it is not a general security certification.
