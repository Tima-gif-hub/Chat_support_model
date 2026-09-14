from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Literal

from .config import RagConfig
from .embedding import DeterministicEmbedding, cosine, tokenize
from .models import Chunk, Evidence, RetrievalContext, RetrievalResponse


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        index_version: str,
        config: RagConfig | None = None,
        embedder: DeterministicEmbedding | None = None,
    ) -> None:
        self.config = config or RagConfig()
        self.embedder = embedder or DeterministicEmbedding(
            self.config.embedding_dimensions, self.config.embedding_max_tokens
        )
        self.chunks = tuple(chunks)
        self.index_version = index_version
        self.last_candidate_counts = (0, 0, 0)

    def retrieve(self, query: str, context: RetrievalContext) -> RetrievalResponse:
        query = " ".join(query.casefold().split())
        query_id = (
            "qry_"
            + hashlib.sha256(
                f"{self.index_version}\0{query}\0{context.workspace_id}".encode()
            ).hexdigest()[:20]
        )
        eligible = [chunk for chunk in self.chunks if _allowed(chunk, context)]
        if not query or not eligible:
            self.last_candidate_counts = (0, 0, 0)
            return RetrievalResponse(query_id, self.index_version, "insufficient_evidence", ())

        query_vector = self.embedder.embed(query)
        dense = sorted(
            ((chunk, max(0.0, cosine(query_vector, chunk.embedding))) for chunk in eligible),
            key=lambda item: (-item[1], item[0].chunk_id),
        )[: self.config.dense_candidates]
        lexical = sorted(
            ((chunk, _lexical_score(query, chunk)) for chunk in eligible),
            key=lambda item: (-item[1], item[0].chunk_id),
        )[: self.config.lexical_candidates]
        dense_rank = {item[0].chunk_id: rank for rank, item in enumerate(dense, 1)}
        lexical_rank = {item[0].chunk_id: rank for rank, item in enumerate(lexical, 1)}
        dense_scores = {item[0].chunk_id: item[1] for item in dense}
        lexical_scores = {item[0].chunk_id: item[1] for item in lexical}
        candidates = {chunk.chunk_id: chunk for chunk, _ in dense + lexical}
        self.last_candidate_counts = (len(dense), len(lexical), len(candidates))
        fused = sorted(
            candidates.values(),
            key=lambda chunk: (
                -sum(
                    1.0 / (self.config.rrf_k + rank)
                    for rank in (dense_rank.get(chunk.chunk_id), lexical_rank.get(chunk.chunk_id))
                    if rank is not None
                ),
                chunk.chunk_id,
            ),
        )[: self.config.rerank_candidates]

        scored = []
        for chunk in fused:
            reranker = _reranker_score(query, chunk)
            if reranker >= self.config.reranker_threshold:
                scored.append((chunk, reranker))
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))

        evidence: list[Evidence] = []
        token_total = 0
        for chunk, reranker in scored:
            size = len(chunk.content.split())
            if evidence and token_total + size > self.config.max_evidence_tokens:
                continue
            evidence.append(
                Evidence(
                    citation_id=f"S{len(evidence) + 1}",
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    source_uri=chunk.source_uri,
                    dense_score=dense_scores.get(chunk.chunk_id, 0.0),
                    lexical_score=lexical_scores.get(chunk.chunk_id, 0.0),
                    reranker_score=reranker,
                    updated_at=chunk.updated_at,
                )
            )
            token_total += size
            if len(evidence) == self.config.max_results:
                break
        status: Literal["ok", "insufficient_evidence"] = (
            "ok" if evidence else "insufficient_evidence"
        )
        return RetrievalResponse(query_id, self.index_version, status, tuple(evidence))


def _allowed(chunk: Chunk, context: RetrievalContext) -> bool:
    return (
        chunk.workspace_id == context.workspace_id
        and chunk.audience == context.audience
        and chunk.language == context.language
        and (chunk.effective_from is None or chunk.effective_from <= context.as_of)
        and (chunk.effective_to is None or context.as_of < chunk.effective_to)
    )


def _lexical_score(query: str, chunk: Chunk) -> float:
    query_counts = Counter(tokenize(query))
    doc_counts = Counter(tokenize(f"{chunk.title} {' '.join(chunk.heading_path)} {chunk.content}"))
    if not query_counts:
        return 0.0
    weighted = sum(min(count, doc_counts[token]) for token, count in query_counts.items())
    return weighted / math.sqrt(sum(query_counts.values()) * max(1, sum(doc_counts.values())))


def _reranker_score(query: str, chunk: Chunk) -> float:
    query_terms = _semantic_terms(query)
    document_terms = _semantic_terms(
        f"{chunk.title} {' '.join(chunk.heading_path)} {chunk.content}"
    )
    if not query_terms:
        return 0.0
    overlap = len(query_terms & document_terms) / len(query_terms)
    phrase_bonus = 0.5 if query in chunk.content.casefold() else 0.0
    # Deterministic cross-feature logit followed by the production-compatible sigmoid range.
    logit = 6.0 * overlap + phrase_bonus - 3.0
    return 1.0 / (1.0 + math.exp(-logit))


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
}


def _semantic_terms(text: str) -> set[str]:
    terms = set()
    for token in tokenize(text):
        if token in _STOP_WORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            token = token[:-1]
        terms.add(token)
    return terms
