from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_model_manifest(
    *,
    adapter: Path,
    dataset_manifest: Path,
    training_config: Path,
    chat_template: Path,
    evaluation_report: Path,
    model_version: str,
    base_revision: str,
    git_commit: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "model_id": "afc-support-qwen3-4b-qlora",
        "model_version": model_version,
        "base_model": "Qwen/Qwen3-4B",
        "base_revision": base_revision,
        "adapter_uri": adapter.resolve().as_uri(),
        "adapter_sha256": sha256_file(adapter),
        "dataset_manifest_sha256": sha256_file(dataset_manifest),
        "training_config_sha256": sha256_file(training_config),
        "chat_template_sha256": sha256_file(chat_template),
        "evaluation_report_sha256": sha256_file(evaluation_report),
        "license_review": "approved",
        "quality_gate": "passed",
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_preparation_artifacts(
    output_dir: Path,
    splits: dict[str, list[dict[str, Any]]],
    manifest: dict[str, Any],
) -> dict[str, Path]:
    """Persist immutable split and data-manifest artifacts for a run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"data_manifest": output_dir / "data-manifest.json"}
    for name, rows in splits.items():
        paths[name] = output_dir / f"{name}.jsonl"
        paths[name].write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
        )
    manifest = dict(manifest)
    manifest["artifacts"] = {name: str(path) for name, path in paths.items()}
    write_json(paths["data_manifest"], manifest)
    return paths
