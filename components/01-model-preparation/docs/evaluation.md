# Offline evaluation

Model quality is evaluated outside the pull-request path against versioned cases for decision structure, action and complaint classification, style, leakage, repetition, and refusal behavior. A model manifest may say `quality_gate: passed` only after the owned report passes its release thresholds and license review is approved.

The CPU fixture test is pipeline coverage, not a model-quality result. The manual GPU dry-run proves forward/backward execution, checkpoint creation, and resume behavior but does not promote an adapter.

## Public reconstruction settings

The public reconstruction is configured around `Qwen/Qwen3-4B` with the non-thinking chat template (`enable_thinking=False`) and an 8,192-token application budget. Its QLoRA configuration records seed 42, a 4,096-token training sequence, packed examples, assistant-only loss, 4-bit NF4 quantization with double quantization and BF16 compute, LoRA rank 16, alpha 32, dropout 0.05, and target modules `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, and `down_proj`.

The public optimization profile is two epochs, learning rate `0.0002`, micro-batch size 2, gradient accumulation 16 (effective batch size 32 per replica), paged AdamW 8-bit, cosine scheduling, warmup ratio `0.03`, weight decay `0.01`, maximum gradient norm `0.3`, gradient checkpointing, and BF16. Evaluation and checkpoint intervals are 100 steps, with three checkpoints retained and best-model selection by evaluation loss. These are public reconstruction settings; no historical production training run or public model weights are claimed here.
