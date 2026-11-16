import json
import runpy
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.init_db import seed_demo_reviews
from app.db.session import SessionLocal
from app.main import app
from app.models import Location, Membership, Review, ReviewImportJob, Tenant, User
from app.services.review_csv import mark_duplicates, parse_review_csv


def test_health_reports_database_connection() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        cors_response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert cors_response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_preflight_allows_workspace_header_and_json_content_type() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/analytics/summary",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type,x-tenant-slug",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in response.headers["access-control-allow-methods"]
    allowed_headers = {header.strip().casefold() for header in response.headers["access-control-allow-headers"].split(",")}
    assert {"content-type", "x-tenant-slug"} <= allowed_headers


def test_codespaces_bootstrap_adds_exact_vercel_origin(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CODESPACE_NAME", raising=False)
    monkeypatch.delenv("VERCEL_ORIGIN", raising=False)
    bootstrap_path = Path(__file__).resolve().parents[1] / "scripts" / "codespaces_bootstrap.py"
    bootstrap = runpy.run_path(str(bootstrap_path))

    environment = bootstrap["_server_environment"]()

    assert environment["APP_ENV"] == "demo"
    assert "https://revio-ai-smoky.vercel.app" in environment["CORS_ALLOWED_ORIGINS"].split(",")


def test_codespaces_bootstrap_accepts_an_explicit_vercel_origin(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CODESPACE_NAME", raising=False)
    monkeypatch.setenv("VERCEL_ORIGIN", "https://preview.example")
    bootstrap_path = Path(__file__).resolve().parents[1] / "scripts" / "codespaces_bootstrap.py"
    bootstrap = runpy.run_path(str(bootstrap_path))

    environment = bootstrap["_server_environment"]()

    assert "https://preview.example" in environment["CORS_ALLOWED_ORIGINS"].split(",")


def test_codespaces_bootstrap_rejects_non_https_vercel_origin(monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("VERCEL_ORIGIN", "http://revio-ai-smoky.vercel.app")
    bootstrap_path = Path(__file__).resolve().parents[1] / "scripts" / "codespaces_bootstrap.py"
    bootstrap = runpy.run_path(str(bootstrap_path))

    with pytest.raises(bootstrap["BootstrapError"], match="exact https:// origin"):
        bootstrap["_server_environment"]()


def test_codespaces_forwards_demo_api_port_public_by_default() -> None:
    devcontainer_path = Path(__file__).resolve().parents[3] / ".devcontainer" / "devcontainer.json"
    devcontainer = json.loads(devcontainer_path.read_text(encoding="utf-8"))

    assert devcontainer["portsAttributes"]["8000"]["visibility"] == "public"


def test_codespaces_bootstrap_stop_handles_socket_reset_after_shutdown(monkeypatch, tmp_path) -> None:
    bootstrap_path = Path(__file__).resolve().parents[1] / "scripts" / "codespaces_bootstrap.py"
    bootstrap = runpy.run_path(str(bootstrap_path))
    pid_file = tmp_path / "api.pid"
    pid_file.write_text("12345\n", encoding="utf-8")
    bootstrap_globals = bootstrap["_stop_api"].__globals__
    bootstrap_globals["PID_FILE"] = pid_file
    monkeypatch.setattr(bootstrap["os"], "kill", lambda *_args: None)

    def connection_reset(*_args, **_kwargs):
        raise ConnectionResetError("peer closed during shutdown")

    bootstrap_globals["urlopen"] = connection_reset
    bootstrap["_stop_api"]()

    assert not pid_file.exists()


def test_cors_origins_are_explicit_and_normalized() -> None:
    settings = Settings(
        cors_allowed_origins=" https://revio.example/ , http://localhost:3000,,https://revio.example "
    )

    assert settings.cors_origins == ["https://revio.example", "http://localhost:3000"]


def test_cors_wildcard_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="explicit origins"):
        Settings(cors_allowed_origins="*")


def test_demo_workspace_and_membership_are_seeded_idempotently() -> None:
    with TestClient(app):
        pass
    with TestClient(app):
        pass

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == "revio-demo")) == 1
        assert db.scalar(select(func.count()).select_from(User).where(User.email == "demo@revio.local")) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1


