from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .chunking import chunk_document
from .config import RagConfig
from .embedding import DeterministicEmbedding
from .models import Chunk, Document
from .parsers import parse_source
from .security import contains_instructional_injection

REQUIRED_METADATA = {
    "document_id",
    "workspace_id",
    "title",
    "document_type",
    "source_uri",
    "language",
    "audience",
    "effective_from",
    "effective_to",
    "updated_at",
    "content_sha256",
}
ALLOWED_DOCUMENT_TYPES = {
    "catalog",
    "policy",
    "delivery",
    "warranty",
    "returns",
    "assembly",
    "faq",
    "pricing",
}


class ValidationError(ValueError):
    pass


def normalize_content(content: str) -> str:
    content = unicodedata.normalize("NFKC", content).replace("\r\n", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in content.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_datetime(value: object) -> datetime | None:
    if value is None or value == "null":
        return None
    if not isinstance(value, str):
        raise ValidationError("timestamps must be RFC3339 strings or null")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValidationError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def load_document(path: Path) -> Document:
    metadata, raw_content = parse_source(path)
    missing = REQUIRED_METADATA - metadata.keys()
    if missing:
        raise ValidationError(f"{path.name}: missing metadata: {', '.join(sorted(missing))}")
    content = normalize_content(raw_content)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    declared_digest = metadata["content_sha256"]
    if declared_digest not in {"auto", digest}:
        raise ValidationError(f"{path.name}: content_sha256 does not match normalized content")
    if metadata["document_type"] not in ALLOWED_DOCUMENT_TYPES:
        raise ValidationError(f"{path.name}: invalid document_type")
    if metadata["language"] != "en":
        raise ValidationError(f"{path.name}: public fixture language must be en")
    if contains_instructional_injection(content):
        raise ValidationError(f"{path.name}: possible prompt injection in source content")
    effective_from = parse_datetime(metadata["effective_from"])
    effective_to = parse_datetime(metadata["effective_to"])
    if effective_from and effective_to and effective_from >= effective_to:
        raise ValidationError(f"{path.name}: invalid validity interval")
    return Document(
        document_id=str(metadata["document_id"]),
        workspace_id=str(metadata["workspace_id"]),
        title=str(metadata["title"]),
        document_type=str(metadata["document_type"]),  # type: ignore[arg-type]
        source_uri=str(metadata["source_uri"]),
        language=str(metadata["language"]),
        audience=str(metadata["audience"]),
        effective_from=effective_from,
        effective_to=effective_to,
        updated_at=parse_datetime(metadata["updated_at"]) or datetime.now(UTC),
        content_sha256=digest,
        content=content,
    )


def discover(directory: Path) -> list[Path]:
    supported = {".json", ".md", ".txt", ".html", ".htm", ".pdf"}
    return sorted(path for path in directory.rglob("*") if path.suffix.lower() in supported)


def build_index(
    source_directory: Path,
    index_version: str,
    config: RagConfig | None = None,
    embedder: DeterministicEmbedding | None = None,
) -> tuple[list[Document], list[Chunk]]:
    config = config or RagConfig()
    embedder = embedder or DeterministicEmbedding(
        config.embedding_dimensions, config.embedding_max_tokens
    )
    documents = [load_document(path) for path in discover(source_directory)]
    ids = [document.document_id for document in documents]
    if len(ids) != len(set(ids)):
        raise ValidationError("document_id values must be unique")
    chunks: list[Chunk] = []
    for document in documents:
        for chunk in chunk_document(document, index_version, config):
            chunks.append(replace(chunk, embedding=embedder.embed(chunk.content)))
    return documents, chunks


def write_index(path: Path, documents: list[Document], chunks: list[Chunk]) -> None:
    """Write a reproducible local index; production writes equivalent rows to PostgreSQL."""

    payload = {
        "documents": [
            {
                **doc.__dict__,
                "effective_from": _date(doc.effective_from),
                "effective_to": _date(doc.effective_to),
                "updated_at": _date(doc.updated_at),
            }
            for doc in documents
        ],
        "chunks": [
            {
                **chunk.__dict__,
                "heading_path": list(chunk.heading_path),
                "embedding": list(chunk.embedding),
                "effective_from": _date(chunk.effective_from),
                "effective_to": _date(chunk.effective_to),
                "updated_at": _date(chunk.updated_at),
            }
            for chunk in chunks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_source_manifest(path: Path, documents: list[Document]) -> None:
    """Write the immutable source lineage used by an index manifest hash."""
    payload = {
        "schema_version": "1.0",
        "documents": [
            {
                "document_id": document.document_id,
                "source_uri": document.source_uri,
                "content_sha256": document.content_sha256,
                "updated_at": _date(document.updated_at),
            }
            for document in sorted(documents, key=lambda item: item.document_id)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_inactive_postgres_index(
    source_directory: Path,
    *,
    index_version: str,
    dsn: str,
    manifest: dict[str, object],
    config: RagConfig | None = None,
) -> tuple[list[Document], list[Chunk]]:
    """Build and persist an inactive pgvector index.

    Promotion is intentionally a separate ``activate`` call on
    :class:`PostgresIndexStore`; an ingestion failure can therefore never
    replace the serving index.
    """
    from .postgres import PostgresIndexStore

    documents, chunks = build_index(source_directory, index_version, config)
    if not documents or not chunks:
        raise ValidationError("cannot write an empty RAG index")
    PostgresIndexStore(dsn).write_inactive(
        index_version=index_version,
        workspace_id=documents[0].workspace_id,
        manifest=manifest,
        documents=documents,
        chunks=chunks,
    )
    return documents, chunks


def _date(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None
