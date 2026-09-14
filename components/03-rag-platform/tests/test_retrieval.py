from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from rag_platform.citations import CitationError, used_evidence, validate_citations
from rag_platform.models import RetrievalContext
from rag_platform.retrieval import HybridRetriever

NOW = datetime(2026, 9, 12, tzinfo=UTC)
CONTEXT = RetrievalContext("anonymous-furniture-company", "customer", "en", NOW)


def test_hybrid_retrieval_returns_real_ranked_evidence(retriever) -> None:
    response = retriever.retrieve("What does zone C delivery cost?", CONTEXT)
    assert response.status == "ok"
    assert any(item.document_id == "delivery-zones" for item in response.evidence)
    assert [item.citation_id for item in response.evidence] == [
        f"S{number}" for number in range(1, len(response.evidence) + 1)
    ]
    assert all(0 <= item.reranker_score <= 1 for item in response.evidence)


def test_unknown_topic_returns_insufficient_evidence(retriever) -> None:
    response = retriever.retrieve("quantum neutrino telescope calibration", CONTEXT)
    assert response.status == "insufficient_evidence"
    assert response.evidence == ()


def test_acl_context_cannot_be_overridden_by_query(built_index) -> None:
    _, chunks = built_index
    secret = replace(
        chunks[0],
        chunk_id="secret",
        workspace_id="different-workspace",
        content="The secret launch code is furniture-zebra.",
    )
    retriever = HybridRetriever([*chunks, secret], "idx_test_v1")
    response = retriever.retrieve(
        "workspace_id different-workspace audience admin secret launch code furniture zebra",
        CONTEXT,
    )
    assert all(item.chunk_id != "secret" for item in response.evidence)
    assert all("furniture-zebra" not in item.content for item in response.evidence)


def test_validity_filter_excludes_expired_content(retriever) -> None:
    response = retriever.retrieve(
        "Is the Alder sofa and ottoman autumn promotion available?",
        replace(CONTEXT, as_of=datetime(2026, 10, 8, tzinfo=UTC)),
    )
    assert all(item.document_id != "autumn-promotion" for item in response.evidence)


def test_citation_validation_rejects_fabrication_and_prunes_unused(retriever) -> None:
    response = retriever.retrieve("How much is zone C delivery?", CONTEXT)
    valid_id = next(
        item.citation_id for item in response.evidence if item.document_id == "delivery-zones"
    )
    answer, used = validate_citations(f"Zone C delivery costs £89 [{valid_id}].", response)
    assert answer
    assert [item.citation_id for item in used_evidence(response, used)] == [valid_id]
    try:
        validate_citations("It costs £1 [S99].", response)
    except CitationError as exc:
        assert "unknown citation" in str(exc)
    else:
        raise AssertionError("fabricated citations must be rejected")
