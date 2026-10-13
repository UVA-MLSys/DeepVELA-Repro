# Telemetry and profiling

Profiling observes the reproduction method; it does not participate in the
scientific decision.

Record observable tool calls by stage, action, obligation, attempt, runtime,
outcome, error class, and retry relationship. Use provider-reported token counts
when available; otherwise record them as unavailable. Do not infer hidden
reasoning or reconstruct decision rounds.

Prefer normalized controller events. `ingest_agent_trace.py` also adapts
common cumulative token counters into non-overlapping usage deltas so repeated
snapshots are not double-counted. Keep tool-call events distinct from model
usage events.

Classify stage intervals as agent-active work, benchmark execution, scheduler
or service wait, human-blocked time, or instrumentation. Record resource samples
only when exposed by the actual runtime and link them to its hardware snapshot
and attempt.

Run `sample_runtime_resources.py` inside each benchmark runtime. Samples retain
units and an explicit aggregation rule for peak use, minimum free capacity,
last values, or cumulative-counter deltas. The profiler process is out of band:
its calls and elapsed time are excluded, while the measured benchmark resource
values remain reportable.

Telemetry serialization, validation, summarization, and profiler-only calls use
`instrumentation=true`. Exclude them from reproduction time, token totals, and
tool-call counts. Evidence and provenance recording are not instrumentation;
they are part of the reproduction method and remain included.

Every human intervention has one canonical `human_decision_id`. The telemetry
event and decision ledger use that same identity and record whether the event
counts toward the intervention metric. This prevents approvals, user-caused
connection delays, and scientific adjudications from being counted differently.

For controlled studies, record benchmark-readiness condition, withheld
ontology elements, controller realization, agent and reasoning configuration,
source and tool access, hardware, budgets, and intervention policy. Compare
fresh independent trials using observable outcomes and systems costs, not
private reasoning traces.

Materialize each condition from an allowlisted visible bundle and explicit
withheld paths. The bundle manifest proves file visibility and content digests;
the execution controller must separately enforce the declared network and
filesystem policy. Seal readiness scores through an assessor independent of the
execution agent before trials begin.
