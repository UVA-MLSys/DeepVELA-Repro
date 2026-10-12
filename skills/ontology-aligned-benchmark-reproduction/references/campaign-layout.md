# Campaign layout

Use these logical roles even if a database or object store replaces the
filesystem:

```text
campaign/
  contract/       campaign contract, readiness assessment, verification policy,
                  and target manifest
  ontology/       elements, obligations, bindings, and relations
  sources/        source manifest, conflicts, and retrieved materials
  planning/       action, resource, risk, and preflight plans
  runtimes/       runtime sessions and hardware/software snapshots
  attempts/       immutable attempt manifests, effects, artifacts, terminals
  verification/   checks, comparisons, and discrepancies
  decisions/      acceptance and human decisions
  state/          campaign state and invalidations
  telemetry/      tool calls, spans, interventions, resource samples, summary
  experiment/     experiment condition and trial summary
  reports/        machine-readable and narrative results
```

Use JSON for singleton records and JSONL for append-oriented collections. Keep
IDs globally unique within a campaign. Store relative artifact paths when the
campaign is portable. Hash files with SHA-256 and verify read-back before they
support acceptance.

Resume from persisted state, not chat history. Before resuming, validate record
schemas, file readability, graph edges, invalidation state, and the last phase
exit condition.
