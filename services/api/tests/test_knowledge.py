import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.config import Settings
from app.db.base import Base
from app.db.init_db import recover_interrupted_knowledge_documents
from app.main import app
from app.models import KnowledgeDocument, Tenant
from app.services.knowledge_documents import DocumentError, chunk_pages, extract_document, safe_filename, split_chunks_to_token_limit, split_text
from app.services.knowledge_indexing import index_document
from app.services.knowledge_vectors import SQLiteVectorKnowledgeStore


class FakeEncoder:
    model_name = "test/fake-multilingual"
    revision = "test-v1"

    def embed_passages(self, texts):
        return [[1.0, 0.0] if "upi" in text.casefold() or "refund" in text.casefold() else [0.0, 1.0] for text in texts]

    def embed_query(self, text):
        return [0.0, 1.0] if "unrelated" in text.casefold() else [1.0, 0.0]


class SimpleTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.strip().split()

    def num_special_tokens_to_add(self, pair=False):
        return 2

    def decode(self, tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False):
        return " ".join(tokens)


def make_text_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


@pytest.fixture
def kb_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    with TestSession() as db:
        db.add_all([
            Tenant(name="Revio Demo", slug="revio-demo", is_demo=True),
            Tenant(name="Other workspace", slug="separate-workspace", is_demo=False),
        ])
        db.commit()

    def override_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, TestSession
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def add_document(TestSession, tenant_slug="revio-demo", status="ready", filename="upi-refunds.md"):
    with TestSession() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        doc = KnowledgeDocument(
            tenant_id=tenant.id,
            title="DEMO / SYNTHETIC DATA — UPI refund guide",
            source_filename=filename,
            source_key=filename.casefold(),
            media_type="text/markdown",
            file_size_bytes=210,
            content_sha256=("a" if tenant_slug == "revio-demo" else "b") * 64,
            version=1,
            page_count=None,
            extracted_chars=85,
            extracted_pages_json=json.dumps([{"page_number": None, "text": "UPI refund reference and refund timeline for Indian customers."}]),
            status=status,
            chunk_count=1 if status == "ready" else 0,
            embedding_model="test/fake-multilingual",
            embedding_revision="test-v1",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return tenant.id, doc.id


def make_store(tmp_path, name="vectors"):
    return SQLiteVectorKnowledgeStore(str(tmp_path / name))


def test_file_validation_normalization_and_filename_safety() -> None:
    extracted = extract_document("..\\private\\upi-guide.md", b"# UPI\r\n\r\n PhonePe refund guide. \t\r\n")
    assert extracted.filename == "upi-guide.md"
    assert extracted.title == "upi-guide"
    assert extracted.pages[0]["text"] == "# UPI\n\nPhonePe refund guide."
    assert len(extracted.content_sha256) == 64
    assert safe_filename("../../notes.txt") == "notes.txt"
    with pytest.raises(DocumentError, match="Supported document types"):
        extract_document("policy.docx", b"content")
    with pytest.raises(DocumentError, match="empty"):
        extract_document("empty.txt", b"")
    with pytest.raises(DocumentError, match="UTF-8"):
        extract_document("wrong-encoding.txt", b"\xff\xfe")


def test_pdf_extractable_text_and_scanned_pdf_rejection() -> None:
    extracted = extract_document("policy.pdf", make_text_pdf("UPI refund process for Jaipur customers"))
    assert extracted.media_type == "application/pdf"
    assert extracted.pages[0]["page_number"] == 1
    assert "UPI refund" in extracted.pages[0]["text"]
    with pytest.raises(DocumentError, match="not a valid PDF"):
        extract_document("fake.pdf", b"not a pdf")
    with pytest.raises(DocumentError, match="Scanned PDFs require OCR"):
        extract_document("scanned.pdf", make_text_pdf(""))


def test_chunking_overlap_and_stable_source_ids() -> None:
    text = "UPI refund rules: " + "customer must share the UTR number. " * 25
    chunks = split_text(text, max_chars=120, overlap=24)
    assert len(chunks) > 2
    assert all(chunk and len(chunk) <= 122 for chunk in chunks)
    pages = [{"page_number": 3, "text": text}]
    first = chunk_pages("doc-1", "tenant-1", "hash", 2, "guide.pdf", pages, 120, 24)
    second = chunk_pages("doc-1", "tenant-1", "hash", 2, "guide.pdf", pages, 120, 24)
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert first[0]["source_reference"] == "guide.pdf · p. 3"
    assert all(row["page_number"] == 3 for row in first)


def test_token_limit_splitting_prevents_embedding_truncation() -> None:
    original = {"id": "base-id", "text": "one two three four five six seven eight nine ten eleven twelve", "page_number": 1, "chunk_index": 0, "source_reference": "faq.pdf p. 1"}
    chunks = split_chunks_to_token_limit([original], SimpleTokenizer(), max_tokens=9, overlap_tokens=2)
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 9 for chunk in chunks)
    assert chunks[0]["text"].split()[-2:] == chunks[1]["text"].split()[:2]
    assert [chunk["id"] for chunk in chunks] == [chunk["id"] for chunk in split_chunks_to_token_limit([original], SimpleTokenizer(), 9, 2)]


