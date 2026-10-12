# Recovery and closure

Localize a failure before editing implementation or configuration. Record the
failed layer, affected nodes, evidence, hypotheses, resolution criteria, owner,
and retry budget.

For a change or discrepancy `delta`, compute the descendants of the changed
node in the dependency graph. Evidence inside that invalidation closure is
stale until regenerated and reverified. Preserve evidence outside the closure
only when producer identity, input digests, effective parameters, governing
obligations, verifier compatibility, and artifact integrity still match.

Retries create new attempt IDs. Do not patch a live attempt and resume its
identity.

Strict target acceptance requires:

```text
completed
AND every required obligation has a current passing check
AND the declared agreement policy is satisfied when required
AND no unresolved critical discrepancy remains
AND required artifacts are readable
```

A conformance-only campaign may mark agreement `unavailable` when no reference
result exists. A negative reproducibility study may close with a failed
comparison only when that outcome is permitted by the contract and fully
evidenced.

Close the campaign only when every target has an allowed terminal disposition,
the graph validates, reports read back successfully, and the stopping condition
is proven.
