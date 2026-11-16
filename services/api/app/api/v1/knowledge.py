import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentTenant, DbSession
from app.core.config import get_settings
from app.models import KnowledgeDocument
from app.schemas.knowledge import DemoKnowledgeSeedOut, KnowledgeDocumentOut, KnowledgeSearchHit, KnowledgeSearchIn, KnowledgeSearchOut
from app.services.knowledge_documents import DocumentError, extract_document
from app.services.knowledge_embeddings import QueryTooLongError, get_encoder
from app.services.knowledge_indexing import index_document
from app.services.knowledge_retrieval import retrieve_knowledge
from app.services.knowledge_vectors import get_store

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[5]
DEMO_POLICY_FILENAMES = {
    "booking-cancellations.md",
    "delivery-delays.md",
    "product-returns.md",
    "restaurant-service-recovery.md",
    "service-escalation.md",
    "upi-refunds.md",
}


def _new_document(tenant_id: str, extracted, title: str | None, version: int) -> KnowledgeDocument:
    settings = get_settings()
    return KnowledgeDocument(
        tenant_id=tenant_id,
        title=(title.strip() if title else extracted.title)[:240],
        source_filename=extracted.filename,
        source_key=extracted.source_key,
        media_type=extracted.media_type,
        file_size_bytes=extracted.size_bytes,
        content_sha256=extracted.content_sha256,
        version=version,
        page_count=len(extracted.pages) if extracted.media_type == "application/pdf" else None,
        extracted_chars=extracted.extracted_chars,
        extracted_pages_json=json.dumps(extracted.pages, ensure_ascii=False),
        status="processing",
        chunk_count=0,
        embedding_model=settings.knowledge_embedding_model,
        embedding_revision=settings.knowledge_embedding_revision,
        chunking_version=f"chars-{settings.knowledge_chunk_chars}-{settings.knowledge_chunk_overlap}-tokens-{settings.knowledge_chunk_max_tokens}-{settings.knowledge_chunk_token_overlap}-v1",
    )


def _document_out(document: KnowledgeDocument, duplicate: bool = False) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut(
        id=document.id,
        title=document.title,
        source_filename=document.source_filename,
        media_type=document.media_type,
        file_size_bytes=document.file_size_bytes,
        content_sha256=document.content_sha256,
        version=document.version,
        page_count=document.page_count,
        extracted_chars=document.extracted_chars,
        status=document.status,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
        embedding_model=document.embedding_model,
        embedding_revision=document.embedding_revision,
        created_at=document.created_at,
        updated_at=document.updated_at,
        duplicate=duplicate,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "knowledge_document_not_found", "message": "Knowledge document not found."})


def _enforce_demo_policy_upload(content: bytes) -> None:
    if not get_settings().demo_mode:
        return
    source_dir = REPO_ROOT / "data" / "demo" / "knowledge"
    try:
        sources = {source.name: source for source in source_dir.glob("*.md")}
        allowed_hashes = {
            hashlib.sha256(sources[name].read_bytes()).digest()
            for name in DEMO_POLICY_FILENAMES
            if name in sources
        }
    except OSError as exc:
        logger.exception("Committed synthetic policy files are unavailable in demo mode")
        raise HTTPException(status_code=503, detail={"code": "demo_fixture_unavailable", "message": "Synthetic policy examples are temporarily unavailable."}) from exc
    if len(allowed_hashes) != len(DEMO_POLICY_FILENAMES):
        raise HTTPException(status_code=503, detail={"code": "demo_fixture_unavailable", "message": "Synthetic policy examples are temporarily unavailable."})
    if hashlib.sha256(content).digest() not in allowed_hashes:
        raise HTTPException(
            status_code=403,
            detail={"code": "demo_upload_restricted", "message": "The public demo accepts only the six committed synthetic policy examples; custom document uploads are disabled."},
        )