def test_upload_duplicate_and_document_tenant_listing(kb_client, monkeypatch) -> None:
    client, _ = kb_client
    monkeypatch.setattr("app.api.v1.knowledge.index_document", lambda *_args, **_kwargs: None)
    content = b"# Refunds\nPhonePe UPI refunds are checked against the UTR."
    first = client.post("/api/v1/knowledge/documents", files={"file": ("upi.md", content, "text/markdown")})
    second = client.post("/api/v1/knowledge/documents", files={"file": ("upi-copy.md", content, "text/markdown")})
    other = client.get("/api/v1/knowledge/documents", headers={"X-Tenant-Slug": "separate-workspace"})
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]
    assert len(other.json()) == 0


def test_upload_validation_error_is_consistent(kb_client) -> None:
    client, _ = kb_client
    response = client.post("/api/v1/knowledge/documents", files={"file": ("notes.csv", b"content", "text/csv")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_search_returns_source_metadata_and_never_crosses_tenants(kb_client, monkeypatch, tmp_path) -> None:
    client, TestSession = kb_client
    tenant_id, document_id = add_document(TestSession)
    store = make_store(tmp_path)
    store.upsert(
        tenant_id,
        document_id,
        [{"id": "upi-chunk", "text": "UPI refund is checked using the UTR reference.", "page_number": 2, "chunk_index": 0, "source_reference": "upi-refunds.pdf · p. 2", "risk_flags": []}],
        [[1.0, 0.0]],
        {"title": "DEMO / SYNTHETIC DATA — UPI refunds", "source_filename": "upi-refunds.pdf", "version": 1, "content_sha256": "a" * 64},
    )
    monkeypatch.setattr("app.api.v1.knowledge.get_store", lambda: store)
    monkeypatch.setattr("app.api.v1.knowledge.get_encoder", FakeEncoder)
    result = client.post("/api/v1/knowledge/search", json={"query": "How does a UPI refund work?"}).json()
    isolated = client.post("/api/v1/knowledge/search", json={"query": "How does a UPI refund work?"}, headers={"X-Tenant-Slug": "separate-workspace"}).json()
    assert result["abstained"] is False
    assert result["results"][0]["passage"].startswith("UPI refund")
    assert result["results"][0]["document_title"].startswith("DEMO / SYNTHETIC DATA")
    assert result["results"][0]["page_number"] == 2
    assert result["results"][0]["source_reference"] == "upi-refunds.pdf · p. 2"
    assert result["results"][0]["retrieval_metadata"]["untrusted_source"] is True
    assert isolated["abstained"] is True
    assert isolated["results"] == []


def test_search_abstains_for_empty_and_low_relevance_results(kb_client, monkeypatch, tmp_path) -> None:
    client, TestSession = kb_client
    tenant_id, document_id = add_document(TestSession, status="processing")
    empty = client.post("/api/v1/knowledge/search", json={"query": "UPI refund?"}).json()
    assert empty["abstained"] is True
    assert empty["results"] == []
    with TestSession() as db:
        db.get(KnowledgeDocument, document_id).status = "ready"
        db.commit()

    store = make_store(tmp_path)
    store.upsert(
        tenant_id,
        document_id,
        [{"id": "upi-chunk", "text": "UPI refunds use UTR references.", "page_number": None, "chunk_index": 0, "source_reference": "upi-refunds.md", "risk_flags": []}],
        [[1.0, 0.0]],
        {"title": "UPI refunds", "source_filename": "upi-refunds.md", "version": 1, "content_sha256": "a" * 64},
    )
    monkeypatch.setattr("app.api.v1.knowledge.get_store", lambda: store)
    monkeypatch.setattr("app.api.v1.knowledge.get_encoder", FakeEncoder)
    response = client.post("/api/v1/knowledge/search", json={"query": "unrelated space question"}).json()
    assert response["abstained"] is True
    assert response["results"] == []
    assert response["abstention_reason"]


def test_delete_is_tenant_scoped_and_removes_vectors(kb_client, monkeypatch, tmp_path) -> None:
    client, TestSession = kb_client
    tenant_id, document_id = add_document(TestSession)
    store = make_store(tmp_path)
    store.upsert(
        tenant_id,
        document_id,
        [{"id": "delete-me", "text": "UPI refund", "page_number": None, "chunk_index": 0, "source_reference": "policy.md", "risk_flags": []}],
        [[1.0, 0.0]],
        {"title": "UPI", "source_filename": "policy.md", "version": 1, "content_sha256": "a" * 64},
    )
    monkeypatch.setattr("app.api.v1.knowledge.get_store", lambda: store)
    wrong_tenant = client.delete(f"/api/v1/knowledge/documents/{document_id}", headers={"X-Tenant-Slug": "separate-workspace"})
    deleted = client.delete(f"/api/v1/knowledge/documents/{document_id}")
    assert wrong_tenant.status_code == 404
    assert deleted.status_code == 204
    assert store.count_document(tenant_id, document_id) == 0


def test_reindex_is_idempotent_and_preserves_metadata(kb_client, tmp_path) -> None:
    _, TestSession = kb_client
    tenant_id, document_id = add_document(TestSession, status="processing")
    store = make_store(tmp_path)
    encoder = FakeEncoder()
    index_document(document_id, tenant_id, encoder, store, TestSession)
    with TestSession() as db:
        document = db.get(KnowledgeDocument, document_id)
        assert document.status == "ready"
        assert document.chunk_count > 0
        first_ids = store.chunk_ids(tenant_id, document_id)
    index_document(document_id, tenant_id, encoder, store, TestSession)
    with TestSession() as db:
        document = db.get(KnowledgeDocument, document_id)
        second_ids = store.chunk_ids(tenant_id, document_id)
        assert document.status == "ready"
        assert document.chunk_count == len(first_ids)
        assert sorted(first_ids) == sorted(second_ids)


def test_vector_index_persists_across_store_instances_and_is_tenant_scoped(tmp_path) -> None:
    path = str(tmp_path / "persistent")
    first = SQLiteVectorKnowledgeStore(path)
    first.upsert(
        "tenant-one",
        "doc-1",
        [{"id": "chunk-1", "text": "UPI refunds", "page_number": None, "chunk_index": 0, "source_reference": "refunds.md", "risk_flags": []}],
        [[1.0, 0.0]],
        {"title": "UPI refunds", "source_filename": "refunds.md", "version": 1, "content_sha256": "x"},
    )
    reopened = SQLiteVectorKnowledgeStore(path)
    assert len(reopened.search("tenant-one", ["doc-1"], [1.0, 0.0], 1)) == 1
    assert reopened.search("tenant-two", ["doc-1"], [1.0, 0.0], 1) == []


def test_interrupted_indexing_job_is_recoverable(kb_client) -> None:
    _, TestSession = kb_client
    _, document_id = add_document(TestSession, status="processing")
    with TestSession() as db:
        assert recover_interrupted_knowledge_documents(db) == 1
    with TestSession() as db:
        document = db.get(KnowledgeDocument, document_id)
        assert document.status == "failed"
        assert "Reindex to retry" in document.error_message


def test_demo_policy_seed_is_idempotent_and_restricted_to_demo_tenant(kb_client, monkeypatch) -> None:
    client, _ = kb_client
    monkeypatch.setattr("app.api.v1.knowledge.index_document", lambda *_args, **_kwargs: None)
    first = client.post("/api/v1/knowledge/demo-documents")
    second = client.post("/api/v1/knowledge/demo-documents")
    other = client.post("/api/v1/knowledge/demo-documents", headers={"X-Tenant-Slug": "separate-workspace"})
    assert first.status_code == 202
    assert first.json()["added"] == 6
    assert second.json()["added"] == 0
    assert second.json()["already_present"] == 6
    assert all(document["title"].startswith("DEMO / SYNTHETIC DATA") for document in first.json()["documents"])
    assert other.status_code == 403


def test_demo_mode_accepts_only_committed_synthetic_policy_documents(kb_client, monkeypatch) -> None:
    client, _ = kb_client
    monkeypatch.setattr("app.api.v1.knowledge.get_settings", lambda: Settings(app_env="demo"))
    monkeypatch.setattr("app.api.v1.knowledge.index_document", lambda *_args, **_kwargs: None)
    arbitrary = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("private-policy.md", b"A private policy supplied by an anonymous user.", "text/markdown")},
    )
    sample_path = Path(__file__).resolve().parents[3] / "data" / "demo" / "knowledge" / "upi-refunds.md"
    sample = client.post(
        "/api/v1/knowledge/documents",
        files={"file": (sample_path.name, sample_path.read_bytes(), "text/markdown")},
    )

    assert arbitrary.status_code == 403
    assert arbitrary.json()["error"]["code"] == "demo_upload_restricted"
    assert sample.status_code == 202
    assert sample.json()["source_filename"] == "upi-refunds.md"
    assert sample.json()["title"].startswith("DEMO / SYNTHETIC DATA")


