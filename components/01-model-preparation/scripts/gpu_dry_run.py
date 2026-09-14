from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit GPU-only adapter resumability check")
    parser.add_argument("--run-name", required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "fixtures" / "synthetic-training.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/gpu-dry-run"))
    args = parser.parse_args()
    if os.getenv("MODEL_PREPARATION_GPU_DRY_RUN") != "1":
        raise SystemExit(
            "set MODEL_PREPARATION_GPU_DRY_RUN=1 on an explicitly configured GPU runner"
        )
    from model_preparation.gpu import run_gpu_dry_run

    try:
        result = run_gpu_dry_run(
            run_name=args.run_name, fixture=args.fixture, output_dir=args.output_dir
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
