from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentTenant, DbSession
from app.models import ResponseAuditEvent, ResponseDraft, Review
from app.schemas.responses import ResponseAuditEventOut, ResponseDraftOut, ResponseEditIn, ResponseRejectIn
from app.services.response_workflow import WorkflowFailure, run_response_workflow, serialize_draft

router = APIRouter(prefix="/api/v1", tags=["responses"])


def _draft_or_404(db: Session, tenant_id: str, draft_id: str) -> ResponseDraft:
    draft = db.scalar(select(ResponseDraft).where(
        ResponseDraft.id == draft_id, ResponseDraft.tenant_id == tenant_id
    ))
    if draft is None:
        raise HTTPException(status_code=404, detail={"code": "response_not_found", "message": "Response draft not found in this workspace."})
    return draft


@router.post("/reviews/{review_id}/responses/generate", response_model=ResponseDraftOut, status_code=201)
def generate_response(review_id: str, tenant: CurrentTenant, db: DbSession) -> ResponseDraftOut:
    try:
        draft = run_response_workflow(db, tenant.id, review_id)
    except WorkflowFailure as exc:
        if exc.code == "review_not_found":
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message, "workflow_trace": exc.trace}) from exc
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message, "workflow_trace": exc.trace}) from exc
    return ResponseDraftOut(**serialize_draft(draft))


@router.get("/reviews/{review_id}/responses", response_model=list[ResponseDraftOut])
def list_review_responses(review_id: str, tenant: CurrentTenant, db: DbSession) -> list[ResponseDraftOut]:
    review = db.scalar(select(Review.id).where(Review.id == review_id, Review.tenant_id == tenant.id))
    if review is None:
        raise HTTPException(status_code=404, detail={"code": "review_not_found", "message": "Review not found in this workspace."})
    drafts = db.scalars(select(ResponseDraft).where(
        ResponseDraft.tenant_id == tenant.id, ResponseDraft.review_id == review_id
    ).order_by(ResponseDraft.version.desc())).all()
    return [ResponseDraftOut(**serialize_draft(draft)) for draft in drafts]


@router.get("/responses/{draft_id}", response_model=ResponseDraftOut)
def get_response(draft_id: str, tenant: CurrentTenant, db: DbSession) -> ResponseDraftOut:
    return ResponseDraftOut(**serialize_draft(_draft_or_404(db, tenant.id, draft_id)))


@router.patch("/responses/{draft_id}", response_model=ResponseDraftOut)
def edit_response(draft_id: str, payload: ResponseEditIn, tenant: CurrentTenant, db: DbSession) -> ResponseDraftOut:
    draft = _draft_or_404(db, tenant.id, draft_id)
    if draft.status not in {"draft", "edited"}:
        raise HTTPException(status_code=409, detail={"code": "response_not_editable", "message": "Only draft responses can be edited."})
    previous_status = draft.status
    draft.response_text = payload.response_text.strip()
    draft.status = "edited"
    draft.updated_at = datetime.now(timezone.utc)
    db.add(ResponseAuditEvent(
        tenant_id=tenant.id, draft_id=draft.id, action="edited", from_status=previous_status,
        to_status="edited", actor="demo-operator", reason=None,
    ))
    db.commit()
    db.refresh(draft)
    return ResponseDraftOut(**serialize_draft(draft))


@router.post("/responses/{draft_id}/approve", response_model=ResponseDraftOut)
def approve_response(draft_id: str, tenant: CurrentTenant, db: DbSession) -> ResponseDraftOut:
    draft = _draft_or_404(db, tenant.id, draft_id)
    if draft.status not in {"draft", "edited"}:
        raise HTTPException(status_code=409, detail={"code": "response_not_approvable", "message": "Only draft or edited responses can be approved."})
    previous_status = draft.status
    now = datetime.now(timezone.utc)
    draft.status = "approved"
    draft.approved_at = now
    draft.updated_at = now
    db.add(ResponseAuditEvent(
        tenant_id=tenant.id, draft_id=draft.id, action="approved", from_status=previous_status,
        to_status="approved", actor="demo-operator", reason=None, created_at=now,
    ))
    db.commit()
    db.refresh(draft)
    return ResponseDraftOut(**serialize_draft(draft))


@router.post("/responses/{draft_id}/reject", response_model=ResponseDraftOut)
def reject_response(draft_id: str, payload: ResponseRejectIn, tenant: CurrentTenant, db: DbSession) -> ResponseDraftOut:
    draft = _draft_or_404(db, tenant.id, draft_id)
    if draft.status not in {"draft", "edited"}:
        raise HTTPException(status_code=409, detail={"code": "response_not_rejectable", "message": "Only draft or edited responses can be rejected."})
    previous_status = draft.status
    now = datetime.now(timezone.utc)
    draft.status = "rejected"
    draft.rejected_at = now
    draft.updated_at = now
    db.add(ResponseAuditEvent(
        tenant_id=tenant.id, draft_id=draft.id, action="rejected", from_status=previous_status,
        to_status="rejected", actor="demo-operator", reason=payload.reason.strip() if payload.reason else None, created_at=now,
    ))
    db.commit()
    db.refresh(draft)
    return ResponseDraftOut(**serialize_draft(draft))


@router.get("/responses/{draft_id}/audit", response_model=list[ResponseAuditEventOut])
def response_audit(draft_id: str, tenant: CurrentTenant, db: DbSession) -> list[ResponseAuditEventOut]:
    draft = _draft_or_404(db, tenant.id, draft_id)
    events = db.scalars(select(ResponseAuditEvent).where(
        ResponseAuditEvent.tenant_id == tenant.id, ResponseAuditEvent.draft_id == draft.id
    ).order_by(ResponseAuditEvent.created_at, ResponseAuditEvent.id)).all()
    return [ResponseAuditEventOut.model_validate(event) for event in events]
