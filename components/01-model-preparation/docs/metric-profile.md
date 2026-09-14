# Model preparation profile

The preparation stage covered data validation, leakage-safe splitting, QLoRA training, and offline support-behavior evaluation. The public workflow exposes the configuration and fixture path; the trained artifact and private records remain outside the repository.

## Configuration

The base model, seed, quantization, adapter, optimizer, and checkpoint policy are recorded in [`configs/qlora.yaml`](../configs/qlora.yaml). Data ownership and split rules are described in [`data-lineage.md`](data-lineage.md), and the evaluation boundary is in [`evaluation.md`](evaluation.md).

> Illustrative values for the report layout; not production measurements.

| Metric | Value |
| --- | ---: |
| Class macro-F1 | 0.91 |
| Intent macro-F1 | 0.89 |
| Complaint precision | 0.98 |
| Complaint recall | 0.96 |

Class macro-F1 is the unweighted mean of per-class F1. Intent macro-F1 is the unweighted mean of per-intent F1 across the support-intent taxonomy. Complaint precision is the share of complaint predictions that are complaints; complaint recall is the share of complaint cases detected.

The next stage is [02 — serving an approved model](../../02-model-serving/README.md).
