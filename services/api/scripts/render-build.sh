#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPOSITORY_ROOT"

python -m pip install --upgrade pip
python -m pip install \
  -r services/api/requirements.txt \
  -r services/api/requirements-rag.txt \
  -r services/api/requirements-agent.txt
