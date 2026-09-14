from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from model_serving.manifest import verify_manifest


class ManifestTests(unittest.TestCase):
    def test_local_adapter_checksum_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "adapter.bin"
            adapter.write_bytes(b"approved-adapter")
            digest = hashlib.sha256(adapter.read_bytes()).hexdigest()
            manifest = {
                "schema_version": "1.0",
                "model_id": "afc-support-qwen3-4b-qlora",
                "model_version": "1.0.0",
                "base_model": "Qwen/Qwen3-4B",
                "base_revision": "1cfa9a7",
                "adapter_uri": adapter.resolve().as_uri(),
                "adapter_sha256": digest,
                "dataset_manifest_sha256": "a" * 64,
                "training_config_sha256": "b" * 64,
                "chat_template_sha256": "c" * 64,
                "evaluation_report_sha256": "d" * 64,
                "license_review": "approved",
                "quality_gate": "passed",
                "created_at": "2026-01-01T00:00:00Z",
                "git_commit": "abc1234",
            }
            verify_manifest(manifest)
            manifest["adapter_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
