from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

if __package__:
    from .ingestion import build_index
    from .models import RetrievalContext
    from .retrieval import HybridRetriever
else:  # pragma: no cover - convenience for the documented direct script form
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag_platform.ingestion import build_index  # noqa: E402
    from rag_platform.models import RetrievalContext  # noqa: E402
    from rag_platform.retrieval import HybridRetriever  # noqa: E402


def evaluate(source_dir: Path, cases_path: Path) -> dict[str, object]:
    _, chunks = build_index(source_dir, "idx_evaluation_v1")
    retriever = HybridRetriever(chunks, "idx_evaluation_v1")
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    reciprocal_ranks: list[float] = []
    hits = 0
    returned = 0
    relevant_returned = 0
    failures = []
    for case in cases:
        context = RetrievalContext(
            case["workspace_id"],
            case["audience"],
            case["language"],
            datetime.fromisoformat(case["as_of"].replace("Z", "+00:00")),
        )
        response = retriever.retrieve(case["query"], context)
        expected = set(case["expected_document_ids"])
        rank = next(
            (
                rank
                for rank, item in enumerate(response.evidence, 1)
                if item.document_id in expected
            ),
            None,
        )
        hits += int(rank is not None)
        returned += len(response.evidence)
        relevant_returned += sum(item.document_id in expected for item in response.evidence)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        if rank is None:
            failures.append(case["case_id"])
    count = len(cases)
    recall = hits / count if count else 0.0
    mrr = sum(reciprocal_ranks) / count if count else 0.0
    precision = relevant_returned / returned if returned else 0.0
    # Retrieval responses are contractually capped at five chunks, so naming
    # this Recall/MRR@5 is important: @10 would claim a rank window the API
    # never returns.  The legacy aliases remain for consumers of the first
    # public fixture report and are not used for gating.
    result = {
        "result_family": "public_synthetic_benchmark",
        "fixture_version": "rag-retrieval-v1",
        "case_count": count,
        "retrieval_k": 5,
        "recall_at_5": round(recall, 4),
        "mrr_at_5": round(mrr, 4),
        "precision_at_5": round(precision, 4),
        "precision_recall_curve": [
            {
                "threshold": retriever.config.reranker_threshold,
                "precision_at_5": round(precision, 4),
                "recall_at_5": round(recall, 4),
            }
        ],
        "threshold": retriever.config.reranker_threshold,
        "quality_gate": "passed" if recall >= 0.90 and mrr >= 0.75 else "failed",
        "failed_case_ids": failures,
    }
    # Compatibility for the original report shape.  These values are aliases
    # of the API's actual top-5 result, never a fabricated top-10 query.
    result["recall_at_10"] = result["recall_at_5"]
    result["mrr_at_10"] = result["mrr_at_5"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("cases", type=Path)
    args = parser.parse_args()
    report = evaluate(args.source, args.cases)
    print(json.dumps(report, indent=2))
    return 0 if report["quality_gate"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
