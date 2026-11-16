#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

# Codespaces can enter recovery mode after a failed or skipped creation hook.
# setup.sh is fingerprinted and idempotent, so this also repairs a missing or
# incomplete virtual environment without reinstalling dependencies on each start.
bash .devcontainer/setup.sh
exec services/api/.venv/bin/python services/api/scripts/codespaces_bootstrap.py start
