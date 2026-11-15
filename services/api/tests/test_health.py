from sqlalchemy import func, select
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models import Membership, Tenant, User


def test_health_reports_database_connection() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_demo_workspace_and_membership_are_seeded_idempotently() -> None:
    with TestClient(app):
        pass
    with TestClient(app):
        pass

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == "revio-demo")) == 1
        assert db.scalar(select(func.count()).select_from(User).where(User.email == "demo@revio.local")) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1