def _ensure_demo_reindex_is_allowed(document: KnowledgeDocument) -> None:
    if get_settings().demo_mode:
        if document.source_filename not in DEMO_POLICY_FILENAMES or not document.title.startswith("DEMO / SYNTHETIC DATA"):
            raise HTTPException(
                status_code=403,
                detail={"code": "demo_document_management_disabled", "message": "Only the six committed synthetic policy examples can be reindexed in the public demo."},
            )
        source = REPO_ROOT / "data" / "demo" / "knowledge" / document.source_filename
        try:
            fixture = extract_document(source.name, source.read_bytes())
        except (OSError, DocumentError) as exc:
            logger.exception("Committed synthetic policy fixture is unavailable during reindex")
            raise HTTPException(status_code=503, detail={"code": "demo_fixture_unavailable", "message": "Synthetic policy examples are temporarily unavailable."}) from exc
        if fixture.content_sha256 != document.content_sha256:
            raise HTTPException(
                status_code=403,
                detail={"code": "demo_document_management_disabled", "message": "Only the six committed synthetic policy examples can be reindexed in the public demo."},
            )


def _ensure_demo_document_deletion_is_disabled() -> None:
    if get_settings().demo_mode:
        raise HTTPException(
            status_code=403,
            detail={"code": "demo_document_management_disabled", "message": "Document deletion is disabled in the public synthetic demo."},
        )


@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=202)
async def upload_knowledge_document(
    background_tasks: BackgroundTasks,
    tenant: CurrentTenant,
    db: DbSession,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=240),
) -> KnowledgeDocumentOut:
    settings = get_settings()
    content = await file.read(settings.knowledge_upload_max_bytes + 1)
    if len(content) > settings.knowledge_upload_max_bytes:
        raise HTTPException(status_code=413, detail={"code": "document_too_large", "message": f"Documents must be {settings.knowledge_upload_max_bytes // (1024 * 1024)} MB or smaller."})
    _enforce_demo_policy_upload(content)
    try:
        extracted = extract_document(file.filename, content)
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc

    existing = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant.id,
            KnowledgeDocument.content_sha256 == extracted.content_sha256,
        )
    )
    if existing is not None:
        return _document_out(existing, duplicate=True)

    if title is not None and not title.strip():
        raise HTTPException(status_code=422, detail={"code": "invalid_title", "message": "Document title cannot be blank."})
    current_version = db.scalar(
        select(func.max(KnowledgeDocument.version)).where(
            KnowledgeDocument.tenant_id == tenant.id,
            KnowledgeDocument.source_key == extracted.source_key,
        )
    ) or 0
    safe_title = title
    if settings.demo_mode:
        safe_title = f"DEMO / SYNTHETIC DATA — {title or extracted.title}"
    document = _new_document(tenant.id, extracted, safe_title, current_version + 1)
    db.add(document)
    try:
        db.commit()
        db.refresh(document)
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant.id,
                KnowledgeDocument.content_sha256 == extracted.content_sha256,
            )
        )
        if duplicate is not None:
            return _document_out(duplicate, duplicate=True)
        raise HTTPException(status_code=409, detail={"code": "document_conflict", "message": "A document version conflict occurred. Retry the upload."}) from exc

    background_tasks.add_task(index_document, document.id, tenant.id)
    return _document_out(document)


