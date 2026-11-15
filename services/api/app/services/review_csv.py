import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, Review

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_REVIEW_TEXT_LENGTH = 5000
MAX_ROWS = 10000

HEADER_ALIASES = {
    "text": "review_text",
    "review": "review_text",
    "review_body": "review_text",
    "author": "author_name",
    "author_name": "author_name",
    "customer": "author_name",
    "date": "review_date",
    "created_at": "review_date",
    "location_name": "location",
    "review_source": "source",
    "platform": "source",
    "external_id": "external_review_id",
    "id": "external_review_id",
    "synthetic": "is_synthetic",
}
SUPPORTED_HEADERS = {
    "review_text", "rating", "author_name", "review_date", "location", "source",
    "external_review_id", "is_synthetic",
}


@dataclass
class RowIssue:
    code: str
    message: str


@dataclass
class ParsedReview:
    row_number: int
    review_text: str
    rating: float
    author_name: str | None
    review_date: date | None
    location: str
    source: str
    external_review_id: str | None
    is_synthetic: bool
    dedupe_key: str
    issues: list[RowIssue] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.issues


@dataclass
class CsvPreview:
    headers: list[str]
    rows: list[ParsedReview]
    total_rows: int

    @property
    def accepted_rows(self) -> int:
        return sum(row.accepted for row in self.rows)

    @property
    def rejected_rows(self) -> int:
        return self.total_rows - self.accepted_rows


