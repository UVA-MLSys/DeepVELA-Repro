# Ontology model

## Layers

1. **Benchmark description:** software environment, problem specification and
   constraints, dataset, performance metrics, reference solution, and
   documentation.
2. **Workload obligations:** testable conditions required for a result to have
   its intended meaning.
3. **Implementation and execution:** bindings, actions, runtime sessions, and
   immutable attempts that claim to realize obligations.
4. **Evidence and decisions:** artifacts, checks, comparisons, discrepancies,
   invalidations, and acceptance decisions.

## Required relations

```text
benchmark has_component ontology_element
workload_obligation derived_from ontology_element_or_source
workload_obligation applies_to target
workload_obligation implemented_by implementation_binding
workload_obligation verified_by check
action realizes implementation_binding
action consumes artifact_or_pinned_input
attempt executes action_plan
attempt produces artifact
check consumes artifact
check verifies workload_obligation
artifact depends_on source_input_configuration_environment_or_artifact
comparison evaluates reproduced_result_against_reference
acceptance_decision supported_by check_or_comparison
change_or_discrepancy invalidates dependent_nodes
```

Use stable IDs. Record edges in `ontology/relations.jsonl`. An assertion is not
evidence unless it names a source or artifact, the obligation it concerns, and
the check that verifies the obligation.

## Graph invariants

- Every required obligation applies to at least one target and is source-
  grounded.
- Every planned action realizes at least one binding.
- Every binding implements at least one obligation.
- Every check consumes addressable artifacts and verifies named obligations.
- Every acceptance decision cites current checks or comparisons.
- Dependency edges used for invalidation are acyclic.
- Missing or conflicting facts remain explicit; they are never converted into
  inferred passing evidence.