def test_demo_mode_allows_only_committed_fixture_reindex_and_blocks_delete(kb_client, monkeypatch) -> None:
    client, TestSession = kb_client
    monkeypatch.setattr("app.api.v1.knowledge.get_settings", lambda: Settings(app_env="demo"))
    monkeypatch.setattr("app.api.v1.knowledge.index_document", lambda *_args, **_kwargs: None)
    seeded = client.post("/api/v1/knowledge/demo-documents", json={})
    assert seeded.status_code == 202
    seeded_documents = client.get("/api/v1/knowledge/documents").json()
    fixture = next(item for item in seeded_documents if item["source_filename"] == "upi-refunds.md")
    _, arbitrary_id = add_document(TestSession, filename="private-policy.md")
    with TestSession() as db:
        failed_fixture = db.get(KnowledgeDocument, fixture["id"])
        failed_fixture.status = "failed"
        db.commit()

    deleted = client.delete(f"/api/v1/knowledge/documents/{fixture['id']}")
    fixture_reindex = client.post(f"/api/v1/knowledge/documents/{fixture['id']}/reindex")
    arbitrary_reindex = client.post(f"/api/v1/knowledge/documents/{arbitrary_id}/reindex")

    assert deleted.status_code == 403
    assert fixture_reindex.status_code == 202
    assert fixture_reindex.json()["status"] == "processing"
    assert arbitrary_reindex.status_code == 403
    assert deleted.json()["error"]["code"] == "demo_document_management_disabled"
    assert arbitrary_reindex.json()["error"]["code"] == "demo_document_management_disabled"
