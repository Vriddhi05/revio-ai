from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Tenant

DbSession = Annotated[Session, Depends(get_db)]


def get_tenant(
    db: DbSession,
    tenant_slug: Annotated[str, Header(alias="X-Tenant-Slug")] = "revio-demo",
) -> Tenant:
    resolved_slug = tenant_slug.strip()
    if get_settings().demo_mode and resolved_slug != "revio-demo":
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Workspace not found."})
    tenant = db.scalar(select(Tenant).where(Tenant.slug == resolved_slug))
    if tenant is None:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Workspace not found."})
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_tenant)]
