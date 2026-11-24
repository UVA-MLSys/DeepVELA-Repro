"""Domain-neutral evaluation models for rubric bundles and scored runs.

Nothing here may hardcode a phase ID, rubric ID, or domain metric name -- those are always
resolved from the rubric bundle (`skills/agent-evaluation-profile/`). Scoring protocol:
`skills/agent-evaluation-profile/references/protocol.md`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GuidanceExposure = Literal["phase_labels_only", "self_check_feedback", "rubric_claims_exposed"]
SuiteRole = Literal["development", "regression", "held_out"]
Verdict = Literal["pass", "fail", "not_applicable"]
# Intervention types an LLM judge assigns from the recorded context (protocol.md, "Effort").
InterventionType = Literal["clarification", "error-fixing", "correction", "approval"]
ExecutionOutcome = Literal["ok", "exit_nonzero", "timed_out", "backgrounded", "interrupted", "tool_error", "harness_denied"]
UsageQuality = Literal["measured", "estimated", "unavailable"]


class EvaluationPhase(BaseModel):
    """One phase entry of a bundle's `bundle.yaml`. `id` and `label` are bundle content, not a
    library enum -- a new domain defines its own phase list in that profile's `bundle.yaml`
    without touching this model."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    rubric_templates: list[str] = Field(default_factory=list)


class EvaluationProfile(BaseModel):
    """A bundle's `bundle.yaml` identity and phase list, plus the bundle digest it was read at.
    `profile_id` is also the bundle's directory name under the bundle root."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    profile_version: int
    phases: list[EvaluationPhase]
    guidance_exposure: GuidanceExposure = "phase_labels_only"


class QualityContract(BaseModel):
    """The domain's terminal correctness oracle, explicit rather than a bare number or prose
    verdict.

    Deliberately metric-agnostic: `result_name_type_and_direction` and `acceptance_rule` are
    free-text, authored per task from that task's own documentation (e.g. "mean_dice, float,
    higher_is_better" for one MLPerf workload, "F1, float, higher_is_better" for another). Many
    tasks under the same `EvaluationProfile` can have entirely different metrics -- the profile
    fixes phase structure, not metric identity. See "One profile, many metrics" in
    rubric-authoring.md."""

    model_config = ConfigDict(extra="forbid")

    identity: dict[str, Any] = Field(default_factory=dict)
    evaluator_identity: str
    result_name_type_and_direction: str
    reference_value: float | dict[str, float] | None = None
    expected_verdict: str | None = None
    acceptance_rule: str
    source_path_sha256_excerpt: dict[str, str]
    matching_external_anchors: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceContract(BaseModel):
    """What a `PhaseRubric`'s checker is allowed to consume: workspace artifacts, the transcript's
    command outputs, and `report.json` -- evidence every arm produces the same way, never a record
    one arm's skill asks the agent to write (protocol.md, "Scores"). Consuming anything outside
    this contract is a checker defect, not a passing check."""

    model_config = ConfigDict(extra="forbid")

    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class PhaseRubric(BaseModel):
    """One independently checkable atomic claim, authored per rubric-authoring.md."""

    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    phase_id: str
    claim: str
    critical: bool
    source_refs: list[dict[str, str]] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    checker: dict[str, Any]  # {kind, args}; untyped so a task can pick the check its own metric
    # needs (e.g. a relative-error check for one workload's metric, a different threshold
    # direction for another's) without a schema or library change -- see QualityContract above.
    evidence_contract: EvidenceContract
    applicable: bool = True
    pass_threshold: float = 1.0
    # The target (task `targets` key) this rubric scores, or null for a rubric shared by every
    # target that lists it, directly or through `prerequisites`.
    target: str | None = None
    # Cache conditions this rubric applies under. Absent or empty means "applies under every
    # cache condition."
    cache_conditions: list[str] = Field(default_factory=list)


class InputReuseContract(BaseModel):
    """What may be inherited from a shared cache without counting as reused generated work."""

    model_config = ConfigDict(extra="forbid")

    cache_condition_id: str
    allowed_cache_roots: list[str] = Field(default_factory=list)
    allowed_artifact_classes: list[str] = Field(default_factory=list)
    required_identity_and_hashes: list[dict[str, str]] = Field(default_factory=list)
    package_cache_class: str | None = None
    forbidden_artifact_classes: list[str] = Field(default_factory=list)
    initial_workspace_manifest: str | None = None
    external_visible_path_manifest: str | None = None


class AuthoredBy(BaseModel):
    """Author identity for a rubric bundle/task manifest -- part of the comparison identity so
    runs scored by different authors or bundle versions are never pooled."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    authored_at: str
    source_revision: str
    reviewed_by: str = "pending"


