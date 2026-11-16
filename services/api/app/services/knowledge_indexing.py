import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import KnowledgeDocument
from app.services.knowledge_documents import chunk_pages, content_risk_flags, split_chunks_to_token_limit
from app.services.knowledge_embeddings import get_encoder
from app.services.knowledge_vectors import get_store

logger = logging.getLogger(__name__)


def index_document(document_id: str, tenant_id: str, encoder=None, store=None, session_factory=None) -> None:
    """Background task; it owns its SQL session and never receives request-scoped state."""
    settings = get_settings()
    encoder = encoder or get_encoder()
    store = store or get_store()
    session_factory = session_factory or SessionLocal
    with session_factory() as db:
        document = db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
            )
        )
        if document is None or document.status != "processing":
            return
        try:
            pages = json.loads(document.extracted_pages_json)
            chunks = chunk_pages(
                document.id,
                document.tenant_id,
                document.content_sha256,
                document.version,
                document.source_filename,
                pages,
                settings.knowledge_chunk_chars,
                settings.knowledge_chunk_overlap,
            )
            tokenizer = getattr(encoder, "tokenizer", None)
            if tokenizer is not None:
                chunks = split_chunks_to_token_limit(
                    chunks,
                    tokenizer,
                    settings.knowledge_chunk_max_tokens,
                    settings.knowledge_chunk_token_overlap,
                )
            if not chunks:
                raise ValueError("No indexable text chunks were created.")
            for chunk in chunks:
                chunk["risk_flags"] = content_risk_flags(chunk["text"])
            vectors = encoder.embed_passages([chunk["text"] for chunk in chunks])
            store.upsert(
                document.tenant_id,
                document.id,
                chunks,
                vectors,
                {
                    "title": document.title,
                    "source_filename": document.source_filename,
                    "version": document.version,
                    "content_sha256": document.content_sha256,
                },
            )
            prior_versions = db.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.source_key == document.source_key,
                    KnowledgeDocument.id != document.id,
                    KnowledgeDocument.status == "ready",
                )
            ).all()
            for prior in prior_versions:
                prior.status = "superseded"
            document.status = "ready"
            document.error_message = None
            document.chunk_count = len(chunks)
            document.embedding_model = encoder.model_name
            document.embedding_revision = encoder.revision
            document.chunking_version = f"chars-{settings.knowledge_chunk_chars}-{settings.knowledge_chunk_overlap}-tokens-{settings.knowledge_chunk_max_tokens}-{settings.knowledge_chunk_token_overlap}-v1"
            document.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception("Knowledge indexing failed for tenant-scoped document %s", document_id)
            failed = db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.tenant_id == tenant_id,
                )
            )
            if failed is not None:
                failed.status = "failed"
                failed.error_message = _safe_error(exc)
                failed.updated_at = datetime.now(timezone.utc)
                db.commit()


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "The document could not be indexed. Check the file and try reindexing."
    return message[:500]
