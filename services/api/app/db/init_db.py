from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config

from app.core.config import API_ROOT
from app.db.session import SessionLocal
from app.models import Membership, Tenant, User


def initialize_database() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "head")
    with SessionLocal() as db:
        ensure_demo_workspace(db)


def ensure_demo_workspace(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == "revio-demo"))
    if tenant is None:
        tenant = Tenant(name="Revio Demo", slug="revio-demo", is_demo=True)
        db.add(tenant)
        db.flush()

    user = db.scalar(select(User).where(User.email == "demo@revio.local"))
    if user is None:
        user = User(display_name="Demo Account", email="demo@revio.local")
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
    )
    if membership is None:
        db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))

    db.commit()
    db.refresh(tenant)
    return tenant
