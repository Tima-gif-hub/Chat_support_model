from __future__ import annotations

from pathlib import Path

import pytest
from rag_platform.config import RagConfig
from rag_platform.ingestion import build_index
from rag_platform.retrieval import HybridRetriever

COMPONENT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def built_index():
    return build_index(COMPONENT / "fixtures" / "knowledge-base", "idx_test_v1", RagConfig())


@pytest.fixture(scope="session")
def retriever(built_index):
    _, chunks = built_index
    return HybridRetriever(chunks, "idx_test_v1", RagConfig())