class TargetSpec(BaseModel):
    """One independently scored result of a multi-target task (evaluation protocol, Tasks section):
    its own quality contract and quality rubric. `shared_rubrics` names the target-less rubrics its
    rubrics depend on; the bundle loader checks it against the `prerequisites` closure."""

    # Other keys are the target's identity (model, dataset, scenario, evaluator ...), as in the
    # single-target manifest's `domain_identity`; they are descriptive and never read by a checker.
    model_config = ConfigDict(extra="allow")

    quality_rubric_id: str
    quality_contract: QualityContract
    shared_rubrics: list[str] = Field(default_factory=list)


class EvaluationTask(BaseModel):
    """The frozen per-task manifest, prepared independently of the evaluated agent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    task_id: str
    evaluation_profile_id: str
    evaluation_profile_version: int
    domain_identity: dict[str, Any] = Field(default_factory=dict)
    # Exactly one of `quality_contract` + `quality_rubric_id` (one result) or `targets` (several).
    quality_contract: QualityContract | None = None
    source_revision: str
    objective: str
    task_family: str
    resource_budget: dict[str, Any] = Field(default_factory=dict)
    benchmark_contract_sources: list[dict[str, str]] = Field(default_factory=list)
    phases: list[PhaseRubric]
    suite_role: SuiteRole
    input_reuse_contract: InputReuseContract
    authored_by: AuthoredBy
    injected_failure: dict[str, Any] | None = None
    manifest_version: int = 1
    reviewer_and_review_date: str | None = None
    # Semantic artifact name -> path, relative to the run's `repo/` directory, e.g.
    # {"kits19_raw_data_dir": "kits19_raw_data_dir", "mlperf_log_accuracy_json":
    # "build/logs/mlperf_log_accuracy.json"}. These paths are fixed by the benchmark's own
    # Makefile/README, so they're authored once here alongside the rest of the task manifest, not
    # inferred by a checker or hardcoded in this package -- a rubric's `path_from:
    # manifest.inputs.<name>` / `manifest.outputs.<name>` resolves through this dict (see
    # evaluation/checkers.py). A rubric whose path_from has no entry here reports a checker
    # defect, not a false pass or fail.
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    # The rubric whose checker decides the task's quality result, named at setup; the scorer
    # reports its metric as `quality_result`.
    quality_rubric_id: str | None = None
    targets: dict[str, TargetSpec] = Field(default_factory=dict)
    # Regexes for what a run may not access (protocol.md, "What the agent may not see"): the
    # task's published results and the bundle root. A transcript access matching one fails the monitor.
    forbidden_access: list[str] = Field(default_factory=list)
    # The dataset record (`dataset/tasks/<source_id>.json`) the task prompt was rendered from;
    # `evaluation.prepare` takes its `policy.compute` as the default Compute wording. Absent in bundles
    # authored before prompts were rendered.
    source_id: str | None = None
    # Earlier runs whose products `evaluation.prepare` stages read-only into ./prior-artifacts:
    # `trials.<n>.<arm>` names each source workspace. Absent when a task stages none.
    prior_artifacts: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_result_shape(self) -> "EvaluationTask":
        single = self.quality_contract is not None and self.quality_rubric_id is not None
        if single == bool(self.targets) or (self.quality_contract is None) != (self.quality_rubric_id is None):
            raise ValueError("a task defines either quality_contract with quality_rubric_id, or targets, not both or neither")
        return self


class CheckResult(BaseModel):
    """One checker's verdict against one rubric. Checkers cannot modify the run -- this model has
    no field through which one could."""

    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    verdict: Verdict
    score: float
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str
    checker_id: str
    checker_version: str


class Intervention(BaseModel):
    """One human message after the task prompt, read from the harness transcript. `type` stays
    null until the LLM judge labels it from `agent_before`, `text`, and `agent_after`."""

    model_config = ConfigDict(extra="forbid")

    index: int
    timestamp: str
    text: str
    interrupted: bool
    agent_before: str
    agent_after: str | None = None
    type: InterventionType | None = None
    labeled_by: str | None = None


class Execution(BaseModel):
    """One shell command the agent ran, read from the harness transcript, with the `sacct` state
    of any Slurm job it submitted."""

    model_config = ConfigDict(extra="forbid")

    source: str
    timestamp: str
    command: str
    outcome: ExecutionOutcome
    exit_code: int | None = None
    job_ids: list[str] = Field(default_factory=list)
    job_states: dict[str, str] = Field(default_factory=dict)
    # The command's result as the harness recorded it, searched by landmark checks.
    output: str = ""

    @property
    def failed(self) -> bool:
        """A command that exited non-zero, timed out, or was misused, or a job that did not
        complete. A harness permission denial is not the agent's failure."""
        if self.outcome in ("exit_nonzero", "timed_out", "tool_error"):
            return True
        return any(state not in ("COMPLETED", "RUNNING", "PENDING") for state in self.job_states.values())


