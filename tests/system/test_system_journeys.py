"""Cross-boundary tests only: RAG, model serving, runtime and manager queue."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        assert not line.startswith("+"), f"{path}:{number} has patch marker, not JSONL"
        if line.strip():
            value = json.loads(line)
            assert isinstance(value, dict)
            rows.append(value)
    return rows


def test_system_fixture_ownership_manifest_is_complete() -> None:
    grounded = _jsonl(ROOT / "tests/system/fixtures/grounded-answers.jsonl")
    failures = _jsonl(ROOT / "tests/system/fixtures/dependency-failures.jsonl")
    assert len(grounded) == 80
    assert len(failures) == 15
    assert len({row["case_id"] for row in grounded + failures}) == 95
    for row in grounded:
        assert row["family"] == "grounded_answer"
        assert row["expected_action"] == "rag_answer"
        assert row["expected_document_ids"]
        assert row["required_facts"] and row["forbidden_claims"]
        assert set(row["owner_components"]) == {"03-rag-platform", "04-support-runtime"}
    for row in failures:
        assert row["family"] == "dependency_failure"
        assert row["dependency"] in {"rag", "model_decision", "model_answer"}
        assert row["must_preserve_conversation"] is True
        assert row["must_not_submit_complaint"] is True


def test_assembled_runtime_rag_model_journeys_and_queue() -> None:
    """The root test crosses three service owners and verifies persisted queue visibility."""
    from scripts.system_smoke import in_process_smoke

    assert in_process_smoke() == 0


def test_root_evaluator_executes_all_owner_cases_and_applies_gates() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate.py"), "--suite", "public-synthetic-300"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(completed.stdout)
    assert report["total_cases"] == report["executed_cases"] == 300
    assert report["quality_gate"] == "passed"
    assert report["failures"] == []
    assert all(gate["passed"] for gate in report["quality_gates"].values())
