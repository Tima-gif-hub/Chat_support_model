"""Optional PostgreSQL/pgvector index adapter.

The local deterministic path never imports a database driver.  Deployments
provide psycopg (v3), a DSN, and the migrations in this component.  All SQL
queries keep the trusted ACL and validity predicates in the database boundary.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, Literal

from .artifacts import validate_index_manifest
from .embedding import DeterministicEmbedding
from .models import Chunk, Document, Evidence, RetrievalContext, RetrievalResponse
from .retrieval import _reranker_score


def _vector_literal(values: tuple[float, ...]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in values) + "]"


class PostgresIndexStore:
    """pgvector-backed writer and lifecycle controller for an index version."""

    def __init__(self, dsn: str, connection_factory: Callable[[str], Any] | None = None) -> None:
        self.dsn = dsn
        self._connection_factory = connection_factory

    def _connect(self) -> Any:
        if self._connection_factory:
            return self._connection_factory(self.dsn)
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - deployment optional
            raise RuntimeError("Postgres mode requires psycopg[binary]") from exc
        return psycopg.connect(self.dsn)

    def write_inactive(
        self,
        *,
        index_version: str,
        workspace_id: str,
        manifest: dict[str, Any],
        documents: list[Document],
        chunks: list[Chunk],
    ) -> None:
        if manifest.get("status") != "inactive":
            raise ValueError("new indexes must be written inactive")
        validate_index_manifest(manifest)
        if (
            manifest.get("index_version") != index_version
            or manifest.get("workspace_id") != workspace_id
        ):
            raise ValueError("index manifest identity does not match write request")
        if manifest.get("document_count") != len(documents) or manifest.get("chunk_count") != len(
            chunks
        ):
            raise ValueError("index manifest counts do not match write request")
        if any(
            document.workspace_id != workspace_id for document in documents
        ) or any(
            chunk.workspace_id != workspace_id or chunk.index_version != index_version
            for chunk in chunks
        ):
            raise ValueError("index rows do not match write request identity")
        connection = self._connect()
        try:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO rag.index_versions "
                    "(index_version,workspace_id,status,manifest) "
                    "VALUES (%s,%s,'inactive',%s::jsonb)",
                    (index_version, workspace_id, json.dumps(manifest)),
                )
                for document in documents:
                    cursor.execute(
                        "INSERT INTO rag.documents "
                        "(index_version,document_id,workspace_id,title,document_type,source_uri,language,audience," 
                        "effective_from,effective_to,updated_at,content_sha256) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            index_version,
                            document.document_id,
                            document.workspace_id,
                            document.title,
                            document.document_type,
                            document.source_uri,
                            document.language,
                            document.audience,
                            document.effective_from,
                            document.effective_to,
                            document.updated_at,
                            document.content_sha256,
                        ),
                    )
                for chunk in chunks:
                    cursor.execute(
                        "INSERT INTO rag.chunks "
                        "(index_version,document_id,chunk_id,heading_path,content,token_start,token_end,"
                        "content_sha256,workspace_id,audience,language,effective_from,effective_to,updated_at,"
                        "source_uri,embedding) VALUES "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                        (
                            index_version,
                            chunk.document_id,
                            chunk.chunk_id,
                            list(chunk.heading_path),
                            chunk.content,
                            chunk.token_start,
                            chunk.token_end,
                            chunk.content_sha256,
                            chunk.workspace_id,
                            chunk.audience,
                            chunk.language,
                            chunk.effective_from,
                            chunk.effective_to,
                            chunk.updated_at,
                            chunk.source_uri,
                            _vector_literal(chunk.embedding),
                        ),
                    )
        finally:
            connection.close()

    def activate(self, index_version: str) -> None:
        connection = self._connect()
        try:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute("SELECT rag.activate_index(%s)", (index_version,))
        finally:
            connection.close()

    def rollback(self, index_version: str) -> None:
        """Promote a previously written approved version atomically."""
        self.activate(index_version)

    def active_version(self, workspace_id: str) -> str | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT index_version FROM rag.index_versions "
                    "WHERE workspace_id=%s AND status='active'",
                    (workspace_id,),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None
        finally:
            connection.close()

    def ready_version(
        self, index_version: str, workspace_id: str, embedding_dimensions: int
    ) -> bool:
        """Verify the active pointer and the materialized index identity before serving."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT manifest FROM rag.index_versions "
                    "WHERE index_version=%s AND workspace_id=%s AND status='active'",
                    (index_version, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    return False
                manifest = row[0]
                if isinstance(manifest, str):
                    manifest = json.loads(manifest)
                validate_index_manifest(manifest)
                cursor.execute(
                    "SELECT (SELECT count(*) FROM rag.documents WHERE index_version=%s), "
                    "count(*), COALESCE(bool_and(vector_dims(embedding)=%s), false) "
                    "FROM rag.chunks WHERE index_version=%s",
                    (index_version, embedding_dimensions, index_version),
                )
                document_count, chunk_count, dimensions_match = cursor.fetchone()
                return bool(
                    manifest["index_version"] == index_version
                    and manifest["workspace_id"] == workspace_id
                    and manifest["embedding_dimensions"] == embedding_dimensions
                    and manifest["document_count"] == document_count
                    and manifest["chunk_count"] == chunk_count
                    and dimensions_match
                )
        except Exception:
            return False
        finally:
            connection.close()


# Explicit names used in deployment wiring and documentation.  Keeping the
# writer separate from the reader makes it difficult for request handling to
# mutate index lifecycle state accidentally.
PostgresRagAdapter = PostgresIndexStore


class IndexLifecycle:
    def __init__(self, store: PostgresIndexStore) -> None:
        self.store = store

    def write_inactive(self, **kwargs: Any) -> None:
        self.store.write_inactive(**kwargs)

    def activate(self, index_version: str) -> None:
        self.store.activate(index_version)

    def rollback(self, index_version: str) -> None:
        self.store.rollback(index_version)


class PostgresRetriever:
    """Hybrid pgvector + PostgreSQL FTS reader implementing the RAG contract."""

    def __init__(
        self,
        store: PostgresIndexStore,
        *,
        index_version: str,
        embedder: DeterministicEmbedding | None = None,
        dense_candidates: int = 20,
        lexical_candidates: int = 20,
        max_results: int = 5,
        rerank_candidates: int = 12,
        reranker_threshold: float = 0.35,
        max_evidence_tokens: int = 2400,
        rrf_k: int = 60,
        hnsw_ef_search: int = 100,
    ) -> None:
        self.store = store
        self.index_version = index_version
        self.embedder = embedder or DeterministicEmbedding()
        self.dense_candidates = dense_candidates
        self.lexical_candidates = lexical_candidates
        self.max_results = max_results
        self.rerank_candidates = rerank_candidates
        self.reranker_threshold = reranker_threshold
        self.max_evidence_tokens = max_evidence_tokens
        self.rrf_k = rrf_k
        self.hnsw_ef_search = hnsw_ef_search
        self.last_candidate_counts = (0, 0, 0)

    def retrieve(self, query: str, context: RetrievalContext) -> RetrievalResponse:
        query = " ".join(query.casefold().split())
        query_id = "qry_" + uuid.uuid5(
            uuid.NAMESPACE_URL, f"{self.index_version}:{query}:{context.workspace_id}"
        ).hex[:20]
        if not query:
            return RetrievalResponse(query_id, self.index_version, "insufficient_evidence", ())
        vector = _vector_literal(self.embedder.embed(query))
        connection = self.store._connect()
        try:
            with connection.cursor() as cursor:
                # ef_search is set for this transaction only; ACL and validity
                # predicates are mandatory in both candidate queries.
                if not 1 <= self.hnsw_ef_search <= 10000:
                    raise ValueError("hnsw ef_search must be between 1 and 10000")
                cursor.execute(
                    "SELECT set_config('hnsw.ef_search', %s, true)",
                    (str(self.hnsw_ef_search),),
                )
                base = (
                    context.workspace_id,
                    context.audience,
                    context.language,
                    context.as_of,
                    self.index_version,
                )
                cursor.execute(
                    "SELECT c.chunk_id,c.document_id,d.title,c.heading_path,c.content,c.source_uri,"
                    "c.updated_at,GREATEST(0, 1 - (c.embedding <=> %s::vector)) AS score "
                    "FROM rag.chunks c JOIN rag.documents d ON "
                    "d.index_version=c.index_version AND d.document_id=c.document_id "
                    "WHERE c.workspace_id=%s AND c.audience=%s AND c.language=%s "
                    "AND (c.effective_from IS NULL OR c.effective_from <= %s) "
                    "AND (c.effective_to IS NULL OR %s < c.effective_to) AND c.index_version=%s "
                    "AND EXISTS (SELECT 1 FROM rag.index_versions iv "
                    "WHERE iv.index_version = c.index_version AND iv.status='active') "
                    "ORDER BY c.embedding <=> %s::vector LIMIT %s",
                    (vector, *base[:4], context.as_of, base[4], vector, self.dense_candidates),
                )
                dense_rows = cursor.fetchall()
                cursor.execute(
                    "SELECT c.chunk_id,c.document_id,d.title,c.heading_path,c.content,c.source_uri,"
                    "c.updated_at,ts_rank_cd(c.search_vector, "
                    "plainto_tsquery('english', %s)) AS score "
                    "FROM rag.chunks c JOIN rag.documents d ON "
                    "d.index_version=c.index_version AND d.document_id=c.document_id "
                    "WHERE c.workspace_id=%s AND c.audience=%s AND c.language=%s "
                    "AND (c.effective_from IS NULL OR c.effective_from <= %s) "
                    "AND (c.effective_to IS NULL OR %s < c.effective_to) AND c.index_version=%s "
                    "AND EXISTS (SELECT 1 FROM rag.index_versions iv "
                    "WHERE iv.index_version = c.index_version AND iv.status='active') "
                    "AND c.search_vector @@ plainto_tsquery('english', %s) "
                    "ORDER BY score DESC, chunk_id LIMIT %s",
                    (query, *base[:4], context.as_of, base[4], query, self.lexical_candidates),
                )
                lexical_rows = cursor.fetchall()
        finally:
            connection.close()
        dense = {row[0]: (row, float(row[7])) for row in dense_rows}
        lexical = {row[0]: (row, float(row[7])) for row in lexical_rows}
        self.last_candidate_counts = (len(dense), len(lexical), len(set(dense) | set(lexical)))
        dense_rank = {key: rank for rank, key in enumerate(dense, 1)}
        lexical_rank = {key: rank for rank, key in enumerate(lexical, 1)}
        ids = sorted(
            set(dense) | set(lexical),
            key=lambda key: (
                -sum(
                    1 / (self.rrf_k + rank)
                    for rank in (dense_rank.get(key), lexical_rank.get(key))
                    if rank is not None
                ),
                key,
            ),
        )[: self.rerank_candidates]
        evidence: list[Evidence] = []
        token_total = 0
        for chunk_id in ids:
            row = (dense.get(chunk_id) or lexical[chunk_id])[0]
            content = str(row[4])
            chunk_like = type(
                "ChunkLike",
                (),
                {"title": row[2], "heading_path": tuple(row[3] or ()), "content": content},
            )()
            score = _reranker_score(query, chunk_like)
            exceeds_budget = evidence and (
                token_total + len(content.split()) > self.max_evidence_tokens
            )
            if score < self.reranker_threshold or exceeds_budget:
                continue
            evidence.append(
                Evidence(
                    f"S{len(evidence) + 1}",
                    row[1],
                    row[0],
                    row[2],
                    tuple(row[3] or ()),
                    content,
                    row[5],
                    dense.get(chunk_id, (None, 0.0))[1],
                    lexical.get(chunk_id, (None, 0.0))[1],
                    score,
                    row[6],
                )
            )
            token_total += len(content.split())
            if len(evidence) >= self.max_results:
                break
        status: Literal["ok", "insufficient_evidence"] = (
            "ok" if evidence else "insufficient_evidence"
        )
        return RetrievalResponse(query_id, self.index_version, status, tuple(evidence))
