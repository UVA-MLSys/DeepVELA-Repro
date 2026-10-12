# Execution and effects

## Preflight

Check source and input availability, storage, permissions, runtime capability,
dependency resolution, evaluator accessibility, artifact publication, and
observability before expensive work. Use small, risk-targeted tests rather than
using the full cohort as the first smoke test.

## Runtime identity

Treat the control environment and every benchmark or evaluator environment as
separate runtime sessions. Record requested, provider-allocated, directly
observed, inferred, and unavailable fields separately. Capture hardware and
software from inside the runtime that actually executes the workload.

A reconnect, scheduler reallocation, or runtime replacement creates a new
runtime-session identity. Do not reuse the control host's hardware record for a
remote benchmark attempt.

## Immutable attempts

Register an attempt before consequential execution. It records the action-plan
digest, input identities, effective configuration, runtime session, hardware
snapshot, timing, and terminal state. A retry is a new attempt; never overwrite
the previous attempt or its artifacts.

## Artifacts

Record role, producer attempt, dependencies, location, digest, media type,
size, and read-back status. Publish terminal manifests atomically when
possible. Logs, forecasts, labels, evaluator inputs, and metric outputs should
remain separately addressable when the benchmark exposes them.

The scripts in this skill do not run benchmarks. Use the authorized execution
mechanism, then register observed effects and artifacts in the neutral campaign
records.
