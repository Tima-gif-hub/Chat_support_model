# Data lineage

The checked-in corpus is a static 64-record synthetic fixture licensed CC0-1.0. It exists only to exercise validation, normalization, leakage-safe splitting, rendering, and trainer orchestration without production data or model downloads.

The production experience represented used 39,401 accepted English-primary records: 1,032 private, 31,234 public, and 7,135 teacher-generated. Those records are not included. The recorded split was 27,581 train records (approximately 70%), 5,910 validation records (approximately 15%), and 5,910 evaluation records (approximately 15%). Splitting was grouped by semantic cluster, class, and source with seed 42 so paraphrases could not cross splits.

The 7,135 teacher-generated records were distributed across 3,924 grounded FAQ/RAG answers, 1,070 complaints and tool calls, 714 clarification cases, 714 abstention/out-of-scope/safety cases, and 713 direct-style/general-help cases. The reference run used teacher alias `5.6 Luna`, extra-high reasoning effort, and temperature `0.3`; these are provenance details for that production dataset, not claims about the public deterministic simulator.

The data manifest records stage counts, rejection reasons, split ownership, seed 42, source provenance, and immutable input hashes for each training run.
