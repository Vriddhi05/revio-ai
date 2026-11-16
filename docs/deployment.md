# REVIO zero-budget assessment deployment

## Current status

No hosting service has been created, no deployment has been attempted, and no public URL exists. This repository prepares a temporary synthetic-data demonstration using a personal GitHub Codespace for FastAPI and Vercel Hobby for Next.js. No paid plan, trial, billing method, LLM credential, or hosted resource is part of this plan. Public deployment and URL checks remain pending the owner’s account setup.

Do not upload real customer reviews, private business policies, credentials, or personal information. The X-Tenant-Slug header selects the demo workspace; it is not authentication or authorization. A public forwarded API port allows anyone with its URL to reach the unauthenticated demo API. REVIO is not production-secure.

## Chosen zero-budget topology

| Part | Service | Configuration | Persistence / limits |
| --- | --- | --- | --- |
| Next.js frontend | Vercel Hobby | Import Vriddhi05/revio-ai; root apps/web; set NEXT_PUBLIC_API_BASE_URL to the public API origin | Free usage is capped; Hobby is for personal, non-commercial use. Do not start a Pro trial. |
| FastAPI, SQLite, vector index, LangGraph | GitHub Codespaces Free on a personal account | Use .devcontainer/devcontainer.json; it sets no minimum machine size, so GitHub can offer the types available to the account | GitHub Free includes 120 Codespaces core-hours and 15 GB-month storage for personal accounts. Compute use depends on the selected core count. Confirm remaining quota before creation. |
| Reviews and knowledge data | SQLite files in the Codespace workspace | Startup applies Alembic, synchronizes the 45 managed fictional reviews, and restores/reindexes the six committed policy examples | Files survive Codespace stop/start but are lost if the Codespace is deleted or rebuilt from scratch. The committed fictional dataset can be reconstructed; user uploads are temporary. |
| Embedding model | intfloat/multilingual-e5-small, pinned revision in the evaluation report | Downloaded from Hugging Face during first policy indexing and cached in the Codespace home directory | The recorded local evaluation measured 470.44 MB of model files and 648.07 MB process RSS after load. A separate full-API diagnostic with multilingual MiniLM L12 measured 689.89 MB after query embedding. These are local measurements, not Codespaces benchmarks. Choose an available machine with enough memory for the model and API; startup may fail on a constrained machine. |

This is temporary assessment compute, not persistent public hosting. GitHub documents a 12-hour maximum lifetime and a default 30-minute idle timeout for Codespaces. Public traffic is not a promised keep-alive mechanism. Keep the Codespace active while presenting and restart it manually if it stops. Its forwarded port URL belongs to that Codespace; avoid creating a replacement unless necessary because the API origin will change.

Vercel Hobby terms are limited to personal, non-commercial use. Use this route only if the owner’s assessment demonstration qualifies under those terms. Otherwise stop and ask for another genuinely free option; do not accept a paid trial or upgrade.

## Why Render Free is not selected

Render Free documents 512 MB RAM, no persistent disk, and loss of local files on restart, redeploy, or idle spin-down. It stops after 15 minutes without inbound traffic and takes about a minute to restart. REVIO’s selected E5 model alone measured 648.07 MB RSS in the local retrieval evaluation, already above the published limit. The full API plus the smaller multilingual MiniLM L12 measured 689.89 MB after a query in this environment, also above the limit. These local readings do not predict Render’s exact Linux RSS; they do show that the current implementation cannot be shown to fit safely in 512 MB. Do not deploy this API to Render Free for the assessment.

