---
name: builder-reproduce
description: Build and assess a scientific ML benchmark from reference artifacts, then hand the benchmark contract to Reproduce for execution and verification. Use for the Builder + Reproduce configuration.
---

# Builder + Reproduce

Use this skill when the benchmark contract is missing or spread across a paper, code, data, and
results. The output is a benchmark definition that `reproduce` can consume; it is not a
replacement for reproducing the reference solution.

This configuration requires the sibling `reproduce` skill to be installed.

The bundled `references/ontology.md`, `assets/`, and `scripts/` are the working source of truth
for the core workflow. Read the ontology before interviewing or scoring.

## 1. Inspect before interviewing

Read the repository, paper, README, dataset sample or schema, environment files, launchers,
metrics, reference outputs, and existing benchmark documentation. Record each finding with its
source path and section. Do not fill gaps by inference.

Map the evidence to five elements:

1. problem and constraints;
2. dataset, access, schema, version, and splits;
3. metrics, formulas, edge cases, direction, and aggregation;
4. reference solution, requirements, and expected outputs;
5. documentation and a clean-environment reproduction protocol.

Also identify the scientific domain and one primary AI/ML motif. If an element is absent or
ambiguous, ask the user for all such facts together.

- A missing task definition, dataset or split, metric, or reference output blocks a benchmark card.
- A missing wrapper or documentation file is a repairable implementation task.

## 2. Write the benchmark contract

Create or update the smallest repository-native set of artifacts that makes the contract explicit:

```text
<benchmark>/
  BENCHMARK_CARD.md       # task, data, constraints, metrics, reference, protocol
  DATA_SCHEMA.md          # fields, units, identifiers, splits, provenance
  metrics/score.py        # benchmark-owned metric implementation, if absent
  rubric.yaml             # evidence-backed completeness score, if requested
```

- Adapt an existing layout instead of moving working code.
- Every claim in the card names its source. Unknowns stay marked as unknown.
- Define exact formulas and behavior for empty predictions, ties, invalid values,
  per-target/per-class aggregation, and multi-objective tradeoffs where they apply.
- Do not select a convenient generic metric that does not match the task motif.

The reference solution must have a reproducible command, environment requirements, inputs,
outputs, and a benchmark-owned evaluator. If the command is not yet successful, hand off to
`reproduce` after the contract is complete.

## 3. Audit and score

When the user requests an audit, copy `assets/rubric_template.yaml` beside the benchmark and score
only evidence present in the artifacts.

- For every rubric item, write `met: true` or `met: false` and a path/section citation.
- Do not turn an unanswered item into a false score.
- Do not claim an endorsement threshold without the rubric's actual result.
- Report the gaps ordered by how cheaply each one closes a real contract defect.

Run the deterministic scorer from this skill directory:

```bash
python scripts/score_benchmark.py path/to/rubric.yaml --out SCORE_REPORT.md
```

Use `scripts/metrics.py` only for regression or classification tasks it actually supports; write a
benchmark-specific metric for other motifs.

## 4. Optional benchmark record

Only create a submission report when requested, using
`assets/submission_report_template.md`. External publication and competition packaging are outside
this skill's scope.

## Hand-off to reproduction

The hand-off is a completed benchmark card plus a successful or clearly specified reference command.
Call the Skill tool with skill `reproduce` once the card is written (reading its SKILL.md as a file does not invoke it); it reads the card in the workspace as part of its contract.

```text
benchmark card -> reproduce -> report.json and clean replay
```

Do not self-score a reproduction here. The benchmark-owned evaluator decides quality, and the
reproduction skill owns the canonical run and replay evidence.
