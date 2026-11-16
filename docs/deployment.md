# REVIO deployment readiness

## Status

The deployment configuration is prepared but **no service has been created or deployed**. There are no live REVIO URLs to report. No paid resource has been provisioned. The deployment must remain labeled as a demonstration using only the committed fictional Indian reviews and fictional policies.

## Recommended hosting topology

| Component | Hosting | Configuration |
| --- | --- | --- |
| Next.js frontend | Vercel | Import the repository as a separate project with root directory `apps/web`; set `NEXT_PUBLIC_API_BASE_URL` to the real API origin before building. |
| FastAPI, SQLite database, vector index, model cache | Render | One Singapore web service, plan `2c-4g` (2 CPU, 4 GB RAM), and a 2 GB persistent disk mounted at `/var/data`. The checked-in `render.yaml` disables automatic deploys. |

The selected E5 model measured 648.07 MB process RSS after loading in the local CPU evaluation. The 512 MB Render tier cannot hold that measured process footprint. The 4 GB plan provides room for the API, model runtime, and request work; this is a sizing recommendation, not a cloud benchmark. Render publishes `2c-4g` at $85/month and persistent disks at $0.25/GB/month; this configuration's API compute and 2 GB disk therefore have an indicative listed cost of **$85.50/month**, before tax, bandwidth/other metered usage, and any Vercel plan or hosted-model charges. Confirm the current estimate in the account before provisioning. No LLM provider key is configured and hosted inference is disabled.

Render Singapore is the nearest listed Render region for India. Vercel serves the frontend through its global CDN. The one-instance Render design deliberately uses the already verified exact-cosine SQLite vector fallback rather than depending on a Chroma write path that stalled in the verified Windows environment. SQLite relational data, vector data, and the lazy Hugging Face cache all live under the same attached disk. The 45 managed synthetic review rows are created or synchronized by idempotent startup code after Alembic upgrades.

The E5 model is loaded lazily. The first knowledge-document indexing/search operation on a new service can download about 470 MB of model files and incur cold-load latency. The test environment's 648.07 MB RSS and 25.19 ms median / 32.54 ms p95 warmed query-plus-retrieval measurements are local CPU measurements, not predicted Render latency.

The persistent disk is attached to one service instance. Render documents that attached disks cannot be shared across service instances and prevent horizontal scaling of the service; deployments have brief downtime. This design is suitable for the assessment demo and modest single-process use, not high availability or a multi-tenant production SaaS. A later production architecture should move relational records to managed PostgreSQL, documents to object storage, and vectors to a server-backed vector service, then add durable background processing, authenticated membership enforcement, rate limits, backup/recovery procedures, and monitoring.

## Owner actions required before public deployment

No credentials should be sent in chat. Sign in directly to each provider and approve service creation yourself.

1. **Review the paid Render estimate first.** Sign in at the Render Dashboard, connect the GitHub repository `Vriddhi05/revio-ai`, and choose **New Blueprint** for the repository's `render.yaml` on `main`. Inspect the proposed Singapore region, `2c-4g` plan, and 2 GB disk. Create the service only after accepting the displayed price; this is a paid service. `autoDeployTrigger: off` keeps future commits from deploying automatically.
2. The Blueprint initially restricts CORS to localhost. After creating the API service, copy the actual Render service origin from its dashboard and verify `https://<actual-render-service-origin>/health` returns `{"status":"ok","database":"ok"}`. The angle-bracket text is an instruction, not a deployed URL.
3. Sign in to Vercel, import the same GitHub repository as a new project, and set **Root Directory** to `apps/web`. In project build settings, enable **Include source files outside the Root Directory** because `apps/web/next.config.mjs` sets its tracing root to the monorepo root. Keep the detected Next.js framework, set **Install Command** to `npm ci`, and **Build Command** to `npm run build`. Set the production environment variable `NEXT_PUBLIC_API_BASE_URL` to the actual Render API origin only (no `/api/v1` suffix), then deploy the frontend.
4. Copy the actual Vercel production origin from Vercel and replace Render's `CORS_ALLOWED_ORIGINS` with that exact HTTPS origin, optionally followed by explicitly needed local origins. Do not use `*`. Save the variable and wait for the manual redeploy to finish.
5. Verify the API health endpoint again, then open the actual deployed frontend and check Overview, Reviews Inbox, Crisis Monitor, Location Analytics, Knowledge Base, and Response Studio. Upload/index only the provided fictional policy examples, then generate a response for a synthetic review and verify its citations, workflow, edit, approval, and audit flow. Check mobile-width rendering and browser console/network errors. Do not approve or send anything to an external review platform; the app has no publishing integration.
6. Record the actual Vercel and Render URLs in this document and the assessment reports only after those checks pass. No live URLs are recorded here yet.

### Assessment environment variables

The Render Blueprint sets the following safe demo defaults:

- `APP_ENV=demo`
- `DATABASE_URL=sqlite:////var/data/revio.db`
- `KNOWLEDGE_VECTOR_BACKEND=sqlite`
- `KNOWLEDGE_VECTOR_PATH=/var/data/knowledge-index`
- `HF_HOME=/var/data/huggingface` and `HF_HUB_CACHE=/var/data/huggingface/hub`
- `REVIO_SENTIMENT_PROVIDER=fallback`, `REVIO_ASPECT_PROVIDER=rules`, and `RESPONSE_LLM_PROVIDER=demo`
- `CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000` until the actual Vercel origin is known

No secret is required for this configuration. Do not add `RESPONSE_LLM_API_KEY` unless a separate data-processing and cost decision has been made. When set, reviews and retrieved policy text are sent to that provider.

### Deployment configuration behavior

- Render runs `bash services/api/scripts/render-build.sh` to install base FastAPI, RAG, and LangGraph requirements on Python 3.12.16. The local verified interpreter is Python 3.12.6; this newer cloud patch is in the same Python minor series and has not yet been exercised on Render.
- `bash services/api/scripts/render-start.sh` binds Uvicorn to Render's `PORT` on `0.0.0.0` and one worker. FastAPI lifespan applies Alembic migrations and synchronizes only the explicitly synthetic demo review fixture. Both are idempotent.
- Render's `/health` check performs a database query. It does not load or health-check the embedding model; the model is intentionally lazy-loaded.
- `NEXT_PUBLIC_API_BASE_URL` is compiled into the browser bundle at build time. Change it in Vercel and redeploy the frontend when the API origin changes.
- The demo `X-Tenant-Slug` header is workspace selection, not authentication. This public demo is not production-secure and can be mutated by anyone who can reach the API. Never upload real customer information, credentials, or private policies. CORS is a browser policy, not access control.

## Provider references checked on 16 November 2026

- [Render compute plans](https://render.com/docs/compute-plans) and [current Render pricing](https://render.com/pricing)
- [Render persistent disk behavior and limitations](https://render.com/docs/disks)
- [Render Blueprint reference](https://render.com/docs/blueprint-spec) and [Python version selection](https://render.com/docs/python-version)
- [Python 3.12.16 security release](https://www.python.org/downloads/release/python-31216/)
- [Render deployment regions](https://render.com/docs/regions)
- [Vercel monorepo root-directory setup](https://vercel.com/docs/monorepos) and [environment variables](https://vercel.com/docs/environment-variables)
