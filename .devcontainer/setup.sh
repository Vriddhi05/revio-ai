#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[revio-setup] %s\n' "$*"
}

on_error() {
  local status=$?
  local line=$1
  local failed_command=$2
  trap - ERR
  printf '[revio-setup] ERROR: command failed at line %s (exit %s): %s\n' "$line" "$status" "$failed_command" >&2
  exit "$status"
}

trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPOSITORY_ROOT"

VENV_DIR="$REPOSITORY_ROOT/services/api/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
SETUP_MARKER="$VENV_DIR/.revio-codespaces-setup-complete"
FINGERPRINT_FILES=(
  .devcontainer/setup.sh
  services/api/requirements-codespaces.txt
  services/api/requirements.txt
  services/api/requirements-agent.txt
  services/api/requirements-ai.txt
  apps/web/package-lock.json
)

for command_name in python3 npm sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '[revio-setup] ERROR: required command is unavailable: %s\n' "$command_name" >&2
    exit 1
  fi
done

SETUP_FINGERPRINT="$(sha256sum "${FINGERPRINT_FILES[@]}" | sha256sum | cut -d ' ' -f 1)"
if [[ -x "$VENV_PYTHON" && -f "$SETUP_MARKER" && -d apps/web/node_modules ]] \
  && [[ "$(cat "$SETUP_MARKER")" == "$SETUP_FINGERPRINT" ]] \
  && "$VENV_PYTHON" -c 'import fastapi, langgraph, sentence_transformers, uvicorn' >/dev/null 2>&1; then
  log "Python and Node dependencies already match the current requirements; skipping installation."
  exit 0
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  log 'Creating the backend Python virtual environment.'
  python3 -m venv "$VENV_DIR"
fi

log 'Installing backend dependencies from requirements-codespaces.txt.'
"$VENV_PYTHON" -m pip install --disable-pip-version-check -r services/api/requirements-codespaces.txt
"$VENV_PYTHON" -c 'import fastapi, langgraph, uvicorn; print("[revio-setup] FastAPI, LangGraph, and Uvicorn imports passed.")'

log 'Installing frontend dependencies with npm ci.'
npm --prefix apps/web ci

printf '%s\n' "$SETUP_FINGERPRINT" > "$SETUP_MARKER"
log 'Dependency setup completed successfully.'
