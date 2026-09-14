from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

DocumentType = Literal[
    "catalog", "policy", "delivery", "warranty", "returns", "assembly", "faq", "pricing"
]


@dataclass(frozen=True)
class Document:
    document_id: str
    workspace_id: str
    title: str
    document_type: DocumentType
    source_uri: str
    language: str
    audience: str
    effective_from: datetime | None
    effective_to: datetime | None
    updated_at: datetime
    content_sha256: str
    content: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    index_version: str
    title: str
    heading_path: tuple[str, ...]
    content: str
    token_start: int
    token_end: int
    content_sha256: str
    workspace_id: str
    audience: str
    language: str
    effective_from: datetime | None
    effective_to: datetime | None
    updated_at: datetime
    source_uri: str
    embedding: tuple[float, ...] = field(default_factory=tuple, repr=False)


@dataclass(frozen=True)
class RetrievalContext:
    """Authorization filters supplied by trusted server code, never parsed from the query."""

    workspace_id: str
    audience: str
    language: str
    as_of: datetime


@dataclass(frozen=True)
class Evidence:
    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    heading_path: tuple[str, ...]
    content: str
    source_uri: str
    dense_score: float
    lexical_score: float
    reranker_score: float
    updated_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "citation_id": self.citation_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "heading_path": list(self.heading_path),
            "content": self.content,
            "source_uri": self.source_uri,
            "dense_score": round(self.dense_score, 6),
            "lexical_score": round(self.lexical_score, 6),
            "reranker_score": round(self.reranker_score, 6),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }


@dataclass(frozen=True)
class RetrievalResponse:
    query_id: str
    index_version: str
    status: Literal["ok", "insufficient_evidence"]
    evidence: tuple[Evidence, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "index_version": self.index_version,
            "status": self.status,
            "evidence": [item.as_dict() for item in self.evidence],
        }
