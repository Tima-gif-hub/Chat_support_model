from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from model_preparation.artifacts import (  # noqa: E402
    write_json,
    write_preparation_artifacts,
)
from model_preparation.config import QLoRAConfig  # noqa: E402
from model_preparation.pipeline import load_jsonl, prepare_records  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CPU-safe preparation pipeline smoke")
    parser.add_argument("--fixture-check", action="store_true")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "fixtures" / "synthetic-training.jsonl",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs" / "qlora.yaml",
    )
    args = parser.parse_args()
    if not args.fixture_check:
        parser.error("the public CPU command requires --fixture-check")
    records = load_jsonl(args.fixture)
    if len(records) != 64:
        raise SystemExit(f"expected 64 static records, got {len(records)}")
    splits, manifest = prepare_records(records)
    if manifest["rejections"]:
        raise SystemExit(json.dumps(manifest["rejections"], indent=2))
    if args.output_dir:
        QLoRAConfig.load(args.config)
        paths = write_preparation_artifacts(args.output_dir, splits, manifest)
        manifest["artifacts"] = {name: str(path) for name, path in paths.items()}
        manifest["artifacts"]["qlora_config"] = str(args.config)
        write_json(paths["data_manifest"], manifest)
    print(
        json.dumps(
            {
                "fixture_records": len(records),
                "split_counts": {key: len(value) for key, value in splits.items()},
                "stage_counts": manifest["stage_counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