@router.post("/demo-documents", response_model=DemoKnowledgeSeedOut, status_code=202)
def add_synthetic_demo_documents(
    background_tasks: BackgroundTasks,
    tenant: CurrentTenant,
    db: DbSession,
) -> DemoKnowledgeSeedOut:
    if not tenant.is_demo:
        raise HTTPException(status_code=403, detail={"code": "demo_documents_unavailable", "message": "Synthetic policy examples can only be added to the REVIO demo workspace."})
    source_dir = REPO_ROOT / "data" / "demo" / "knowledge"
    sources = sorted(source for source in source_dir.glob("*.md") if source.name.casefold() != "readme.md")
    if not sources:
        raise HTTPException(status_code=503, detail={"code": "demo_documents_missing", "message": "Synthetic policy example files are unavailable."})
    added: list[KnowledgeDocumentOut] = []
    already_present = 0
    for source in sources:
        try:
            extracted = extract_document(source.name, source.read_bytes())
        except DocumentError as exc:
            raise HTTPException(status_code=503, detail={"code": "demo_document_invalid", "message": "A synthetic example policy could not be read."}) from exc
        duplicate = db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant.id,
                KnowledgeDocument.content_sha256 == extracted.content_sha256,
            )
        )
        if duplicate is not None:
            already_present += 1
            continue
        version = (db.scalar(select(func.max(KnowledgeDocument.version)).where(
            KnowledgeDocument.tenant_id == tenant.id,
            KnowledgeDocument.source_key == extracted.source_key,
        )) or 0) + 1
        document = _new_document(tenant.id, extracted, f"DEMO / SYNTHETIC DATA — {extracted.title}", version)
        try:
            with db.begin_nested():
                db.add(document)
                db.flush()
        except IntegrityError:
            duplicate = db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == tenant.id,
                    KnowledgeDocument.content_sha256 == extracted.content_sha256,
                )
            )
            if duplicate is not None:
                already_present += 1
                continue
            raise HTTPException(status_code=409, detail={"code": "demo_document_conflict", "message": "A synthetic policy example version conflict occurred."})
        added.append(_document_out(document))
    db.commit()
    for document in added:
        background_tasks.add_task(index_document, document.id, tenant.id)
    return DemoKnowledgeSeedOut(added=len(added), already_present=already_present, documents=added)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_knowledge_documents(tenant: CurrentTenant, db: DbSession) -> list[KnowledgeDocumentOut]:
    documents = db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant.id).order_by(KnowledgeDocument.created_at.desc())
    ).all()
    return [_document_out(document) for document in documents]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def get_knowledge_document(document_id: str, tenant: CurrentTenant, db: DbSession) -> KnowledgeDocumentOut:
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == tenant.id,
        )
    )
    if document is None:
        raise _not_found()
    return _document_out(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_knowledge_document(document_id: str, tenant: CurrentTenant, db: DbSession) -> None:
    _ensure_demo_document_deletion_is_disabled()
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == tenant.id,
        )
    )
    if document is None:
        raise _not_found()
    if document.status == "processing":
        raise HTTPException(status_code=409, detail={"code": "document_processing", "message": "Wait for document processing to finish before deleting it."})
    try:
        get_store().delete_document(tenant.id, document.id)
    except Exception as exc:
        logger.exception("Failed to remove vectors for knowledge document %s", document_id)
        raise HTTPException(status_code=503, detail={"code": "vector_store_unavailable", "message": "The knowledge index is unavailable. The document was not deleted."}) from exc
    db.delete(document)
    db.commit()
    return None


@router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocumentOut, status_code=202)
def reindex_knowledge_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    tenant: CurrentTenant,
    db: DbSession,
) -> KnowledgeDocumentOut:
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == tenant.id,
        )
    )
    if document is None:
        raise _not_found()
    _ensure_demo_reindex_is_allowed(document)
    if document.status == "processing":
        raise HTTPException(status_code=409, detail={"code": "document_processing", "message": "This document is already processing."})
    document.status = "processing"
    document.error_message = None
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    background_tasks.add_task(index_document, document.id, tenant.id)
    return _document_out(document)


@router.post("/search", response_model=KnowledgeSearchOut)
def search_knowledge(payload: KnowledgeSearchIn, tenant: CurrentTenant, db: DbSession) -> KnowledgeSearchOut:
    try:
        return retrieve_knowledge(
            db, tenant.id, payload.query, payload.top_k,
            encoder_factory=get_encoder,
            store_factory=get_store,
        )
    except QueryTooLongError as exc:
        raise HTTPException(status_code=422, detail={"code": "query_too_long", "message": str(exc)}) from exc
    except Exception as exc:
        logger.exception("Knowledge search failed for tenant %s", tenant.slug)
        raise HTTPException(status_code=503, detail={"code": "knowledge_search_unavailable", "message": "Knowledge search is temporarily unavailable."}) from exc
