from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

REQUIRED = {
    "schema_version",
    "model_id",
    "model_version",
    "base_model",
    "base_revision",
    "adapter_uri",
    "adapter_sha256",
    "dataset_manifest_sha256",
    "training_config_sha256",
    "chat_template_sha256",
    "evaluation_report_sha256",
    "license_review",
    "quality_gate",
    "created_at",
    "git_commit",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(value: dict[str, Any], *, verify_adapter: bool = True) -> None:
    missing = REQUIRED - value.keys()
    if missing:
        raise ValueError(f"manifest missing fields: {sorted(missing)}")
    if set(value) != REQUIRED:
        raise ValueError("manifest contains unsupported fields")
    if value["schema_version"] != "1.0" or value["base_model"] != "Qwen/Qwen3-4B":
        raise ValueError("unsupported model manifest")
    for field in ("model_id", "model_version", "adapter_uri", "git_commit"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"invalid model manifest identity: {field}")
    if not isinstance(value["base_revision"], str) or len(value["base_revision"]) < 7:
        raise ValueError("invalid model manifest base revision")
    if value["license_review"] != "approved" or value["quality_gate"] != "passed":
        raise ValueError("model artifact is not approved")
    checksums = [key for key in REQUIRED if key.endswith("_sha256")]
    if any(
        not isinstance(value[key], str)
        or len(value[key]) != 64
        or set(value[key]) - set("0123456789abcdef")
        for key in checksums
    ):
        raise ValueError("invalid manifest checksum")
    if verify_adapter:
        parsed = urlparse(value["adapter_uri"])
        if parsed.scheme != "file":
            raise ValueError("local verification requires a file adapter URI")
        raw_path = unquote(parsed.path)
        # pathlib emits a Windows file URI; the leading slash is URI syntax,
        # not part of the local drive path.
        if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
        adapter = Path(raw_path)
        if not adapter.exists() or _sha256(adapter) != value["adapter_sha256"]:
            raise ValueError("adapter checksum mismatch")


def load_manifest(path: Path, *, verify_adapter: bool = True) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    verify_manifest(value, verify_adapter=verify_adapter)
    return value
