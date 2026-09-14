from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_preparation.pipeline import load_jsonl, prepare_records, split_for_cluster
from model_preparation.records import validate_record

COMPONENT = Path(__file__).parents[1]


class PipelineTests(unittest.TestCase):
    def test_static_fixture_has_64_valid_synthetic_records(self) -> None:
        records = load_jsonl(COMPONENT / "fixtures/synthetic-training.jsonl")
        self.assertEqual(64, len(records))
        for record in records:
            validate_record(record)
            self.assertTrue(record["synthetic_data"])

    def test_pipeline_is_deterministic_and_cluster_safe(self) -> None:
        records = load_jsonl(COMPONENT / "fixtures/synthetic-training.jsonl")
        first, manifest = prepare_records(records)
        second, second_manifest = prepare_records(records)
        self.assertEqual(first, second)
        self.assertEqual(manifest, second_manifest)
        self.assertEqual(64, manifest["stage_counts"]["rendered"])
        clusters: dict[str, str] = {}
        for row in manifest["split_records"]:
            previous = clusters.setdefault(row["semantic_cluster_id"], row["split"])
            self.assertEqual(previous, row["split"])
            self.assertEqual(42, row["seed"])

    def test_duplicate_and_pii_are_rejected(self) -> None:
        record = load_jsonl(COMPONENT / "fixtures/synthetic-training.jsonl")[0]
        pii = dict(record)
        pii["record_id"] = "pii"
        pii["semantic_cluster_id"] = "pii-cluster"
        pii["question"] = "Email me at person@example.com"
        _, manifest = prepare_records([record, dict(record), pii])
        self.assertEqual(1, manifest["stage_counts"]["rendered"])
        reasons = {item["reason"] for item in manifest["rejections"]}
        self.assertIn("exact duplicate", reasons)
        self.assertIn("PII detected", reasons)

    def test_locked_configuration_matches_required_values(self) -> None:
        config = json.loads((COMPONENT / "configs/qlora.yaml").read_text(encoding="utf-8"))
        lock = json.loads((COMPONENT / "configs/model.lock.yaml").read_text(encoding="utf-8"))
        self.assertEqual(42, config["seed"])
        self.assertEqual(4096, config["max_sequence_length"])
        self.assertEqual("bfloat16", config["quantization"]["compute_dtype"])
        self.assertEqual(lock["revision"], config["base_model_revision"])
        self.assertEqual(40, len(lock["revision"]))
        self.assertEqual(split_for_cluster("same"), split_for_cluster("same"))


if __name__ == "__main__":
    unittest.main()
