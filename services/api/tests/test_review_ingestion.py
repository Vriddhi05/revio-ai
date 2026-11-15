import csv
import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Tenant


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    with TestSession() as db:
        db.add_all(
            [
                Tenant(name="Revio Test", slug="revio-demo", is_demo=True),
                Tenant(name="Separate Workspace", slug="separate-workspace", is_demo=False),
            ]
        )
        db.commit()

    def override_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        test_engine.dispose()


def make_csv(rows: list[dict[str, str]], headers: list[str] | None = None) -> bytes:
    columns = headers or [
        "review_text", "rating", "author_name", "review_date", "location", "source", "external_review_id", "is_synthetic"
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def row(
    text: str = "The chai and poha were fresh; staff packed my takeaway quickly.",
    rating: str = "5",
    external_id: str = "R-1",
    location: str = "Jaipur, Rajasthan, India",
    review_date: str = "2026-11-14",
    author: str = "Aditi Sharma",
    synthetic: str = "true",
) -> dict[str, str]:
    return {
        "review_text": text,
        "rating": rating,
        "author_name": author,
        "review_date": review_date,
        "location": location,
        "source": "Google Maps",
        "external_review_id": external_id,
        "is_synthetic": synthetic,
    }


def upload(client: TestClient, content: bytes, endpoint: str = "/api/v1/reviews/imports", tenant: str = "revio-demo"):
    return client.post(
        endpoint,
        files={"file": ("reviews.csv", content, "text/csv")},
        headers={"X-Tenant-Slug": tenant},
    )


def test_preview_reports_invalid_rows_and_required_columns(client: TestClient) -> None:
    content = make_csv([row(), row(text="", rating="0", external_id="R-2")])
    response = upload(client, content, "/api/v1/reviews/imports/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 2
    assert body["accepted_rows"] == 1
    assert body["rejected_rows"] == 1
    assert body["preview_rows"][0]["is_synthetic"] is True
    assert {issue["code"] for issue in body["preview_rows"][1]["issues"]} == {
        "missing_review_text", "invalid_rating"
    }
    assert {issue["code"] for issue in body["issue_summary"]} == {"missing_review_text", "invalid_rating"}

    missing = upload(client, make_csv([], headers=["author_name", "review_date"]), "/api/v1/reviews/imports/preview")
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "missing_columns"


@pytest.mark.parametrize("rating", ["0", "5.5", "NaN", "bad", "4.2"])
def test_invalid_ratings_are_rejected(client: TestClient, rating: str) -> None:
    response = upload(client, make_csv([row(rating=rating)]), "/api/v1/reviews/imports/preview")
    assert response.status_code == 200
    assert response.json()["accepted_rows"] == 0
    assert response.json()["preview_rows"][0]["issues"][0]["code"] == "invalid_rating"


def test_malformed_csv_returns_consistent_validation_error(client: TestClient) -> None:
    response = upload(client, b'review_text,rating\n"unterminated,5\n', "/api/v1/reviews/imports/preview")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "malformed_csv"


def test_fictional_sample_csv_is_downloadable(client: TestClient) -> None:
    response = client.get("/api/v1/demo/reviews.csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 45
    assert {row["location"] for row in rows} == {
        "Jaipur, Rajasthan, India",
        "Chandigarh, India",
        "Ludhiana, Punjab, India",
    }
    assert all(row["is_synthetic"] == "true" for row in rows)
    assert len({row["author_name"] for row in rows}) == 45
    assert {int(row["rating"]) for row in rows} == {1, 2, 3, 4, 5}
    assert any(any("\u0900" <= char <= "\u097f" for char in row["review_text"]) for row in rows)
    assert any("kaafi badiya" in row["review_text"].casefold() for row in rows)


def test_import_is_persistent_and_idempotent(client: TestClient) -> None:
    content = make_csv([
        row(synthetic="false"),
        row(external_id="R-2", text="Swiggy order from Pink City Thali arrived late and cold.", rating="2", synthetic="false"),
    ])
    first = upload(client, content)
    second = upload(client, content)

    assert first.status_code == 201
    assert first.json()["accepted_rows"] == 2
    assert first.json()["rejected_rows"] == 0
    assert second.status_code == 201
    assert second.json()["accepted_rows"] == 0
    assert second.json()["rejected_rows"] == 2

    listing = client.get("/api/v1/reviews", params={"page": 1, "page_size": 10})
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert {item["status"] for item in listing.json()["items"]} == {"new", "needs_attention"}
    assert listing.json()["items"][0]["import_metadata"]["record_origin"] == "CSV import"

    job = client.get(f"/api/v1/reviews/imports/{first.json()['id']}")
    assert job.status_code == 200
    assert job.json()["accepted_rows"] == 2


def test_duplicate_fingerprint_prevents_repeat_without_external_id(client: TestClient) -> None:
    first = row(external_id="")
    duplicate = {**first}
    assert upload(client, make_csv([first])).json()["accepted_rows"] == 1
    repeated = upload(client, make_csv([duplicate]))
    assert repeated.json()["accepted_rows"] == 0
    assert repeated.json()["errors"][0]["code"] == "duplicate_review"


def test_import_counts_invalid_rows_and_in_file_duplicates(client: TestClient) -> None:
    accepted = row(external_id="COUNT-1")
    invalid = row(text="Jaipur cafe review with an invalid rating.", rating="6", external_id="COUNT-2")
    response = upload(client, make_csv([accepted, invalid, accepted]))

    assert response.status_code == 201
    assert response.json()["accepted_rows"] == 1
    assert response.json()["rejected_rows"] == 2
    assert {issue["code"] for issue in response.json()["errors"]} == {"invalid_rating", "duplicate_in_file"}
    assert client.get("/api/v1/reviews").json()["total"] == 1


def test_preview_handles_more_rows_than_sqlite_parameter_limit(client: TestClient) -> None:
    rows = [row(text=f"Fictional Jaipur cafe review {index}", external_id=f"BULK-{index}") for index in range(1100)]
    response = upload(client, make_csv(rows), "/api/v1/reviews/imports/preview")
    assert response.status_code == 200
    assert response.json()["total_rows"] == 1100
    assert response.json()["accepted_rows"] == 1100


def test_tenant_isolation_for_reviews_and_detail(client: TestClient) -> None:
    imported = upload(client, make_csv([row()]), tenant="separate-workspace")
    review_id = client.get("/api/v1/reviews", headers={"X-Tenant-Slug": "separate-workspace"}).json()["items"][0]["id"]

    demo_list = client.get("/api/v1/reviews", headers={"X-Tenant-Slug": "revio-demo"})
    hidden_detail = client.get(f"/api/v1/reviews/{review_id}", headers={"X-Tenant-Slug": "revio-demo"})
    other_list = client.get("/api/v1/reviews", headers={"X-Tenant-Slug": "separate-workspace"})

    assert imported.status_code == 201
    assert demo_list.json()["total"] == 0
    assert hidden_detail.status_code == 404
    assert other_list.json()["total"] == 1


def test_review_pagination_filtering_and_status(client: TestClient) -> None:
    rows = [
        row(text="Masala chai arrived fast and staff were kind.", rating="5", external_id="P-1", location="Jaipur, Rajasthan, India", review_date="2026-11-10"),
        row(text="Cold coffee after a long wait at peak hour.", rating="2", external_id="P-2", location="Jaipur, Rajasthan, India", review_date="2026-11-11"),
        row(text="Good filter coffee and a kind team.", rating="4", external_id="P-3", location="Chandigarh, India", review_date="2026-11-12"),
        row(text="Service was slow, but the samosa puff was good.", rating="3", external_id="P-4", location="Chandigarh, India", review_date="2026-11-13"),
        row(text="A quiet table and excellent masala chai.", rating="5", external_id="P-5", location="Jaipur, Rajasthan, India", review_date="2026-11-14"),
    ]
    upload(client, make_csv(rows))
    locations = client.get("/api/v1/locations").json()
    jaipur_id = next(location["id"] for location in locations if location["name"] == "Jaipur, Rajasthan, India")

    first_page = client.get("/api/v1/reviews", params={"page": 1, "page_size": 2})
    assert first_page.json()["total"] == 5
    assert first_page.json()["pages"] == 3
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["items"][0]["review_date"] == "2026-11-14"

    priority = client.get("/api/v1/reviews", params={"sort": "priority", "page_size": 5})
    assert priority.json()["items"][0]["rating"] == 2.0

    filtered = client.get(
        "/api/v1/reviews",
        params={"search": "cold", "location_id": jaipur_id, "rating": 2, "date_from": "2026-11-11", "date_to": "2026-11-12"},
    )
    assert filtered.json()["total"] == 1
    target_id = filtered.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/reviews/{target_id}")
    assert detail.json()["location"]["name"] == "Jaipur, Rajasthan, India"
    assert detail.json()["source_name"] == "Google Maps"
    assert detail.json()["author_name"] == "Aditi Sharma"

    updated = client.patch(f"/api/v1/reviews/{target_id}/status", json={"status": "resolved"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"


def test_analytics_uses_persisted_review_aggregates(client: TestClient) -> None:
    upload(
        client,
        make_csv(
            [
                row(text="Jaipur chai was excellent.", rating="5", external_id="A-1", location="Jaipur, Rajasthan, India", review_date="2026-11-14"),
                row(text="Jaipur cafe was fine; invoice took a while.", rating="3", external_id="A-2", location="Jaipur, Rajasthan, India", review_date="2026-11-13"),
                row(text="Chandigarh delivery was cold and late.", rating="1", external_id="A-3", location="Chandigarh, India", review_date="2026-11-12"),
            ]
        ),
    )
    response = client.get("/api/v1/analytics/summary", params={"days": 30})
    body = response.json()
    assert body["total_reviews"] == 3
    assert body["average_rating"] == 3.0
    assert body["needs_attention"] == 1
    assert body["locations"] == 2
    assert sum(point["count"] for point in body["trend"]) == 3
