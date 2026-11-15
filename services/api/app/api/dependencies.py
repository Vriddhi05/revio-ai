from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Tenant

DbSession = Annotated[Session, Depends(get_db)]


def get_tenant(
    db: DbSession,
    tenant_slug: Annotated[str, Header(alias="X-Tenant-Slug")] = "revio-demo",
) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug.strip()))
    if tenant is None:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Workspace not found."})
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_tenant)]
