"""Start the Codespaces API and restore only the committed synthetic demo data."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
API_PORT = int(os.environ.get("REVIO_API_PORT", "8000"))
API_URL = os.environ.get("REVIO_BOOTSTRAP_API_URL", f"http://127.0.0.1:{API_PORT}").rstrip("/")
TENANT_HEADERS = {"X-Tenant-Slug": "revio-demo"}
DEMO_POLICY_FILES = {
    "upi-refunds.md",
    "booking-cancellations.md",
    "service-escalation.md",
    "delivery-delays.md",
    "product-returns.md",
    "restaurant-service-recovery.md",
}
PID_FILE = Path(os.environ.get("REVIO_API_PID_FILE", "/tmp/revio-api.pid"))
LOG_FILE = Path(os.environ.get("REVIO_API_LOG_FILE", "/tmp/revio-api.log"))


class BootstrapError(RuntimeError):
    pass


def _request(path: str, *, method: str = "GET", body: bytes | None = None, timeout: int = 20):
    request = Request(
        f"{API_URL}{path}",
        data=body,
        headers={**TENANT_HEADERS, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except HTTPError as exc:
        payload = exc.read()
        try:
            detail = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = payload.decode("utf-8", errors="replace")
        raise BootstrapError(f"API {method} {path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise BootstrapError(f"Could not reach the local API at {API_URL}: {exc.reason}") from exc


def _server_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("APP_ENV", "demo")
    environment.setdefault("APP_NAME", "REVIO API - DEMONSTRATION")
    environment.setdefault("DATABASE_URL", f"sqlite:///{(API_ROOT / 'revio.db').as_posix()}")
    environment.setdefault("KNOWLEDGE_VECTOR_BACKEND", "sqlite")
    environment.setdefault("KNOWLEDGE_VECTOR_PATH", str(API_ROOT / "chroma_data"))
    environment.setdefault("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    environment.setdefault("HF_HUB_CACHE", str(Path(environment["HF_HOME"]) / "hub"))
    environment.setdefault("REVIO_SENTIMENT_PROVIDER", "fallback")
    environment.setdefault("REVIO_ASPECT_PROVIDER", "rules")
    environment.setdefault("RESPONSE_LLM_PROVIDER", "demo")

    origins = [
        origin.strip().rstrip("/")
        for origin in environment.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ] or ["http://localhost:3000", "http://127.0.0.1:3000"]
    codespace_name = environment.get("CODESPACE_NAME")
    if codespace_name:
        origins.append(f"https://{codespace_name}-3000.app.github.dev")
    vercel_origin = environment.get("VERCEL_ORIGIN", "").strip().rstrip("/")
    if vercel_origin:
        if not vercel_origin.startswith("https://"):
            raise BootstrapError("VERCEL_ORIGIN must be the exact https:// origin shown by Vercel.")
        origins.append(vercel_origin)
    environment["CORS_ALLOWED_ORIGINS"] = ",".join(dict.fromkeys(origins))
    environment["PORT"] = str(API_PORT)
    return environment


def _stop_api() -> None:
    if not PID_FILE.exists():
        return
    try:
        process_id = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(process_id, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    PID_FILE.unlink(missing_ok=True)
    for _ in range(30):
        try:
            _request("/health", timeout=1)
        except BootstrapError:
            return
        time.sleep(0.5)
    raise BootstrapError("The previous API process did not stop; inspect /tmp/revio-api.log before retrying.")


def _start_api(environment: dict[str, str]) -> None:
    try:
        _request("/health", timeout=2)
        print(f"REVIO API is already responding on port {API_PORT}.")
        return
    except BootstrapError:
        pass

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    popen_options = {"start_new_session": True}
    if os.name == "nt":
        popen_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(API_PORT), "--workers", "1"],
            cwd=API_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            **popen_options,
        )
    PID_FILE.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"Started the one-worker REVIO API (log: {LOG_FILE}). Waiting for migrations and health check.")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BootstrapError(f"The API exited with code {process.returncode}; inspect {LOG_FILE}.")
        try:
            _, health = _request("/health", timeout=2)
            if health == {"status": "ok", "database": "ok"}:
                return
        except BootstrapError:
            time.sleep(2)
    raise BootstrapError(f"The API did not become healthy within 180 seconds; inspect {LOG_FILE}.")


def _vector_count(tenant_id: str, document_id: str, vector_db: Path) -> int:
    if not vector_db.is_file():
        return 0
    try:
        with sqlite3.connect(f"file:{vector_db.as_posix()}?mode=ro", uri=True, timeout=5) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_vectors'"
            ).fetchone()
            if not exists:
                return 0
            return int(connection.execute(
                "SELECT count(*) FROM knowledge_vectors WHERE tenant_id=? AND document_id=?",
                (tenant_id, document_id),
            ).fetchone()[0])
    except sqlite3.Error:
        return 0


def _restore_demo_knowledge(environment: dict[str, str]) -> None:
    source_dir = REPOSITORY_ROOT / "data" / "demo" / "knowledge"
    available = {path.name for path in source_dir.glob("*.md") if path.name.casefold() != "readme.md"}
    if available != DEMO_POLICY_FILES:
        raise BootstrapError("The committed synthetic policy set is incomplete; expected exactly six known policy files.")

    _request("/api/v1/knowledge/demo-documents", method="POST", body=b"{}", timeout=30)
    _, documents = _request("/api/v1/knowledge/documents", timeout=20)
    selected = [
        document for document in documents
        if document["source_filename"] in DEMO_POLICY_FILES
        and document["title"].startswith("DEMO / SYNTHETIC DATA")
    ]
    found = {document["source_filename"] for document in selected}
    if found != DEMO_POLICY_FILES:
        raise BootstrapError(f"Expected six synthetic demo policies, found {len(found)}: {sorted(found)}")

    vector_path = Path(environment["KNOWLEDGE_VECTOR_PATH"]) / "knowledge-vectors.sqlite3"
    db_path = Path(environment["DATABASE_URL"].removeprefix("sqlite:///"))
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5) as connection:
        tenant_row = connection.execute("SELECT id FROM tenants WHERE slug='revio-demo'").fetchone()
    if tenant_row is None:
        raise BootstrapError("The synthetic demo tenant is missing after the database migration and initialization.")
    tenant_id = tenant_row[0]

    for document in selected:
        if document["status"] == "processing":
            continue
        if document["status"] == "failed" or _vector_count(tenant_id, document["id"], vector_path) == 0:
            _request(f"/api/v1/knowledge/documents/{document['id']}/reindex", method="POST", body=b"{}")

    deadline = time.monotonic() + 900
    latest: list[dict] = []
    while time.monotonic() < deadline:
        _, latest = _request("/api/v1/knowledge/documents", timeout=20)
        selected = [
            document for document in latest
            if document["source_filename"] in DEMO_POLICY_FILES
            and document["title"].startswith("DEMO / SYNTHETIC DATA")
        ]
        failed = [document for document in selected if document["status"] == "failed"]
        if failed:
            errors = "; ".join(f"{item['source_filename']}: {item['error_message']}" for item in failed)
            raise BootstrapError(f"Synthetic policy indexing failed: {errors}. Inspect {LOG_FILE}.")
        if len(selected) == 6 and all(document["status"] == "ready" and document["chunk_count"] > 0 for document in selected):
            print("REVIO synthetic knowledge ready: 6/6 policy files indexed with the configured embedding model and SQLite vector store.")
            return
        time.sleep(3)
    statuses = ", ".join(f"{item['source_filename']}={item['status']}" for item in selected)
    raise BootstrapError(f"Synthetic policy indexing did not finish within 15 minutes ({statuses}). Inspect {LOG_FILE}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "restart", "stop"), nargs="?", default="start")
    args = parser.parse_args()

    if args.action == "stop":
        _stop_api()
        print("Stopped the REVIO API process started by this Codespace.")
        return 0
    if args.action == "restart":
        _stop_api()

    environment = _server_environment()
    _start_api(environment)
    _restore_demo_knowledge(environment)
    print(f"REVIO API: https://<codespace-name>-{API_PORT}.app.github.dev (make port {API_PORT} Public only when ready to share).")
    print("All seeded review and policy content is fictional DEMO / SYNTHETIC DATA.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootstrapError as exc:
        print(f"REVIO Codespaces bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
