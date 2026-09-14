from pathlib import Path

from rag_platform.evaluation import evaluate


def test_retrieval_golden_suite_has_60_cases_and_passes_release_gates() -> None:
    component = Path(__file__).resolve().parents[1]
    report = evaluate(
        component / "fixtures" / "knowledge-base",
        component / "fixtures" / "evaluation" / "retrieval-golden-v1.jsonl",
    )
    assert report["case_count"] == 60
    assert report["recall_at_10"] >= 0.90
    assert report["mrr_at_10"] >= 0.75
    assert report["quality_gate"] == "passed"
