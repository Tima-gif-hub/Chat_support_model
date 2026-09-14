from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RagConfig:
    embedding_dimensions: int = 768
    embedding_max_tokens: int = 512
    dense_candidates: int = 20
    lexical_candidates: int = 20
    rerank_candidates: int = 12
    max_results: int = 5
    max_evidence_tokens: int = 2400
    rrf_k: int = 60
    reranker_threshold: float = 0.35
    target_tokens: int = 420
    maximum_tokens: int = 512
    minimum_tokens: int = 80
    overlap_tokens: int = 64
    separator_order: tuple[str, ...] = ("heading", "paragraph", "sentence")
    preserve_title: bool = True
    preserve_heading_path: bool = True
    preserve_table_rows: bool = True
    hnsw_ef_search: int = 100

    @classmethod
    def from_toml(cls, path: Path) -> RagConfig:
        import tomllib

        values = tomllib.loads(path.read_text(encoding="utf-8"))
        rag = dict(values["rag"])
        if "separator_order" in rag:
            rag["separator_order"] = tuple(rag["separator_order"])
        return cls(**rag)
