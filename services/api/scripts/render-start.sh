#!/usr/bin/env bash
set -euo pipefail

API_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$API_ROOT"

# The mounted volume persists SQLite, the exact-cosine vector index, and lazy model downloads.
mkdir -p "${KNOWLEDGE_VECTOR_PATH:-/var/data/knowledge-index}"
mkdir -p "${HF_HUB_CACHE:-/var/data/huggingface/hub}"

# FastAPI lifespan runs Alembic migrations and idempotently seeds only the 45 synthetic rows.
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --workers 1
