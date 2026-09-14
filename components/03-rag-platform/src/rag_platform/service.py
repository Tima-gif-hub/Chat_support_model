from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import RagConfig
from .embedding import DeterministicEmbedding
from .ingestion import build_index
from .metrics import RagMetrics
from .models import RetrievalContext, RetrievalResponse
from .retrieval import HybridRetriever


class RagPlatform:
    def __init__(
        self,
        retriever: Any,
        *,
        backend: str = "deterministic",
        metrics: RagMetrics | None = None,
    ) -> None:
        self.retriever = retriever
        self.backend = backend
        self.metrics = metrics or RagMetrics()
        self.metrics.index(self.index_version)

    @classmethod
    def from_fixtures(
        cls, source_directory: Path, index_version: str = "idx_local_fixture_v1"
    ) -> RagPlatform:
        config = RagConfig()
        _, chunks = build_index(source_directory, index_version, config)
        return cls(HybridRetriever(chunks, index_version, config), backend="deterministic")

    @classmethod
    def from_postgres(
        cls, dsn: str, index_version: str, config: RagConfig | None = None
    ) -> RagPlatform:
        from .postgres import PostgresIndexStore, PostgresRetriever

        config = config or RagConfig()
        store = PostgresIndexStore(dsn)
        retriever = PostgresRetriever(
            store,
            index_version=index_version,
            embedder=DeterministicEmbedding(
                config.embedding_dimensions, config.embedding_max_tokens
            ),
            dense_candidates=config.dense_candidates,
            lexical_candidates=config.lexical_candidates,
            rerank_candidates=config.rerank_candidates,
            max_results=config.max_results,
            reranker_threshold=config.reranker_threshold,
            max_evidence_tokens=config.max_evidence_tokens,
            rrf_k=config.rrf_k,
            hnsw_ef_search=config.hnsw_ef_search,
        )
        return cls(retriever, backend="postgres_pgvector")

    @property
    def index_version(self) -> str:
        return self.retriever.index_version

    def ready(self, workspace_id: str = "anonymous-furniture-company") -> bool:
        if self.backend == "deterministic":
            return True
        store = getattr(self.retriever, "store", None)
        try:
            return bool(
                store
                and store.ready_version(
                    self.index_version,
                    workspace_id,
                    self.retriever.embedder.dimensions,
                )
            )
        except Exception:  # pragma: no cover - depends on external database
            return False

    def retrieve(
        self,
        query: str,
        *,
        workspace_id: str,
        audience: str,
        language: str,
        as_of: datetime | None = None,
    ) -> RetrievalResponse:
        context = RetrievalContext(
            workspace_id=workspace_id,
            audience=audience,
            language=language,
            as_of=as_of or datetime.now(UTC),
        )
        try:
            with self.metrics.retrieval_timer():
                response = self.retriever.retrieve(query, context)
        except Exception:
            self.metrics.failure()
            raise
        configured = getattr(self.retriever, "config", None)
        configured_dense = getattr(
            configured, "dense_candidates", getattr(self.retriever, "dense_candidates", 0)
        )
        configured_lexical = getattr(
            configured, "lexical_candidates", getattr(self.retriever, "lexical_candidates", 0)
        )
        dense_candidates, lexical_candidates, fused_candidates = getattr(
            self.retriever,
            "last_candidate_counts",
            (configured_dense, configured_lexical, max(configured_dense, configured_lexical)),
        )
        self.metrics.retrieval(
            status=response.status,
            dense_candidates=dense_candidates,
            lexical_candidates=lexical_candidates,
            fused_candidates=fused_candidates,
        )
        return response