def test_demo_dataset_is_fictional_and_spans_three_locations() -> None:
    with TestClient(app):
        pass
    with TestClient(app):
        pass

    with SessionLocal() as db:
        tenant_id = db.scalar(select(Tenant.id).where(Tenant.slug == "revio-demo"))
        seeded = db.execute(
            select(Review, Location.name)
            .join(Location, Review.location_id == Location.id)
            .where(
                Review.tenant_id == tenant_id,
                Review.ingestion_source == "demo_csv",
                Review.external_review_id.like("REVIO-IN-DEMO-%"),
            )
        ).all()
        reviews = [review for review, _ in seeded]
        locations = {location_name for _, location_name in seeded}
        expected_locations = {
            "Jaipur, Rajasthan, India",
            "Chandigarh, India",
            "Ludhiana, Punjab, India",
        }

        assert len(reviews) == 45
        assert len({review.external_review_id for review in reviews}) == 45
        assert all(review.is_synthetic for review in reviews)
        assert locations == expected_locations
        assert {review.rating for review in reviews} == {1, 2, 3, 4, 5}
        assert {review.priority for review in reviews} == {"high", "medium", "normal"}
        assert len({review.review_date for review in reviews}) > 20
        assert db.scalar(
            select(func.count()).select_from(Review).where(
                Review.tenant_id == tenant_id,
                Review.ingestion_source == "demo_csv",
                Review.external_review_id.like("REVIO-DEMO-%"),
            )
        ) == 0


def test_demo_seed_replaces_legacy_fixture_in_place() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with test_session() as db:
            tenant = Tenant(name="Revio Demo", slug="revio-demo", is_demo=True)
            db.add(tenant)
            db.flush()
            old_location = Location(
                tenant_id=tenant.id,
                name="Jaipur, Rajasthan, India",
                normalized_name="jaipur, rajasthan, india",
            )
            old_job = ReviewImportJob(
                tenant_id=tenant.id,
                filename="reviews.csv - fictional demo data",
                file_sha256="a" * 64,
                total_rows=1,
                accepted_rows=1,
                rejected_rows=0,
            )
            db.add_all([old_location, old_job])
            db.flush()
            db.add(
                Review(
                    tenant_id=tenant.id,
                    location_id=old_location.id,
                    import_job_id=old_job.id,
                    review_text="Old synthetic Jaipur cafe fixture row.",
                    rating=2,
                    author_name="Aditi Sharma",
                    source_name="Google Maps",
                    external_review_id="REVIO-DEMO-001",
                    dedupe_key="legacy-demo-dedupe-key",
                    status="needs_attention",
                    priority="high",
                    is_synthetic=True,
                    ingestion_source="demo_csv",
                )
            )
            db.commit()

            seed_demo_reviews(db, tenant)

            migrated = db.scalar(
                select(Review).where(
                    Review.tenant_id == tenant.id,
                    Review.external_review_id == "REVIO-IN-DEMO-001",
                )
            )
            seeded_count = db.scalar(
                select(func.count()).select_from(Review).where(
                    Review.tenant_id == tenant.id,
                    Review.external_review_id.like("REVIO-IN-DEMO-%"),
                )
            )
            assert seeded_count == 45
            assert migrated is not None
            assert migrated.author_name == "Aditi Sharma"
            assert migrated.location.name == "Jaipur, Rajasthan, India"
            assert migrated.review_text != "Old synthetic Jaipur cafe fixture row."
            assert db.get(ReviewImportJob, old_job.id) is None

            sample_path = Path(__file__).resolve().parents[3] / "data" / "demo" / "reviews.csv"
            repeat_import = mark_duplicates(parse_review_csv(sample_path.read_bytes()), db, tenant.id)
            assert repeat_import.accepted_rows == 0
            assert repeat_import.rejected_rows == 45
    finally:
        engine.dispose()
