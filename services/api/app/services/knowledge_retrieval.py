import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import KnowledgeDocument
from app.schemas.knowledge import KnowledgeSearchHit, KnowledgeSearchOut
from app.services.knowledge_embeddings import QueryTooLongError, get_encoder
from app.services.knowledge_vectors import get_store


def retrieve_knowledge(
    db: Session,
    tenant_id: str,
    query: str,
    top_k: int = 5,
    *,
    encoder_factory=None,
    store_factory=None,
) -> KnowledgeSearchOut:
    """Run the shared tenant-scoped semantic retrieval path used by API and agents."""
    settings = get_settings()
    ready_ids = db.scalars(
        select(KnowledgeDocument.id).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status == "ready",
        )
    ).all()
    metadata = {
        "embedding_model": settings.knowledge_embedding_model,
        "embedding_revision": settings.knowledge_embedding_revision,
        "similarity_metric": "cosine similarity (1 - cosine distance)",
        "tenant_filter_enforced": True,
        "minimum_similarity": settings.knowledge_min_similarity,
        "untrusted_source_handling": "Retrieved text is untrusted evidence; heuristic flags are advisory.",
    }
    if not ready_ids:
        return KnowledgeSearchOut(
            query=query, results=[], abstained=True,
            abstention_reason="No processed knowledge documents are available in this workspace.",
            retrieval_metadata={**metadata, "candidate_count": 0},
        )

    encoder = (encoder_factory or get_encoder)()
    query_vector = encoder.embed_query(query)
    store = (store_factory or get_store)()
    raw_hits = store.search(tenant_id, list(ready_ids), query_vector, top_k)
    metadata["vector_store_backend"] = getattr(store, "backend_name", "chromadb-persistent")
    threshold = settings.knowledge_min_similarity
    hits = [hit for hit in raw_hits if hit["similarity"] >= threshold]
    results = []
    for hit in hits:
        source = hit["metadata"]
        try:
            risk_flags = json.loads(source.get("risk_flags") or "[]")
        except (TypeError, json.JSONDecodeError):
            risk_flags = []
        results.append(KnowledgeSearchHit(
            passage=hit["text"],
            document_id=source["document_id"],
            document_title=source["title"],
            source_filename=source["source_filename"],
            source_reference=source["source_reference"],
            page_number=source.get("page_number"),
            similarity_score=round(hit["similarity"], 5),
            retrieval_metadata={
                "cosine_distance": round(hit["distance"], 5),
                "document_version": source["version"],
                "chunk_index": source["chunk_index"],
                "content_sha256": source["content_sha256"],
                "untrusted_source": True,
                "risk_flags": risk_flags,
            },
        ))
    return KnowledgeSearchOut(
        query=query,
        results=results,
        abstained=not results,
        abstention_reason="No passage met the configured relevance threshold; no evidence is available for this query." if not results else None,
        retrieval_metadata={**metadata, "candidate_count": len(raw_hits), "returned_count": len(results)},
    )


__all__ = ["QueryTooLongError", "retrieve_knowledge"]
