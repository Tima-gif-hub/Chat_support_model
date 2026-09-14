from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from rag_platform.chunking import chunk_document
from rag_platform.config import RagConfig
from rag_platform.models import Document


def _document(content: str, document_id: str = "one") -> Document:
    return Document(
        document_id=document_id,
        workspace_id="anonymous-furniture-company",
        title="Test",
        document_type="faq",
        source_uri="kb://test",
        language="en",
        audience="customer",
        effective_from=None,
        effective_to=None,
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        content_sha256="0" * 64,
        content=content,
    )


def test_chunking_honors_maximum_overlap_and_heading_path() -> None:
    words = " ".join(f"token{i}" for i in range(900))
    chunks = chunk_document(_document(f"# Products\n\n## Sizes\n\n{words}"), "idx", RagConfig())
    assert len(chunks) == 2
    assert all(chunk.token_end - chunk.token_start <= 512 for chunk in chunks)
    assert chunks[0].heading_path == ("Products", "Sizes")
    assert chunks[0].content.split()[-64:] == chunks[1].content.split()[:64]


def test_chunks_never_join_documents() -> None:
    first = chunk_document(_document("# A\n\n" + "alpha " * 100, "first"), "idx", RagConfig())
    second = chunk_document(
        replace(_document("# B\n\n" + "beta " * 100, "second"), source_uri="kb://second"),
        "idx",
        RagConfig(),
    )
    assert {chunk.document_id for chunk in first} == {"first"}
    assert {chunk.document_id for chunk in second} == {"second"}
