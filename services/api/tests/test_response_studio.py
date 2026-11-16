import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import KnowledgeDocument, Location, ResponseAuditEvent, ResponseDraft, Review, Tenant
from app.services.knowledge_vectors import SQLiteVectorKnowledgeStore
from app.services.review_csv import parse_review_csv
from app.services.response_workflow import validate_response_text


class FakeEncoder:
    def embed_query(self, _text):
        return [1.0, 0.0]


@pytest.fixture
def response_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with Session() as db:
        demo = Tenant(name="Revio Demo", slug="revio-demo", is_demo=True)
        other = Tenant(name="Separate workspace", slug="separate-workspace", is_demo=False)
        db.add_all([demo, other])
        db.flush()
        review_fixture = next(
            row for row in parse_review_csv((Path(__file__).resolve().parents[3] / "data" / "demo" / "reviews.csv").read_bytes()).rows
            if "phonepe" in row.review_text.casefold() and "refund" in row.review_text.casefold()
        )
        jaipur = Location(tenant_id=demo.id, name=review_fixture.location, normalized_name=" ".join(review_fixture.location.casefold().split()))
        other_location = Location(tenant_id=other.id, name="Chandigarh, India", normalized_name="chandigarh india")
        db.add_all([jaipur, other_location])
        db.flush()
        review = Review(
            tenant_id=demo.id, location_id=jaipur.id,
            review_text=review_fixture.review_text,
            rating=review_fixture.rating, author_name=review_fixture.author_name, review_date=review_fixture.review_date,
            source_name=review_fixture.source, external_review_id=review_fixture.external_review_id,
            dedupe_key=review_fixture.dedupe_key,
            status="new", priority="normal", is_synthetic=review_fixture.is_synthetic, ingestion_source="demo_csv",
        )
        foreign_review = Review(
            tenant_id=other.id, location_id=other_location.id, review_text="Private workspace review.",
            rating=3, author_name="Gurpreet Kaur", review_date=None, source_name="DEMO fixture",
            external_review_id=None, dedupe_key=hashlib.sha256(b"foreign-review").hexdigest(),
            status="new", priority="normal", is_synthetic=True, ingestion_source="demo_csv",
        )
        db.add_all([review, foreign_review])
        db.commit()
        db.refresh(review)
        db.refresh(foreign_review)
        result = {"review_id": review.id, "foreign_review_id": foreign_review.id, "tenant_id": demo.id}

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, Session, result
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def seed_policy_index(Session, tenant_id, store):
    with Session() as db:
        document = KnowledgeDocument(
            tenant_id=tenant_id,
            title="DEMO / SYNTHETIC DATA — UPI payment support policy",
            source_filename="upi-refunds.md",
            source_key="upi-refunds.md",
            media_type="text/markdown",
            file_size_bytes=180,
            content_sha256="a" * 64,
            version=1,
            page_count=None,
            extracted_chars=120,
            extracted_pages_json=json.dumps([{"page_number": None, "text": "Please share your UTR through the verified support channel. Never post payment references publicly."}]),
            status="ready",
            chunk_count=1,
            embedding_model="test/fake-multilingual",
            embedding_revision="test-v1",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
    store.upsert(
        tenant_id,
        document_id,
        [{"id": "upi-policy-chunk", "text": "Please share your UTR through the verified support channel. Never post payment references publicly.", "page_number": None, "chunk_index": 0, "source_reference": "upi-refunds.md", "risk_flags": []}],
        [[1.0, 0.0]],
        {"title": "DEMO / SYNTHETIC DATA — UPI payment support policy", "source_filename": "upi-refunds.md", "version": 1, "content_sha256": "a" * 64},
    )


def test_phonepe_review_runs_langgraph_edit_approve_and_audit(response_client, monkeypatch, tmp_path):
    import app.services.knowledge_retrieval as retrieval
    import app.services.response_workflow as workflow

    client, Session, data = response_client
    vector_store = SQLiteVectorKnowledgeStore(str(tmp_path / "vectors"))
    seed_policy_index(Session, data["tenant_id"], vector_store)
    monkeypatch.setattr(retrieval, "get_store", lambda: vector_store)
    monkeypatch.setattr(retrieval, "get_encoder", FakeEncoder)
    monkeypatch.setattr(workflow, "get_settings", lambda: SimpleNamespace(
        response_llm_provider="demo", response_llm_api_key=None,
    ))

    created = client.post(f"/api/v1/reviews/{data['review_id']}/responses/generate", json={})
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["generation_provider"] == "demo_fallback"
    assert draft["analysis"]["sentiment"] in {"positive", "neutral", "negative"}
    assert draft["analysis"]["categories"]
    assert draft["analysis"]["severity"] in {"low", "medium", "high", "critical"}
    assert len(draft["workflow_trace"]) == 6
    assert all(step["status"] == "completed" for step in draft["workflow_trace"])
    assert draft["workflow_trace"][0]["node"] == "load_review"
    assert draft["workflow_trace"][-1]["node"] == "save_draft"
    assert draft["citations"][0]["source_reference"] == "upi-refunds.md"
    assert draft["citations"][0]["untrusted_source"] is True
    assert "timeline" in draft["response_text"].lower()

    edited = client.patch(f"/api/v1/responses/{draft['id']}", json={"response_text": "We appreciate you sharing this concern. Please contact our verified support channel privately so the team can review the payment reference."})
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "edited"
    approved = client.post(f"/api/v1/responses/{draft['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"]
    audit = client.get(f"/api/v1/responses/{draft['id']}/audit")
    assert audit.status_code == 200
    assert [event["action"] for event in audit.json()] == ["generated", "edited", "approved"]
    assert client.get(f"/api/v1/reviews/{data['review_id']}/responses").json()[0]["id"] == draft["id"]
    with Session() as db:
        assert db.scalar(select(ResponseDraft).where(ResponseDraft.id == draft["id"])).status == "approved"
        assert len(db.scalars(select(ResponseAuditEvent).where(ResponseAuditEvent.draft_id == draft["id"])).all()) == 3


def test_response_drafts_and_reviews_are_tenant_scoped(response_client):
    client, _, data = response_client
    missing = client.post(f"/api/v1/reviews/{data['foreign_review_id']}/responses/generate", json={})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "review_not_found"
    draft = client.post(f"/api/v1/reviews/{data['review_id']}/responses/generate", json={}).json()
    other_headers = {"X-Tenant-Slug": "separate-workspace"}
    assert client.get(f"/api/v1/responses/{draft['id']}", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/responses/{draft['id']}/audit", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/reviews/{data['foreign_review_id']}/responses", headers={"X-Tenant-Slug": "revio-demo"}).status_code == 404


def test_response_without_policy_evidence_abstains_and_has_no_citations(response_client, monkeypatch):
    import app.services.response_workflow as workflow

    client, _, data = response_client
    monkeypatch.setattr(workflow, "get_settings", lambda: SimpleNamespace(response_llm_provider="demo", response_llm_api_key=None))
    response = client.post(f"/api/v1/reviews/{data['review_id']}/responses/generate", json={})
    assert response.status_code == 201
    draft = response.json()
    assert draft["citations"] == []
    assert draft["workflow_trace"][2]["status"] == "completed"
    assert "timeline" in draft["response_text"].lower()
    assert "verified support channel" in draft["response_text"].lower()


def test_guardrail_flags_unsupported_amounts_timelines_and_promises():
    blockers = validate_response_text("We will refund ₹1,200 within 2 days.", "Our policy asks customers to contact support with a UTR.")
    assert "unsupported_amount" in blockers
    assert "unsupported_timeline" in blockers
    assert "unsupported_commitment" in blockers


def test_configured_hosted_provider_and_high_risk_escalation(monkeypatch):
    import app.services.response_workflow as workflow

    captured = {}

    class ProviderResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "We are sorry this happened. Please contact our verified support channel privately so the team can review the details."}}]}

    monkeypatch.setattr(workflow, "get_settings", lambda: SimpleNamespace(
        response_llm_provider="openai_compatible",
        response_llm_api_key="unit-test-placeholder",
        response_llm_base_url="https://provider.example/v1",
        response_llm_model="configured-model",
        response_llm_timeout_seconds=5,
    ))

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json, timeout=timeout)
        return ProviderResponse()

    monkeypatch.setattr(workflow.httpx, "post", fake_post)
    state = {
        "review": {"review_text": "PhonePe payment issue", "rating": 1},
        "analysis": {"language": "English", "severity": "critical"},
        "citations": [{"document_title": "Synthetic policy", "source_reference": "policy.md", "passage": "Use verified support."}],
    }
    generated = workflow._generate_response(state)
    assert generated["generation_provider"] == "openai_compatible"
    assert generated["generation_model"] == "configured-model"
    assert generated["needs_human_escalation"] is True
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer unit-test-placeholder"
    assert "policy_evidence_untrusted" in captured["body"]["messages"][1]["content"]
    assert "Do not claim the issue has been escalated" in captured["body"]["messages"][0]["content"]


def test_demo_draft_matches_hinglish_and_hindi_scripts(monkeypatch):
    import app.services.response_workflow as workflow

    hinglish = workflow._safe_demo_draft("Hinglish", "low")
    hindi = workflow._safe_demo_draft("Hindi", "low")
    critical = workflow._safe_demo_draft("English", "critical")
    assert "dhanyavaad" in hinglish.casefold()
    assert "धन्यवाद" in hindi
    assert "careful attention" in critical
    assert "has been escalated" not in critical.casefold()


def test_response_state_transitions_are_enforced(response_client):
    client, _, data = response_client
    draft = client.post(f"/api/v1/reviews/{data['review_id']}/responses/generate", json={}).json()
    approved = client.post(f"/api/v1/responses/{draft['id']}/approve", json={})
    assert approved.status_code == 200
    blocked = client.patch(f"/api/v1/responses/{draft['id']}", json={"response_text": "This edit should not overwrite an approved response."})
    assert blocked.status_code == 409
