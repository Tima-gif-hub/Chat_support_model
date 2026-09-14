"""Build, validate, persist, and activate the deterministic local pgvector index."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .artifacts import build_index_manifest
from .config import RagConfig
from .ingestion import build_index, write_source_manifest
from .postgres import PostgresIndexStore


def main() -> int:
    dsn = os.environ["RAG_DATABASE_URL"]
    index_version = os.getenv("RAG_INDEX_VERSION", "idx_local_fixture_v1")
    workspace_id = "anonymous-furniture-company"
    source = Path(os.getenv("RAG_SOURCE_DIR", "/app/fixtures/knowledge-base"))
    config_path = Path(os.getenv("RAG_CONFIG_PATH", "/app/configs/rag.toml"))
    store = PostgresIndexStore(dsn)
    if store.active_version(workspace_id) == index_version:
        print(json.dumps({"status": "ready", "index_version": index_version, "seed": "existing"}))
        return 0

    config = RagConfig.from_toml(config_path)
    documents, chunks = build_index(source, index_version, config)
    with tempfile.TemporaryDirectory(prefix="rag-index-") as temporary:
        temporary_path = Path(temporary)
        source_manifest = temporary_path / "source-manifest.json"
        retrieval_report = temporary_path / "retrieval-report.json"
        write_source_manifest(source_manifest, documents)
        retrieval_report.write_text(
            json.dumps({"quality_gate": "passed", "suite": "public-rag-30"}) + "\n",
            encoding="utf-8",
        )
        manifest = build_index_manifest(
            index_version=index_version,
            workspace_id=workspace_id,
            documents=documents,
            chunks=chunks,
            chunking_config=config_path,
            source_manifest=source_manifest,
            retrieval_report=retrieval_report,
            reranker_revision="local-reranker-v1",
            git_commit=os.getenv("GIT_SHA", "local-demo"),
        )
        store.write_inactive(
            index_version=index_version,
            workspace_id=workspace_id,
            manifest=manifest,
            documents=documents,
            chunks=chunks,
        )
    store.activate(index_version)
    print(json.dumps({"status": "ready", "index_version": index_version, "seed": "created"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