class PhaseResult(BaseModel):
    """Per-phase reporting fields. `stable_pass_*` is set when the phase's critical rubrics passed
    and remained valid through the end of the run; `terminal_*` is set instead when they never
    did. Both are cumulative cost-to-outcome measures, not exclusive causal attribution."""

    model_config = ConfigDict(extra="forbid")

    accuracy: float
    success: bool
    stable_pass_seconds: float | None = None
    stable_pass_tokens: int | None = None
    terminal_seconds: float | None = None
    terminal_tokens: int | None = None


class QualityResult(BaseModel):
    """The domain's terminal measure, reported separately from rubric accuracy so the two are
    never confused."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    display_label: str
    name: str
    value: float | str | None = None
    reference: float | str | None = None
    passed: bool


class TargetResult(BaseModel):
    """One target's score: its own rubrics plus the shared rubrics it depends on."""

    model_config = ConfigDict(extra="forbid")

    quality_result: QualityResult
    phases: dict[str, PhaseResult]
    success: bool | None = None


class RouteDeparture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    where: str
    approval: Literal["approved_before", "disclosed_only", "none"]


class RouteDepartures(BaseModel):
    """The post-run judge's count of departures from the documented route (`evaluation/departures.py`).
    Present only when a separately requested study runs the judge; never part of `end_to_end_success`."""

    model_config = ConfigDict(extra="forbid")

    judge: str
    items: list[RouteDeparture]
    unapproved: int


class NotApplicableRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    reason: str


class EvaluationCondition(BaseModel):
    """The run's comparison identity. Runs with different `guidance_exposure`,
    `cache_condition_id`, model, author, or bundle digest are never pooled."""

    model_config = ConfigDict(extra="forbid")

    guidance_exposure: GuidanceExposure
    cache_condition_id: str
    suite_role: SuiteRole
    model_id: str
    authored_by: str


class RunEvaluation(BaseModel):
    """The machine-readable per-run scoring result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_path: str
    profile_id: str
    profile_version: int
    bundle_digest: str
    evaluation_condition: EvaluationCondition
    # False when any of the arm's skills was not invoked in the transcript: the run did not
    # exercise what it was launched to test, so it cannot succeed. Null for arms with no method.
    method_invoked: bool | None = None
    # Per skill of the arm: invoked, read_as_file (a deviation: SKILL.md opened as a file), or none.
    method_access: dict[str, Literal["invoked", "read_as_file", "none"]] | None = None
    # False when the session received the operator's configuration (protocol.md, "The operator's
    # configuration stays out of every run"); the run is then excluded like an uninvoked method. Null for
    # runs prepared before per-run harness isolation (no `codex_home` in launch.json).
    isolated: bool | None = None
    end_to_end_success: bool | None
    # Single-target tasks: the task's result and phases. Multi-target tasks: `quality_result` is null,
    # `phases` holds the phases of the shared rubrics only, and `targets` holds each target's score.
    quality_result: QualityResult | None = None
    phases: dict[str, PhaseResult]
    targets: dict[str, TargetResult] = Field(default_factory=dict)
    # The opt-in post-run judge's departures (`departures.py`); null when it was not run or could not judge.
    route_departures: RouteDepartures | None = None
    # Fraction of targets whose `success` is true.
    target_success_rate: float | None = None
    not_applicable: list[NotApplicableRubric] = Field(default_factory=list)
    disputed: list[str] = Field(default_factory=list)
    token_count_quality: UsageQuality
    # Summed from the transcript's recorded usage, with `wait_*` repeating the keys for responses that
    # only watched started work (`transcript.usage`); null when it records none.
    tokens: dict[str, int] | None = None
    # Accesses in the run's transcript that matched the task's `forbidden_access`; empty is a clean monitor.
    monitor_violations: list[str] = Field(default_factory=list)
    integrity_pass: bool
    # True when the run recorded no bundle digest: scored against the current bundle as a
    # historical audit, never pooled with digest-checked runs.
    historical_audit: bool = False
    # Counted from the harness transcript (evaluation/transcript.py), never from the agent's
    # ledger; null when the run's transcript was not supplied.
    human_interventions: int | None = None
    # Counts per judge label; "unlabeled" until the judge has labeled the interventions.
    interventions_by_type: dict[str, int] | None = None
    executions: int | None = None
    failed_executions: int | None = None
