# System evaluation

The public evaluation set contains 300 versioned cases referenced by [`manifest.yaml`](manifest.yaml). Component-owned evaluators cover decision structure, retrieval relevance, grounded answers, and dependency behavior. Retrieval golden cases report fixture-based Recall@10 and MRR@10; decision and runtime cases describe contract coverage.

Release quality gates specify 100% valid decision JSON, complaint argument validity at least 0.99, zero unauthorized complaints, retrieval Recall@10 at least 0.90, citation precision at least 0.95, supported-claim groundedness at least 0.90, correct abstention at least 0.90, prompt-injection defense at least 0.98, zero prohibited mutations, and zero leaked thinking/repetition cases. These are blocking thresholds for a selected release evaluation, not measured production results. A semantic judge is optional and cannot override deterministic safety, tool, citation, or schema failures.

The benchmark cases are synthetic and versioned. They show reproducible public-code behavior rather than production model quality or business impact.

The evidence boundary and dated measured-run record are maintained in the [validation record](validation.md). It distinguishes synthetic fixture results from completed Compose and browser validation.
