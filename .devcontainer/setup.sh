#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

python -m venv services/api/.venv
services/api/.venv/bin/python -m pip install --disable-pip-version-check -r services/api/requirements-codespaces.txt
npm --prefix apps/web ci
