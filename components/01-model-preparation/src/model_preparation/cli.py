from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .artifacts import build_model_manifest, write_json
from .pipeline import load_jsonl, prepare_records


def main() -> int:
    parser = argparse.ArgumentParser(description="CPU-safe model preparation commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-fixture")
    validate.add_argument("fixture", type=Path)
    validate.add_argument("--output", type=Path)
    gpu = subparsers.add_parser("gpu-dry-run")
    gpu.add_argument("fixture", type=Path)
    gpu.add_argument("--run-name", default="manual")
    gpu.add_argument("--output-dir", type=Path, default=Path("artifacts/gpu-dry-run"))
    manifest_command = subparsers.add_parser("build-manifest")
    manifest_command.add_argument("--adapter", type=Path, required=True)
    manifest_command.add_argument("--dataset-manifest", type=Path, required=True)
    manifest_command.add_argument("--training-config", type=Path, required=True)
    manifest_command.add_argument("--chat-template", type=Path, required=True)
    manifest_command.add_argument("--evaluation-report", type=Path, required=True)
    manifest_command.add_argument("--output", type=Path, required=True)
    manifest_command.add_argument("--model-version", required=True)
    manifest_command.add_argument("--base-revision", required=True)
    manifest_command.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    if args.command == "gpu-dry-run":
        if os.environ.get("MODEL_PREPARATION_GPU_DRY_RUN") != "1":
            parser.error(
                "set MODEL_PREPARATION_GPU_DRY_RUN=1 on an explicitly configured GPU runner"
            )
        from .gpu import run_gpu_dry_run

        try:
            result = run_gpu_dry_run(
                run_name=args.run_name, fixture=args.fixture, output_dir=args.output_dir
            )
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "build-manifest":
        manifest_value = build_model_manifest(
            adapter=args.adapter,
            dataset_manifest=args.dataset_manifest,
            training_config=args.training_config,
            chat_template=args.chat_template,
            evaluation_report=args.evaluation_report,
            model_version=args.model_version,
            base_revision=args.base_revision,
            git_commit=args.git_commit,
        )
        write_json(args.output, manifest_value)
        print(json.dumps(manifest_value, sort_keys=True))
        return 0
    _, data_manifest = prepare_records(load_jsonl(args.fixture))
    if args.output:
        write_json(args.output, data_manifest)
    print(json.dumps(data_manifest, sort_keys=True))
    return 0 if not data_manifest["rejections"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
