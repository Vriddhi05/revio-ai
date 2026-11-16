import hashlib
import json
import platform
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core.config import get_settings


def collection_name(tenant_id: str) -> str:
    return f"tenant_{hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()[:32]}"


class ChromaKnowledgeStore:
    backend_name = "chromadb-persistent"

    def __init__(self, path: str | None = None, client=None):
        if client is None:
            import chromadb

            path = path or get_settings().knowledge_vector_path
            Path(path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=path)
        self.client = client

    def _collection(self, tenant_id: str):
        return self.client.get_or_create_collection(
            name=collection_name(tenant_id),
            metadata={"hnsw:space": "cosine", "tenant_id": tenant_id},
        )

    def upsert(self, tenant_id: str, document_id: str, chunks: list[dict], embeddings: list[list[float]], document: dict) -> None:
        collection = self._collection(tenant_id)
        # Deleting prior IDs before a stable-ID upsert makes a reindex deterministic and prunes stale chunks.
        collection.delete(where={"$and": [{"tenant_id": tenant_id}, {"document_id": document_id}]})
        if not chunks:
            return
        metadatas = []
        for chunk in chunks:
            metadata = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "title": document["title"],
                "source_filename": document["source_filename"],
                "source_reference": chunk["source_reference"],
                "version": int(document["version"]),
                "content_sha256": document["content_sha256"],
                "chunk_index": int(chunk["chunk_index"]),
                "untrusted_source": True,
                "risk_flags": json.dumps(chunk["risk_flags"], ensure_ascii=False),
            }
            if chunk["page_number"] is not None:
                metadata["page_number"] = int(chunk["page_number"])
            metadatas.append(metadata)
        collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete_document(self, tenant_id: str, document_id: str) -> None:
        self._collection(tenant_id).delete(where={"$and": [{"tenant_id": tenant_id}, {"document_id": document_id}]})

    def search(self, tenant_id: str, document_ids: list[str], query_embedding: list[float], limit: int) -> list[dict]:
        if not document_ids:
            return []
        collection = self._collection(tenant_id)
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where={"$and": [{"tenant_id": tenant_id}, {"document_id": {"$in": document_ids}}]},
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for index, text in enumerate((result.get("documents") or [[]])[0]):
            metadata = (result.get("metadatas") or [[]])[0][index] or {}
            distance = float((result.get("distances") or [[]])[0][index])
            hits.append({
                "text": text,
                "metadata": metadata,
                "distance": distance,
                "similarity": max(0.0, min(1.0, 1.0 - distance)),
            })
        return hits


class SQLiteVectorKnowledgeStore:
    """Local exact cosine vector index used where Chroma's native writers are unavailable."""

    backend_name = "sqlite-exact-cosine"

    def __init__(self, path: str | None = None):
        path = path or get_settings().knowledge_vector_path
        vector_path = Path(path)
        vector_path.mkdir(parents=True, exist_ok=True)
        self.path = str(vector_path / "knowledge-vectors.sqlite3")
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_vectors (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_vectors_tenant_document ON knowledge_vectors(tenant_id, document_id)"
            )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert(self, tenant_id: str, document_id: str, chunks: list[dict], embeddings: list[list[float]], document: dict) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("DELETE FROM knowledge_vectors WHERE tenant_id=? AND document_id=?", (tenant_id, document_id))
            rows = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                metadata = {
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "title": document["title"],
                    "source_filename": document["source_filename"],
                    "source_reference": chunk["source_reference"],
                    "version": int(document["version"]),
                    "content_sha256": document["content_sha256"],
                    "chunk_index": int(chunk["chunk_index"]),
                    "untrusted_source": True,
                    "risk_flags": json.dumps(chunk["risk_flags"], ensure_ascii=False),
                }
                if chunk["page_number"] is not None:
                    metadata["page_number"] = int(chunk["page_number"])
                vector = np.asarray(embedding, dtype="<f4")
                if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
                    raise ValueError("Embedding vectors must be finite, non-empty one-dimensional arrays.")
                rows.append((
                    chunk["id"], tenant_id, document_id, chunk["text"], vector.tobytes(),
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                ))
            connection.executemany(
                "INSERT INTO knowledge_vectors(id,tenant_id,document_id,text,embedding,metadata_json) VALUES(?,?,?,?,?,?)",
                rows,
            )

    def delete_document(self, tenant_id: str, document_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM knowledge_vectors WHERE tenant_id=? AND document_id=?",
                (tenant_id, document_id),
            )

    def count_document(self, tenant_id: str, document_id: str) -> int:
        with self._connection() as connection:
            result = connection.execute(
                "SELECT count(*) FROM knowledge_vectors WHERE tenant_id=? AND document_id=?",
                (tenant_id, document_id),
            ).fetchone()
        return int(result[0])

    def chunk_ids(self, tenant_id: str, document_id: str) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM knowledge_vectors WHERE tenant_id=? AND document_id=? ORDER BY id",
                (tenant_id, document_id),
            ).fetchall()
        return [row[0] for row in rows]

    def search(self, tenant_id: str, document_ids: list[str], query_embedding: list[float], limit: int) -> list[dict]:
        if not document_ids:
            return []
        query = np.asarray(query_embedding, dtype="<f4")
        if query.ndim != 1 or query.size == 0 or not np.isfinite(query).all():
            raise ValueError("Query embedding must be finite and one-dimensional.")
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0:
            return []
        # Always constrain the SQL query by tenant before applying document readiness filters.
        with self._connection() as connection:
            if len(document_ids) <= 900:
                placeholders = ",".join("?" for _ in document_ids)
                rows = connection.execute(
                    f"SELECT text, embedding, metadata_json FROM knowledge_vectors WHERE tenant_id=? AND document_id IN ({placeholders})",
                    [tenant_id, *document_ids],
                ).fetchall()
            else:
                ready_ids = set(document_ids)
                rows = [
                    row for row in connection.execute(
                        "SELECT text, embedding, metadata_json FROM knowledge_vectors WHERE tenant_id=?",
                        (tenant_id,),
                    ).fetchall()
                    if json.loads(row[2]).get("document_id") in ready_ids
                ]
        hits = []
        for text, vector_bytes, metadata_json in rows:
            vector = np.frombuffer(vector_bytes, dtype="<f4")
            if vector.shape != query.shape:
                continue
            norm = float(np.linalg.norm(vector))
            if norm == 0:
                continue
            score = float(np.dot(query, vector) / (query_norm * norm))
            hits.append({
                "text": text,
                "metadata": json.loads(metadata_json),
                "distance": 1.0 - score,
                "similarity": max(0.0, min(1.0, score)),
            })
        return sorted(hits, key=lambda hit: hit["similarity"], reverse=True)[:limit]


def build_knowledge_store(path: str | None = None, backend: str | None = None):
    settings = get_settings()
    backend = backend or settings.knowledge_vector_backend
    if backend == "auto":
        backend = "sqlite" if platform.system() == "Windows" else "chroma"
    if backend == "sqlite":
        return SQLiteVectorKnowledgeStore(path or settings.knowledge_vector_path)
    return ChromaKnowledgeStore(path or settings.knowledge_vector_path)


@lru_cache(maxsize=1)
def get_store() -> ChromaKnowledgeStore | SQLiteVectorKnowledgeStore:
    return build_knowledge_store()
