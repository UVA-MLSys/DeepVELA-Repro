# Evidence and verification

An artifact is an output. It becomes evidence only when a declared check
consumes it, verifies named obligations, and records a current result.
Content-addressed storage may deduplicate identical bytes, but never merges
their logical evidence records or provenance.

Prefer the benchmark-owned evaluator. If a separate verifier is used, freeze
its identity and policy before inspecting the complete cohort. Keep evaluator
implementation independent from the reproduced implementation when practical.

Verify at the finest shared grain. Aggregate agreement cannot hide missing
targets or failed secondary metrics. Comparisons must declare join keys,
comparator, tolerance, aggregation, missing-result policy, and both compared
artifact identities.

Keep these states separate:

- `completed`: execution reached a terminal state;
- `valid`: required structure and workload conditions hold;
- `agreed`: the declared result comparator passed;
- `canonical`: the result was selected for publication or downstream use.

For stochastic workloads, apply the frozen replicate, seed, uncertainty, and
equivalence policy. Missing replicate coverage is incomplete evidence, not an
inferred pass.

Create a discrepancy for failed checks, ambiguous joins, source conflicts,
missing evidence, unsupported transformations, or unreadable artifacts.