class CsvImportError(ValueError):
    def __init__(self, message: str, code: str = "invalid_csv", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def normalize_header(value: str) -> str:
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    return HEADER_ALIASES.get(normalized, normalized)


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD or a recognizable date such as 04/21/2026.")


def _parse_synthetic(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"", "false", "no", "0"}:
        return False
    if normalized in {"true", "yes", "1"}:
        return True
    raise ValueError("is_synthetic must be true or false.")


def review_dedupe_key(
    review_text: str,
    rating: float,
    author_name: str | None,
    review_date: date | None,
    location: str,
    source: str,
    external_review_id: str | None,
) -> str:
    if external_review_id:
        stable_value = "external\0" + source.strip().casefold() + "\0" + external_review_id.strip().casefold()
    else:
        stable_value = "review\0" + json.dumps(
            [
                " ".join(review_text.casefold().split()),
                rating,
                (author_name or "").strip().casefold(),
                review_date.isoformat() if review_date else "",
                location.strip().casefold(),
                source.strip().casefold(),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return hashlib.sha256(stable_value.encode("utf-8")).hexdigest()


def parse_review_csv(content: bytes) -> CsvPreview:
    if not content:
        raise CsvImportError("The uploaded CSV is empty.", "empty_file")
    if len(content) > MAX_CSV_BYTES:
        raise CsvImportError("CSV files must be 10 MB or smaller.", "file_too_large")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("The file must use UTF-8 or UTF-8 with BOM encoding.", "invalid_encoding") from exc

    row_number = 1
    try:
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        raw_headers = next(reader, None)
        if not raw_headers:
            raise CsvImportError("The CSV needs a header row.", "missing_headers")
        headers = [normalize_header(header) for header in raw_headers]
        if len(set(headers)) != len(headers):
            raise CsvImportError("The CSV has duplicate column names after normalization.", "duplicate_headers")
        missing = sorted({"review_text", "rating"} - set(headers))
        if missing:
            raise CsvImportError(
                "Required columns are missing.",
                "missing_columns",
                {"missing_columns": missing, "required_columns": ["review_text", "rating"]},
            )

        output: list[ParsedReview] = []
        for cells in reader:
            row_number += 1
            if not cells or all(not cell.strip() for cell in cells):
                continue
            if len(output) >= MAX_ROWS:
                raise CsvImportError("CSV files may contain at most 10,000 review rows.", "too_many_rows")

            issues: list[RowIssue] = []
            if len(cells) != len(headers):
                output.append(
                    ParsedReview(
                        row_number=row_number,
                        review_text="",
                        rating=0,
                        author_name=None,
                        review_date=None,
                        location="",
                        source="",
                        external_review_id=None,
                        is_synthetic=False,
                        dedupe_key="",
                        issues=[RowIssue("column_count", f"Expected {len(headers)} columns but found {len(cells)}.")],
                    )
                )
                continue

            values = dict(zip(headers, cells))
            review_text = values.get("review_text", "").strip()
            if not review_text:
                issues.append(RowIssue("missing_review_text", "Review text is required."))
            elif len(review_text) > MAX_REVIEW_TEXT_LENGTH:
                issues.append(RowIssue("review_too_long", f"Review text must be {MAX_REVIEW_TEXT_LENGTH} characters or fewer."))

            rating_value = 0.0
            try:
                rating_decimal = Decimal(values.get("rating", "").strip())
                if not rating_decimal.is_finite() or rating_decimal < 1 or rating_decimal > 5:
                    raise ValueError("Rating must be between 1 and 5.")
                if rating_decimal * 2 != (rating_decimal * 2).to_integral_value():
                    raise ValueError("Rating must use whole or half-star increments (for example, 4 or 4.5).")
                rating_value = float(rating_decimal)
            except (InvalidOperation, ValueError):
                issues.append(RowIssue("invalid_rating", "Rating must be 1–5 in whole or half-star increments."))

            author = values.get("author_name", "").strip() or None
            location = values.get("location", "").strip() or "Unspecified location"
            source = values.get("source", "").strip() or "CSV import"
            external_id = values.get("external_review_id", "").strip() or None
            if author and len(author) > 160:
                issues.append(RowIssue("author_too_long", "Author name must be 160 characters or fewer."))
            if len(location) > 160:
                issues.append(RowIssue("location_too_long", "Location must be 160 characters or fewer."))
            if len(source) > 80:
                issues.append(RowIssue("source_too_long", "Review source must be 80 characters or fewer."))
            if external_id and len(external_id) > 180:
                issues.append(RowIssue("external_id_too_long", "External review ID must be 180 characters or fewer."))
            parsed_date = None
            try:
                parsed_date = _parse_date(values.get("review_date", ""))
            except ValueError as exc:
                issues.append(RowIssue("invalid_date", str(exc)))
            synthetic = False
            try:
                synthetic = _parse_synthetic(values.get("is_synthetic", ""))
            except ValueError as exc:
                issues.append(RowIssue("invalid_synthetic_flag", str(exc)))

            output.append(
                ParsedReview(
                    row_number=row_number,
                    review_text=review_text,
                    rating=rating_value,
                    author_name=author,
                    review_date=parsed_date,
                    location=location,
                    source=source,
                    external_review_id=external_id,
                    is_synthetic=synthetic,
                    dedupe_key=review_dedupe_key(review_text, rating_value, author, parsed_date, location, source, external_id),
                    issues=issues,
                )
            )
        if not output:
            raise CsvImportError("The CSV contains no review rows.", "no_rows")
        return CsvPreview(headers=[h for h in headers if h in SUPPORTED_HEADERS], rows=output, total_rows=len(output))
    except csv.Error as exc:
        raise CsvImportError(f"Malformed CSV near row {row_number + 1}: {exc}", "malformed_csv") from exc


def mark_duplicates(preview: CsvPreview, db: Session, tenant_id: str) -> CsvPreview:
    seen: set[str] = set()
    keys = sorted({row.dedupe_key for row in preview.rows if row.accepted})
    existing: set[str] = set()
    for offset in range(0, len(keys), 500):
        existing.update(
            db.scalars(
                select(Review.dedupe_key).where(
                    Review.tenant_id == tenant_id,
                    Review.dedupe_key.in_(keys[offset : offset + 500]),
                )
            ).all()
        )
    for row in preview.rows:
        if not row.accepted:
            continue
        if row.dedupe_key in existing:
            row.issues.append(RowIssue("duplicate_review", "This review is already in the workspace."))
        elif row.dedupe_key in seen:
            row.issues.append(RowIssue("duplicate_in_file", "This review appears more than once in this CSV."))
        else:
            seen.add(row.dedupe_key)
    return preview
