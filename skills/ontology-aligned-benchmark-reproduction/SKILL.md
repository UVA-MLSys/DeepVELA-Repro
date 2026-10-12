---
name: ontology-aligned-benchmark-reproduction
description: Reproduce or audit scientific benchmarks by connecting benchmark specifications to executable workload obligations, implementation bindings, runtime evidence, deterministic verification, selective invalidation, and evidence-based closure. Use for benchmark reproduction campaigns where accepted results must be traceable and independently inspectable.
---

# Ontology-aligned benchmark reproduction

Use this skill to reproduce or audit a benchmark without embedding benchmark-
specific answers or depending on a particular agent platform.

## Invariants

1. Instantiate the benchmark ontology before expensive execution.
2. Link every consequential action to at least one workload-obligation ID.
3. Keep benchmark-readiness assessment separate from reproduction acceptance.
4. Classify material facts as `human_decision`,
   `authoritative_source_fact`, `evidence_derived_fact`, or `unresolved`.
5. Freeze the verification policy before inspecting the full result cohort.
6. Register an immutable attempt before consequential execution.
7. Treat an artifact as evidence only after a declared check consumes it and
   verifies a named obligation.
8. Keep completion, validity, agreement, and canonical selection separate.
9. After a change, invalidate dependent evidence before reusing unaffected
   artifacts.
10. Close only when deterministic validation proves the declared stopping
    condition. An agent statement that work is complete is insufficient.

Do not add benchmark profiles, expected scores, model lists, launch commands,
or platform configuration to this package. Put them in the campaign workspace.
Do not widen a comparator or tolerance after viewing results unless a human
approves an amendment and the previous verification evidence is invalidated.

## Workflow

### 0. Establish scope

Read [contract-and-planning.md](references/contract-and-planning.md). Fix the
authorized objective, intended claim, finite targets, permissions, resource and
retry budgets, human-decision boundaries, verification policy, and stopping
condition. Bootstrap a campaign workspace with `scripts/bootstrap_campaign.py`.

Exit only when unresolved fields that could change scientific meaning or
external effects are explicit.

### 1. Instantiate the benchmark ontology

Read [ontology-model.md](references/ontology-model.md) and
[source-grounding.md](references/source-grounding.md). Assess the benchmark
under the six MLCommons-aligned categories, create ontology elements, and turn
authoritative requirements into testable workload obligations. Record missing
or conflicting specification as gaps or discrepancies.

Exit only when every target has an obligation set and every factual obligation
is grounded in an authoritative source.

### 2. Bind obligations to implementation

Create implementation bindings and an action plan. Every action must realize a
binding, and every binding must name the obligations it claims to implement.
Choose the evidence-supported execution mode: authoritative execution,
authoritative-versus-reusable comparison, or conformance-only evaluation.

Exit only when every required obligation is implemented or explicitly limits
the claim.

### 3. Execute and record effects

Read [execution-and-effects.md](references/execution-and-effects.md). Run
bounded preflight checks, register runtime sessions, capture observed hardware
and software from the environment that will execute the workload, and register
an immutable attempt. Execute through available tools, retain outputs and logs,
record effective configuration, and verify artifact read-back.

Exit only when the attempt is terminal and its artifacts are independently
addressable.

### 4. Verify

Read [evidence-and-verification.md](references/evidence-and-verification.md).
Use the benchmark-owned evaluator or a separately frozen verifier. Apply the
declared policy at the finest shared result grain. Record checks, comparisons,
and discrepancies, including missing evidence.

Exit only when every required obligation is passed, failed, or explicitly
unresolved.

### 5. Recover or close

Read [recovery-and-closure.md](references/recovery-and-closure.md). For a repair,
compute the invalidation closure, retain only evidence proven compatible, and
regenerate affected descendants. Otherwise run `decide_acceptance.py` and
`close_campaign.py`.

Close only when each target has an allowed terminal disposition and all claims
are supported by current, readable evidence.

## Campaign records

Use the six schema modules under `assets/schemas/`: `campaign`, `ontology`,
`execution`, `verification`, `telemetry`, and `experiment`. Each module retains
its logical record types as named `$defs`. Read
[campaign-layout.md](references/campaign-layout.md) before creating or resuming
a campaign. Run `scripts/validate_ontology_graph.py` at every phase boundary.

For profiling or controlled studies, read
[telemetry-and-profiling.md](references/telemetry-and-profiling.md). Telemetry
collection is instrumentation and is excluded from reproduction cost. Required
scientific evidence and provenance recording remain part of that cost.
