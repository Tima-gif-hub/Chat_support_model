from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .embedding import DeterministicEmbedding
from .models import Chunk, Document

REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "index_version",
    "workspace_id",
    "embedding_model",
    "embedding_revision",
    "embedding_dimensions",
    "reranker_model",
    "reranker_revision",
    "chunking_config_sha256",
    "source_manifest_sha256",
    "document_count",
    "chunk_count",
    "retrieval_report_sha256",
    "quality_gate",
    "status",
    "created_at",
    "git_commit",
}


def validate_index_manifest(manifest: dict[str, Any]) -> None:
    missing = REQUIRED_MANIFEST_FIELDS - manifest.keys()
    if missing:
        raise ValueError(f"index manifest missing fields: {sorted(missing)}")
    if set(manifest) != REQUIRED_MANIFEST_FIELDS:
        raise ValueError("index manifest contains unsupported fields")
    if (
        manifest["schema_version"] != "1.0"
        or manifest["workspace_id"] != "anonymous-furniture-company"
    ):
        raise ValueError("unsupported index manifest")
    if (
        manifest["embedding_model"] != "BAAI/bge-base-en-v1.5"
        or manifest["embedding_dimensions"] != 768
    ):
        raise ValueError("unsupported embedding contract")
    if manifest["reranker_model"] != "BAAI/bge-reranker-base":
        raise ValueError("unsupported reranker contract")
    for field in ("index_version", "embedding_revision", "reranker_revision", "git_commit"):
        value = manifest[field]
        minimum = 7 if field.endswith("revision") or field == "git_commit" else 1
        if not isinstance(value, str) or len(value) < minimum:
            raise ValueError(f"invalid index manifest identity: {field}")
    if manifest["quality_gate"] != "passed" or manifest["status"] not in {"inactive", "active"}:
        raise ValueError("index manifest is not promotable")
    for field in (
        "chunking_config_sha256",
        "source_manifest_sha256",
        "retrieval_report_sha256",
    ):
        value = manifest[field]
        if not isinstance(value, str) or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise ValueError(f"invalid index manifest checksum: {field}")
    for field in ("document_count", "chunk_count"):
        value = manifest[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"invalid index manifest count: {field}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_index_manifest(
    *,
    index_version: str,
    workspace_id: str,
    documents: list[Document],
    chunks: list[Chunk],
    chunking_config: Path,
    source_manifest: Path,
    retrieval_report: Path,
    reranker_revision: str,
    git_commit: str,
    status: str = "inactive",
    embedding: DeterministicEmbedding | None = None,
) -> dict[str, Any]:
    """Build the manifest required before an index can be activated."""
    embedding = embedding or DeterministicEmbedding()
    if status not in {"inactive", "active"}:
        raise ValueError("index status must be inactive or active")
    if not documents or not chunks:
        raise ValueError("an index manifest requires documents and chunks")
    if any(
        chunk.workspace_id != workspace_id
        or chunk.index_version != index_version
        or len(chunk.embedding) != embedding.dimensions
        for chunk in chunks
    ):
        raise ValueError("chunk identity or embedding dimensions do not match manifest")
    if any(document.workspace_id != workspace_id for document in documents):
        raise ValueError("document workspace does not match manifest workspace")
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("document IDs must be unique within an index")
    manifest = {
        "schema_version": "1.0",
        "index_version": index_version,
        "workspace_id": workspace_id,
        "embedding_model": embedding.model_name,
        "embedding_revision": embedding.revision,
        "embedding_dimensions": embedding.dimensions,
        "reranker_model": "BAAI/bge-reranker-base",
        "reranker_revision": reranker_revision,
        "chunking_config_sha256": sha256_file(chunking_config),
        "source_manifest_sha256": sha256_file(source_manifest),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "retrieval_report_sha256": sha256_file(retrieval_report),
        "quality_gate": "passed",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
    }
    validate_index_manifest(manifest)
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
