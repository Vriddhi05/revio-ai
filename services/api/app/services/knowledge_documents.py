import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath, PureWindowsPath

from pypdf import PdfReader

from app.core.config import get_settings

SUPPORTED_TYPES = {".pdf", ".txt", ".md", ".markdown"}
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DocumentError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    title: str
    source_key: str
    media_type: str
    size_bytes: int
    pages: list[dict[str, int | str | None]]
    content_sha256: str
    extracted_chars: int


def safe_filename(value: str | None) -> str:
    candidate = (value or "").replace("\x00", "").strip()
    name = PureWindowsPath(candidate).name
    name = PurePath(name).name
    name = CONTROL_CHARS.sub("", name).strip(" .")
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name)[:240].strip(" .")
    if not name or name in {".", ".."}:
        raise DocumentError("invalid_filename", "Provide a valid document filename.")
    return name


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    value = CONTROL_CHARS.sub("", value)
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in value.split("\n")]
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_document(filename: str | None, content: bytes) -> ExtractedDocument:
    settings = get_settings()
    safe_name = safe_filename(filename)
    suffix = PurePath(safe_name).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise DocumentError("unsupported_file_type", "Supported document types are PDF, TXT, and Markdown.")
    if not content:
        raise DocumentError("empty_file", "The uploaded document is empty.")
    if len(content) > settings.knowledge_upload_max_bytes:
        raise DocumentError("file_too_large", f"The document exceeds the {settings.knowledge_upload_max_bytes // (1024 * 1024)} MB upload limit.")

    pages: list[dict[str, int | str | None]]
    media_type: str
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise DocumentError("invalid_pdf", "The file extension is PDF, but the content is not a valid PDF.")
        try:
            reader = PdfReader(__import__("io").BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DocumentError("encrypted_pdf", "Password-protected PDFs are not supported.")
            pages = [
                {"page_number": index + 1, "text": normalize_text(page.extract_text() or "")}
                for index, page in enumerate(reader.pages)
            ]
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("pdf_extraction_failed", "Text extraction failed. Check the PDF and try again.") from exc
        if not any(page["text"] for page in pages):
            raise DocumentError("no_extractable_text", "No selectable text was found. Scanned PDFs require OCR, which is not supported.")
        media_type = "application/pdf"
    else:
        try:
            text = content.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise DocumentError("invalid_text_encoding", "Text documents must use UTF-8 encoding.") from exc
        if "\x00" in text:
            raise DocumentError("invalid_text_content", "The document contains binary content and cannot be indexed as text.")
        text = normalize_text(text)
        pages = [{"page_number": None, "text": text}]
        media_type = "text/markdown" if suffix in {".md", ".markdown"} else "text/plain"

    extracted_chars = sum(len(page["text"]) for page in pages)
    if extracted_chars == 0:
        raise DocumentError("empty_document", "The document contains no readable text.")
    if extracted_chars > settings.knowledge_max_extracted_chars:
        raise DocumentError("document_text_too_large", "The extracted text exceeds the configured document limit.")
    canonical = json.dumps(pages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    source_stem = PurePath(safe_name).stem
    source_key = re.sub(r"\s+", " ", safe_name.casefold()).strip()
    return ExtractedDocument(
        filename=safe_name,
        title=source_stem[:240] or safe_name,
        source_key=source_key,
        media_type=media_type,
        size_bytes=len(content),
        pages=pages,
        content_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        extracted_chars=extracted_chars,
    )


def split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars < 1 or overlap < 0 or overlap >= max_chars:
        raise ValueError("Chunk size must be positive and overlap must be smaller than chunk size.")
    text = normalize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end), text.rfind(" ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + (1 if text[boundary] == "\n" else 2 if text[boundary:boundary + 2] == ". " else 1)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
        while start < len(text) and text[start].isspace():
            start += 1
    return chunks


def token_ids(tokenizer, text: str, add_special_tokens: bool = False) -> list[int]:
    """Tokenize without the transformers warning emitted for intentional pre-chunking."""
    backend = getattr(tokenizer, "backend_tokenizer", None)
    if backend is not None:
        return backend.encode(text, add_special_tokens=add_special_tokens).ids
    if hasattr(tokenizer, "tokenize") and hasattr(tokenizer, "convert_tokens_to_ids"):
        ids = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(text))
        return tokenizer.build_inputs_with_special_tokens(ids) if add_special_tokens else ids
    return tokenizer.encode(text, add_special_tokens=add_special_tokens)


def token_count(tokenizer, text: str, add_special_tokens: bool = False) -> int:
    return len(token_ids(tokenizer, text, add_special_tokens))


def chunk_pages(document_id: str, tenant_id: str, content_hash: str, version: int, filename: str, pages: list[dict], max_chars: int, overlap: int) -> list[dict]:
    results = []
    index = 0
    for page in pages:
        for text in split_text(str(page["text"]), max_chars, overlap):
            page_number = page.get("page_number")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunk_id = hashlib.sha256(
                f"{tenant_id}|{document_id}|{content_hash}|{version}|{index}|{page_number}|{digest}".encode("utf-8")
            ).hexdigest()
            results.append({
                "id": chunk_id,
                "text": text,
                "page_number": page_number,
                "chunk_index": index,
                "source_reference": f"{filename} · p. {page_number}" if page_number else filename,
            })
            index += 1
    return results


def split_chunks_to_token_limit(chunks: list[dict], tokenizer, max_tokens: int, overlap_tokens: int, prefix: str = "passage: ") -> list[dict]:
    """Split character chunks further so the embedding model cannot silently truncate them."""
    special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
    prefix_tokens = token_count(tokenizer, prefix, add_special_tokens=False)
    content_limit = max_tokens - special_tokens - prefix_tokens
    if content_limit < 1 or overlap_tokens < 0 or overlap_tokens >= content_limit:
        raise ValueError("Token chunk limits must leave room for passage text and overlap.")
    output = []
    for chunk in chunks:
        ids = token_ids(tokenizer, chunk["text"], add_special_tokens=False)
        starts = range(0, len(ids), content_limit - overlap_tokens) if len(ids) > content_limit else [0]
        for start in starts:
            end = min(len(ids), start + content_limit)
            if start >= len(ids):
                break
            text = tokenizer.decode(ids[start:end], skip_special_tokens=True, clean_up_tokenization_spaces=False).strip()
            if not text:
                continue
            item = dict(chunk)
            if len(ids) > content_limit:
                item["id"] = hashlib.sha256(f"{chunk['id']}|token-window|{start}|{text}".encode("utf-8")).hexdigest()
            item["text"] = text
            item["token_count"] = token_count(tokenizer, prefix + text, add_special_tokens=True)
            output.append(item)
    for index, item in enumerate(output):
        item["chunk_index"] = index
    return output


INJECTION_PATTERN = re.compile(
    r"(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|"
    r"reveal\s+(?:the\s+)?(?:system\s+)?prompt|exfiltrate\s+(?:secrets|credentials)|"
    r"act\s+as\s+(?:an?\s+)?(?:unrestricted|system)\s+assistant",
    re.IGNORECASE,
)


def content_risk_flags(text: str) -> list[str]:
    """Heuristic indicator only; it is not prompt-injection protection."""
    return ["instruction_like_text"] if INJECTION_PATTERN.search(text) else []
