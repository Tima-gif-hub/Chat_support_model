from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from model_preparation.artifacts import build_model_manifest


class ArtifactTests(unittest.TestCase):
    def test_manifest_hashes_every_owned_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = [
                root / name
                for name in ("adapter.bin", "data.json", "train.json", "chat.txt", "eval.json")
            ]
            for index, path in enumerate(files):
                path.write_text(f"artifact-{index}", encoding="utf-8")
            manifest = build_model_manifest(
                adapter=files[0],
                dataset_manifest=files[1],
                training_config=files[2],
                chat_template=files[3],
                evaluation_report=files[4],
                model_version="1.0.0+abc1234",
                base_revision="1cfa9a7208912126459214e8b04321603b3df60c",
                git_commit="abc1234",
            )
            self.assertEqual("approved", manifest["license_review"])
            self.assertEqual("passed", manifest["quality_gate"])
            self.assertEqual(64, len(manifest["adapter_sha256"]))


if __name__ == "__main__":
    unittest.main()
