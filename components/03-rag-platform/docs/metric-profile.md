# Retrieval profile

The RAG stage turns changing company material into permission-aware evidence, then returns stable citations to the support runtime. The public path uses synthetic documents and a deterministic local embedding so the retrieval boundary remains inspectable.

## Configuration

Chunking, candidate counts, reciprocal-rank fusion, evidence budgets, and reranker settings are recorded in [`configs/rag.toml`](../configs/rag.toml). The public benchmark fixture is in [`public-synthetic-benchmark.md`](evaluation/public-synthetic-benchmark.md). Index manifests carry source and retrieval hashes, document and chunk counts, ACL filters, embedding and reranker revisions, and quality-gate status.

> Illustrative values for the report layout; not production measurements.

| Metric | Value |
| --- | ---: |
| Recall@10 | 0.93 |
| MRR@10 | 0.81 |
| Citation precision | 0.97 |
| Citation recall | 0.93 |
| Groundedness | 0.94 |
| Retrieval latency, p95 | 650 ms |

Recall@10 is the fraction of labelled relevant passages retrieved among the top ten results, averaged per query. MRR@10 weights the rank of the first relevant result. Citation precision and recall measure citation correctness and coverage. Groundedness measures whether the answer is supported by returned evidence. Retrieval latency is the p95 elapsed retrieval path used by the integrated profile.

The next stage is [04 — integrating the support experience](../../04-support-runtime/README.md).
