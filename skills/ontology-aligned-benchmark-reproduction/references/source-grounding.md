# Source grounding

Prefer primary benchmark and model sources. Record source identity, revision,
retrieval time, digest when possible, authority role, and the exact ontology
elements or obligations supported.

## Authority order

Use benchmark-owned specifications, evaluator code, result publications,
datasets, and reference implementations before third-party summaries. A model
author's documentation may be authoritative for model-specific behavior while
the benchmark remains authoritative for evaluation semantics.

Classify each material field as:

- `human_decision`;
- `authoritative_source_fact`;
- `evidence_derived_fact`; or
- `unresolved`.

When sources conflict, record both claims, their identities, affected
obligations, and the decision required. Do not silently select the most
convenient value.

Resolve mutable branches, package ranges, datasets, checkpoints, and evaluator
references to the most immutable identity the source exposes. Record effective
defaults discovered in code separately from documented defaults.