The 45 synthetic reviews are synchronized idempotently by FastAPI startup. The existing demo-policy endpoint adds the six committed files idempotently; this repository’s Codespaces bootstrap calls that endpoint and checks/reindexes missing SQLite vector rows. On a completely reset filesystem, this can recreate reviews, policies, and the vector index. It does not solve Render’s model memory limit, or repeated model download and cold indexing. See [Render’s free-tier limits](https://render.com/docs/free).

The Codespaces setup installs FastAPI, the RAG and LangGraph dependencies, and frontend dependencies from the repository. It selects the real tenant-filtered exact-cosine SQLite vector store, not a mock, and retains the existing E5 embeddings, citations, LangGraph Response Studio, human approval, and audit flow. No hosted LLM key is configured; drafting remains the clearly labeled deterministic demo provider.

## Before setup: confirm the free allowance

1. Sign in to the personal GitHub account that owns Vriddhi05/revio-ai.
2. Open Settings, then Billing and licensing, then Usage. Check remaining Codespaces included usage for this billing month. GitHub Free personal accounts include 120 core-hours and 15 GB-month. The repository must remain under a personal account to use that allowance. Compute is charged against included usage at the selected machine's core multiplier; inspect the remaining balance before creation.
3. Do not add a payment method, set a positive spending limit, or accept an upgrade. If GitHub says the included quota is exhausted or asks for payment, cancel and stop. Do not create the Codespace.
4. Sign in to Vercel and select Hobby / Free only. Do not start a Pro trial. If the account says the project or use is outside Hobby’s personal non-commercial terms, stop.

See [GitHub’s included product usage](https://docs.github.com/en/billing/reference/product-usage-included) and [Codespaces included-usage behavior](https://docs.github.com/en/codespaces/troubleshooting/troubleshooting-included-usage). If free quota is exhausted and there is no payment method, GitHub restricts Codespaces rather than extending the free allowance.

## Create and start the backend Codespace

1. Open https://github.com/Vriddhi05/revio-ai while signed in to the personal GitHub account.
2. Select the green Code button, open the Codespaces tab, and choose Create codespace on main. Use the latest main commit. The committed devcontainer has no `hostRequirements` minimum and should allow GitHub to offer account-available machine types. Choose an available machine with enough memory for the measured E5 model/API footprint. Do not choose a paid option. If the list is still empty, check the account and organization causes below before retrying.
3. Let the Codespace finish setup. It installs dependencies from services/api/requirements-codespaces.txt and apps/web/package-lock.json, starts the API, applies Alembic migrations, synchronizes the 45 fictional reviews, then adds and indexes the six synthetic policy files. First indexing downloads the pinned model and can take a few minutes. If setup fails, inspect /tmp/revio-api.log in the Codespace terminal and do not proceed until healthy.
4. In the Codespace terminal run:

       curl -fsS http://127.0.0.1:8000/health
       curl -fsS -H 'X-Tenant-Slug: revio-demo' http://127.0.0.1:8000/api/v1/knowledge/documents

   Health should return {"status":"ok","database":"ok"}. The document list should contain six titles beginning DEMO / SYNTHETIC DATA with ready status.
5. Open the Ports tab in the Codespaces editor. Port 8000 is private by default. When ready to share the demo, change only port 8000 to Public and copy its URL. The expected format is https://<codespace-name>-8000.app.github.dev; use the exact URL displayed by GitHub. A public port is anonymously reachable; see [GitHub’s port-forwarding documentation](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace).
6. From a new browser tab, check the API origin plus /health. Do not publish the frontend until this succeeds.

### If GitHub still shows “None” for every machine type

This repository previously required 4 CPUs, 16 GB RAM, and 64 GB storage in `hostRequirements`; that minimum has been removed. The available machine list can still depend on GitHub account entitlements, remaining included quota, repository ownership/policies, and regional capacity. GitHub says exhausted personal included usage restricts new Codespaces unless paid billing is configured; keep billing at $0 and do not add a payment method.

1. Confirm the Codespaces creation page is using the latest `main` commit, then retry once.
2. Open [GitHub billing usage](https://github.com/settings/billing) and inspect both Codespaces compute and storage for the current billing cycle. Included Codespaces usage applies to personal accounts; if either quota is exhausted, wait for its reset or stop this deployment path. Do not enable paid overage.
3. Confirm `Vriddhi05/revio-ai` is under the personal GitHub account whose included quota you checked. If it is organization-owned, ask an organization owner to check **Settings → Code, planning, and automation → Codespaces → Policies** for a machine-type restriction and whether Codespaces is enabled. Do not change an organization policy unless you administer it.
4. If quota is available and there is no applicable policy, try again later or use another offered region. Machine availability can vary by location. If all regions remain empty, contact GitHub Support with the repository, branch, region, and screenshot; do not select a paid machine.
The committed bootstrap calls the existing demo-policy endpoint, verifies the six expected synthetic Markdown sources, and checks for missing SQLite vector rows. If vectors are absent or a document has failed processing, it requests reindexing. It uses existing tenant/content-hash deduplication and stable chunk IDs. It does not seed user uploads or actual customer data.

## Create the Vercel Hobby frontend

1. In Vercel choose Add New, then Project. Connect GitHub if prompted, and grant access only to Vriddhi05/revio-ai when repository selection is available.
2. Import Vriddhi05/revio-ai and select Hobby / Free. Do not choose a paid trial or upgrade.
3. Set Root Directory to apps/web. Keep the detected Next.js framework. Set Install Command to npm ci and Build Command to npm run build. The monorepo Next config already sets the repository tracing root.
4. Add this Production environment variable, replacing the placeholder with the exact API origin copied from Codespaces. It is a public URL, not a secret; do not add /api/v1 or a trailing path.

       NEXT_PUBLIC_API_BASE_URL=https://<exact-codespace-name>-8000.app.github.dev

5. Deploy on Hobby and copy the actual https://<project>.vercel.app URL shown by Vercel. Record no live URL in reports until the real deployed site has passed browser checks.

See Vercel’s [Hobby plan and limits](https://vercel.com/docs/plans/hobby) and [monorepo root configuration](https://vercel.com/docs/monorepos). If a free usage cap pauses a feature, do not upgrade.

## Allow the Vercel origin and restart the API

Replace the placeholder with the exact Vercel production origin, then run this in the Codespace terminal:

    VERCEL_ORIGIN="https://<exact-project>.vercel.app" services/api/.venv/bin/python services/api/scripts/codespaces_bootstrap.py restart

The restart preserves the workspace SQLite data and vector index, applies explicit-origin CORS, checks API health, verifies the 45-review source and six policy sources, and rebuilds missing synthetic vectors. Do not use a wildcard CORS origin. Check /health and run a knowledge search again before sharing the Vercel URL.

## Public review checklist after account setup

No public checks are claimed yet. After the owner creates the services and provides the actual URLs, verify:

- API GET /health returns the database health response.
- Overview, Reviews Inbox, Crisis Monitor, Location Analytics, Knowledge Base, and Response Studio load without uncaught browser errors.
- Inbox and analytics show the 45 clearly labeled Indian synthetic reviews across Jaipur, Chandigarh, and Ludhiana.
- Knowledge search returns actual passages from the six indexed synthetic policy documents with source citations and page/reference metadata; an unrelated query abstains.
- Generate a draft for a synthetic review; verify LangGraph steps, citations, validation warnings, edit, human approve/reject, and audit entry. Approval is internal only and does not publish a reply.
- Inspect browser console/network errors, API logs, and mobile-width layout. Record only actual observed URLs and results.

## Limitations and future scaling

- Codespaces has included monthly quotas, idle shutdown, and a 12-hour maximum lifetime. It is suitable only for a time-bounded demo while the owner keeps the Codespace available; it is not durable hosting and has no SLA.
- SQLite, uploads, and vector rows survive a normal Codespace stop/start but are lost if the Codespace is deleted or rebuilt. The 45 review and six policy fixtures are reproducible; user uploads are not.
- The public API has no application authentication. The demo tenant header is workspace selection only. Use synthetic data only.
- Vercel Hobby is personal and non-commercial and has included-usage caps. Confirm eligibility and remaining account quotas.
- No hosted LLM credentials exist. Response generation remains a deterministic, labeled demo fallback. Do not claim live model generation.
- The public demo has no durable queue, monitoring, backups, protected customer-data boundary, or review-platform integration.
- A later approved production deployment should add authenticated tenant membership, durable relational and object storage, a server-backed vector service, queued background work, backups, rate limits, and resource monitoring. That is outside the zero-budget assessment deployment.
