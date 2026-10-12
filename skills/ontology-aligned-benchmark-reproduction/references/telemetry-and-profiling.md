# Telemetry and profiling

Profiling observes the reproduction method; it does not participate in the
scientific decision.

Record observable tool calls by stage, action, obligation, attempt, runtime,
outcome, error class, and retry relationship. Use provider-reported token counts
when available; otherwise record them as unavailable. Do not infer hidden
reasoning or reconstruct decision rounds.

Classify stage intervals as agent-active work, benchmark execution, scheduler
or service wait, human-blocked time, or instrumentation. Record resource samples
only when exposed by the actual runtime and link them to its hardware snapshot
and attempt.

Telemetry serialization, validation, summarization, and profiler-only calls use
`instrumentation=true`. Exclude them from reproduction time, token totals, and
tool-call counts. Evidence and provenance recording are not instrumentation;
they are part of the reproduction method and remain included.

For controlled studies, record benchmark-readiness condition, withheld
ontology elements, controller realization, agent and reasoning configuration,
source and tool access, hardware, budgets, and intervention policy. Compare
fresh independent trials using observable outcomes and systems costs, not
private reasoning traces.
