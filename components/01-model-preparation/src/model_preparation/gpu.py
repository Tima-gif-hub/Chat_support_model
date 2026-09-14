"""A small, real CUDA adapter check used by the manual GPU dry-run.

The check intentionally uses a tiny trainable low-rank adapter instead of
pretending to train Qwen weights.  It exercises the same critical operational
properties (64 records, forward/backward, checkpoint, and resume) without
downloading a 4B model merely to validate a runner.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .pipeline import load_jsonl, prepare_records


def _record_features(records: list[dict[str, Any]], dimensions: int = 32) -> list[list[float]]:
    values: list[list[float]] = []
    for record in records:
        vector = [0.0] * dimensions
        for token in f"{record['question']} {record['answer']}".casefold().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0 if digest[4] & 1 else -1.0
        values.append(vector)
    return values


def run_gpu_dry_run(
    *, run_name: str, fixture: Path, output_dir: Path, torch_module: Any | None = None
) -> dict[str, Any]:
    """Run a 64-record forward/backward and verify a genuine resume.

    ``torch_module`` is injectable for focused orchestration tests; production
    callers leave it unset and therefore import the installed CUDA torch.
    """
    torch_api = torch_module
    if torch_api is None:
        try:
            import torch as imported_torch
        except ImportError as exc:  # pragma: no cover - optional GPU profile
            raise RuntimeError(
                "gpu-dry-run requires the optional GPU training environment"
            ) from exc
        torch_api = imported_torch
    torch = torch_api
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("gpu-dry-run requires a CUDA GPU with BF16 support")

    records = load_jsonl(fixture)
    if len(records) != 64:
        raise ValueError(f"gpu-dry-run requires the 64-record fixture, got {len(records)}")
    splits, data_manifest = prepare_records(records)
    if data_manifest["rejections"] or sum(map(len, splits.values())) != 64:
        raise ValueError("GPU fixture preparation rejected or dropped records")

    torch.manual_seed(42)
    device = torch.device("cuda")
    # A rank-4 adapter over hashed record features.  BF16 is used for the
    # actual matmuls, while the loss is accumulated in FP32 for stability.
    input_size, rank, classes = 32, 4, 5
    features = torch.tensor(_record_features(records), device=device, dtype=torch.bfloat16)
    labels = torch.tensor(
        [
            ["answer", "rag_answer", "clarify", "complaint_tool", "abstain"].index(
                record["expected_action"]
            )
            for record in records
        ],
        device=device,
        dtype=torch.long,
    )
    adapter_a = torch.nn.Parameter(
        torch.zeros((input_size, rank), device=device, dtype=torch.bfloat16)
    )
    adapter_b = torch.nn.Parameter(
        torch.zeros((rank, classes), device=device, dtype=torch.bfloat16)
    )
    torch.nn.init.normal_(adapter_a, std=0.02)
    torch.nn.init.zeros_(adapter_b)
    optimizer = torch.optim.AdamW((adapter_a, adapter_b), lr=2e-3)
    logits = features @ adapter_a @ adapter_b
    loss = torch.nn.functional.cross_entropy(logits.float(), labels)
    loss.backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    step = 1
    checkpoint_dir = output_dir / run_name
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = checkpoint_dir / "adapter_checkpoint.pt"
    torch.save(
        {
            "format": "tiny-qlora-dry-run-v1",
            "step": step,
            "records": len(records),
            "adapter_a": adapter_a.detach().cpu(),
            "adapter_b": adapter_b.detach().cpu(),
            "optimizer": optimizer.state_dict(),
        },
        checkpoint,
    )
    before_resume = (features @ adapter_a @ adapter_b).detach().float().cpu()

    restored_a = torch.nn.Parameter(
        torch.empty((input_size, rank), device=device, dtype=torch.bfloat16)
    )
    restored_b = torch.nn.Parameter(
        torch.empty((rank, classes), device=device, dtype=torch.bfloat16)
    )
    restored_optimizer = torch.optim.AdamW((restored_a, restored_b), lr=2e-3)
    state = torch.load(checkpoint, map_location=device, weights_only=False)
    if state.get("records") != 64 or state.get("format") != "tiny-qlora-dry-run-v1":
        raise RuntimeError("checkpoint metadata failed resume validation")
    restored_a.data.copy_(state["adapter_a"].to(device=device, dtype=torch.bfloat16))
    restored_b.data.copy_(state["adapter_b"].to(device=device, dtype=torch.bfloat16))
    restored_optimizer.load_state_dict(state["optimizer"])
    after_resume = (features @ restored_a @ restored_b).detach().float().cpu()
    if not torch.equal(before_resume, after_resume) or state.get("step") != step:
        raise RuntimeError("resumed adapter state differs from saved checkpoint")

    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    result = {
        "run_name": run_name,
        "fixture_records": 64,
        "device": torch.cuda.get_device_name(0),
        "forward_backward": "passed",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": digest,
        "resume": "passed",
        "step": step,
    }
    (checkpoint_dir / "gpu-dry-run-manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
