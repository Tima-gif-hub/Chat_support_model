from __future__ import annotations

import json
from pathlib import Path


def test_runtime_evaluation_fixture_has_75_unique_owned_cases():
    path = Path(__file__).parents[1] / "fixtures" / "evaluation" / "runtime-cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 75
    assert len({case["case_id"] for case in cases}) == 75
    assert all(set(case) == {"case_id", "family", "message", "expected"} for case in cases)
