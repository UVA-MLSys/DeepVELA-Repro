"""Scores one arm's frozen run against its task's rubric bundle.

    python -m evaluation.scorer <launch.json> [--write]

`launch.json` is the record `evaluation.prepare` wrote beside the arm's workspace (protocol.md,
"Launch"): `profile_id`, `task_id`, `bundle_digest`, `arm`, and `workspace`. The scorer finds the
workspace's Claude Code or Codex sessions itself and reads only evidence every arm produces the same way:
the workspace files, the transcript's command outputs, and `report.json`. A bundle digest that no
longer matches the launch record is an integrity failure and stops scoring. Output goes to
`<run dir>/evaluation/` beside `ws/`, never into the workspace.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from .bundle import EvaluationBundleError, bundle_digest, load_profile, profile_dir, load_task, rubric_closure
from .checkers import RunSnapshot, _reported, _selected_names, run_checker
from .schema import (
    CheckResult,
    EvaluationCondition,
    Execution,
    Intervention,
    NotApplicableRubric,
    PhaseResult,
    QualityContract,
    QualityResult,
    RunEvaluation,
    TargetResult,
)
from .prepare import USER_CLAUDE_MD, USER_CODEX_HOME
from .transcript import carry_labels, extract, find_sessions, accesses, models, slash_commands, usage
from .transcript import agent_messages, codex_accesses, codex_extract, codex_models, codex_usage, find_codex_sessions, _utc
from .transcript import write as write_transcript


class IntegrityFailure(RuntimeError):
    """The bundle changed after launch; report both digests and score against neither version."""


def _read_report(workspace: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = workspace / "report.json"
    if not path.is_file():
        return None, "report.json is missing from the workspace"
    try:
        report = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"report.json is not valid JSON: {exc}"
    if not isinstance(report, dict):
        return None, "report.json is not a JSON object"
    return report, None


def _section(report: dict[str, Any] | None, path: list[str]) -> dict[str, Any] | None:
    for key in path:
        report = report.get(key) if isinstance(report, dict) else None
    return report if isinstance(report, dict) else None


# An absolute path in a tool call's input. A path reached by `cd` and a relative one is not resolved.
_ABS_PATH = re.compile(r"(?<![\w.~$})])/[^\s\"'`;|&<>(){}\[\],:=*?\\]+")


def outside_scope(target: str, scope: dict | None) -> list[str]:
    """Absolute paths in `target` under a guarded root but not under an allowed path (`launch.json`
    `access_scope`, written by `evaluation.prepare`); empty for a launch record without one."""
    if not scope:
        return []
    within = lambda path, root: path == root or path.startswith(root.rstrip("/") + "/")
    return [p for p in (m.rstrip("/.") or "/" for m in _ABS_PATH.findall(target))
            if any(within(p, g) for g in scope["guarded"]) and not any(within(p, a) for a in scope["allowed"])]


def _end_to_end(quality_result, phases, targets, violations, method_invoked, isolated):
    """The quality rule, every applicable phase, and a clean run; every target must meet those rules."""
    clean = not violations and method_invoked is not False and isolated is not False
    if targets:
        return all(t.success for t in targets.values()) and all(p.success for p in phases.values()) and clean
    return quality_result.passed and all(p.success for p in phases.values()) and clean


def _method_access(skill: str, calls: list[tuple[str, str, str]], slashed: set[str]) -> str:
    """How the arm's skill entered the session (protocol.md, "Setup"): `invoked` by a `/<skill>` command or
    a `Skill` call, which loads it as a skill; `read_as_file` when only its SKILL.md was opened as a
    file, a deviation from the method; `none` otherwise."""
    if skill in slashed or any(tool == "Skill" and json.loads(target).get("skill") == skill for _, tool, target in calls):
        return "invoked"
    if any(f"{skill}/SKILL.md" in target for _, _, target in calls):
        return "read_as_file"
    return "none"


def _sessions(launch: dict[str, Any], workspace: Path) -> tuple[str, list[Path], bool | None]:
    """The harness that ran the session, its session files, and whether the session was isolated from
    the operator's configuration. A Claude Code session is isolated when the workspace still excludes
    the operator's CLAUDE.md; a Codex session when it is saved in the run's own CODEX_HOME, and not when
    it is found in the operator's. Runs prepared before `codex_home` existed are not judged (None)."""
    sessions = find_sessions(workspace)
    if "codex_home" not in launch:
        return "claude-code", sessions, None
    if sessions:
        settings = workspace / ".claude" / "settings.json"
        excluded = settings.is_file() and str(USER_CLAUDE_MD) in json.loads(settings.read_text()).get("claudeMdExcludes", [])
        return "claude-code", sessions, excluded
    if codex := find_codex_sessions(Path(launch["codex_home"]), workspace):
        return "codex", codex, True
    if codex := find_codex_sessions(USER_CODEX_HOME, workspace):
        return "codex", codex, False
    return "claude-code", [], None


def _evaluation_dir(launch: dict[str, Any]) -> Path:
    return Path(launch["workspace"]).parent / "evaluation"


def score_run(launch: dict[str, Any]) -> tuple[RunEvaluation, list[CheckResult], list[Intervention], list[Execution]]:
    workspace = Path(launch["workspace"])
    # New launch records carry a null boundary until evaluation.launch freezes the run. Older records
    # predate that contract and remain readable for historical regression checks.
    if "ended" in launch and not launch["ended"]:
        raise IntegrityFailure("run is not frozen: run evaluation.launch --freeze-only <launch.json>")
    profile = load_profile(launch["profile_id"])
    task = load_task(profile, launch["task_id"])
    digest = bundle_digest(profile_dir(profile.profile_id), launch["task_id"])
    if launch["bundle_digest"] != digest:
        raise IntegrityFailure(f"run launched against bundle digest {launch['bundle_digest']}, bundle is now {digest}")
    cache_condition = task.input_reuse_contract.cache_condition_id

    harness, sessions, isolated = _sessions(launch, workspace)
    # `ended` (ISO timestamp, set in launch.json when the run's session ended) drops whatever the
    # workspace's sessions recorded afterwards.
    ended = launch.get("ended")
    if ended:  # transcripts stamp UTC with `Z` and are filtered by string comparison
        ended = _utc(ended).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    if harness == "codex":
        interventions, executions = codex_extract(sessions, ended)
        calls, slashed = codex_accesses(sessions, ended), set()
    else:
        interventions, executions = extract(sessions, workspace)
        if ended:
            interventions = [i for i in interventions if i.timestamp <= ended]
            executions = [e for e in executions if e.timestamp <= ended]
        calls = accesses(sessions, ended)
        slashed = {name for _, name in slash_commands(sessions, ended)}
    scope = launch.get("access_scope")
    if scope and launch.get("codex_home"):  # the session's own CODEX_HOME, where Codex itself lists skills
        scope = {**scope, "allowed": [*scope["allowed"], launch["codex_home"]]}
    violations = [f"{t[11:19]} {tool}: {target[:160]}" for t, tool, target in calls
                  if any(re.search(pattern, target) for pattern in task.forbidden_access)
                  or outside_scope(target, scope)]
    skills = launch.get("skills") or ([launch["skill"]] if launch.get("skill") else [])
    method_access = {skill: _method_access(skill, calls, slashed) for skill in skills} or None
    if harness == "codex" and method_access:
        # Codex has no Skill tool: it loads a skill by reading the skill's SKILL.md.
        method_access = {s: "invoked" if a == "read_as_file" else a for s, a in method_access.items()}
    method_invoked = None if method_access is None else all(a == "invoked" for a in method_access.values())
    carry_labels(interventions, _evaluation_dir(launch) / "interventions.jsonl")
    report, report_error = _read_report(workspace)
    snapshot = RunSnapshot(
        run_path=f"{launch['task_id']}/{workspace.parent.name}", workspace=workspace,
        executions=executions, messages=agent_messages(sessions, harness, ended), report=report, report_error=report_error,
    )

    results: list[CheckResult] = []
    for rubric in task.phases:
        if not rubric.applicable:
            results.append(CheckResult(
                rubric_id=rubric.rubric_id, verdict="not_applicable", score=0.0,
                reason=f"rubric is authored applicable: false -- {rubric.claim}",
                checker_id=rubric.checker.get("kind", "unknown"), checker_version="4",
            ))
            continue
        if rubric.cache_conditions and cache_condition not in rubric.cache_conditions:
            results.append(CheckResult(
                rubric_id=rubric.rubric_id, verdict="not_applicable", score=0.0,
                reason=f"rubric applies only under cache_conditions {rubric.cache_conditions}, this run is {cache_condition!r}",
                checker_id=rubric.checker.get("kind", "unknown"), checker_version="4",
            ))
            continue
        results.append(run_checker(rubric, snapshot, task))

    critical = {rb.rubric_id for rb in task.phases if rb.critical}
    phase_of = {rb.rubric_id: rb.phase_id for rb in task.phases}

    def phase_scores(subset: list[CheckResult]) -> dict[str, PhaseResult]:
        phases: dict[str, PhaseResult] = {}
        for phase in profile.phases:
            # A phase the subset has no rubric for (a target with no inputs to prepare) is absent, not failed;
            # a phase whose rubrics are all not_applicable stays a failed phase with nothing scored.
            if not any(phase_of[r.rubric_id] == phase.id for r in subset):
                continue
            scored = [r for r in subset if phase_of[r.rubric_id] == phase.id and r.verdict != "not_applicable"]
            n_pass = sum(r.verdict == "pass" for r in scored)
            # Only a critical failure fails the phase (rubric-authoring.md, "Criticality"); non-critical
            # results still count toward the diagnostic accuracy.
            critical_fail = any(r.verdict == "fail" and r.rubric_id in critical for r in scored)
            phases[phase.id] = PhaseResult(
                accuracy=round(n_pass / len(scored), 3) if scored else 0.0,
                success=bool(scored) and not critical_fail,
            )
        return phases

    def quality_of(rubric_id: str, contract: QualityContract) -> QualityResult:
        quality_rubric = next((rb for rb in task.phases if rb.rubric_id == rubric_id), None)
        if quality_rubric is None:
            raise EvaluationBundleError(f"quality_rubric_id {rubric_id!r} names no rubric of task {task.task_id!r}")
        quality_check = next((r for r in results if r.rubric_id == rubric_id), None)
        quality_args = quality_rubric.checker.get("args", {})
        scoped = snapshot if not quality_args.get("report_path") else replace(snapshot, report=_section(snapshot.report, quality_args["report_path"]))
        if contract.expected_verdict is not None and not any(k in quality_args for k in ("metric_name", "references", "bounds")):
            # A verdict oracle (the program prints PASS, or its output is complete) has no numeric metric to bind.
            return QualityResult(
                profile_id=profile.profile_id,
                display_label=f"{profile.profile_id}:{contract.result_name_type_and_direction.split(',')[0].strip()}",
                name=contract.result_name_type_and_direction.split(",")[0].strip(),
                value=None, reference=contract.expected_verdict,
                passed=bool(quality_check and quality_check.verdict == "pass"),
            )
        quality_name = _selected_names(quality_args, scoped, task)[0]
        return QualityResult(
            profile_id=profile.profile_id,
            display_label=f"{profile.profile_id}:{quality_name}",
            name=quality_name,
            value=_reported(scoped, quality_name)[1],
            reference=(quality_args["references"].get(quality_name) if isinstance(quality_args.get("references"), dict)
                       else str(quality_args["bounds"].get(quality_name)) if isinstance(quality_args.get("bounds"), dict)
                       else contract.reference_value),
            passed=bool(quality_check and quality_check.verdict == "pass"),
        )

    not_applicable = [NotApplicableRubric(rubric_id=r.rubric_id, reason=r.reason) for r in results if r.verdict == "not_applicable"]
    target_results: dict[str, TargetResult] = {}
    if task.targets:
        # A target is scored on its own rubrics plus the shared rubrics in their prerequisites closure
        # (bundle.rubric_closure); another target's failure does not touch it.
        for name, spec in task.targets.items():
            in_scope = {rb.rubric_id for rb in rubric_closure(task.phases, name)}
            quality = quality_of(spec.quality_rubric_id, spec.quality_contract)
            target_phases = phase_scores([r for r in results if r.rubric_id in in_scope])
            target_results[name] = TargetResult(
                quality_result=quality, phases=target_phases,
                success=quality.passed and all(p.success for p in target_phases.values()),
            )
        shared = {rb.rubric_id for rb in task.phases if rb.target is None}
        phases = phase_scores([r for r in results if r.rubric_id in shared])
        quality_result = None
    else:
        phases = phase_scores(results)
        quality_result = quality_of(task.quality_rubric_id, task.quality_contract)

    by_type: dict[str, int] = {}
    for i in interventions:
        by_type[i.type or "unlabeled"] = by_type.get(i.type or "unlabeled", 0) + 1
    ran = codex_models(sessions) if harness == "codex" else models(sessions)
    evaluation = RunEvaluation(
        run_path=snapshot.run_path,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        bundle_digest=digest,
        evaluation_condition=EvaluationCondition(
            guidance_exposure=profile.guidance_exposure,
            cache_condition_id=cache_condition,
            suite_role=task.suite_role,
            model_id=",".join(ran) if ran else "unrecorded",
            authored_by=task.authored_by.model_id,
        ),
        method_invoked=method_invoked,
        method_access=method_access,
        isolated=isolated,
        end_to_end_success=_end_to_end(quality_result, phases, target_results, violations, method_invoked, isolated),
        quality_result=quality_result,
        phases=phases,
        targets=target_results,
        # Departure judging is a separately requested study, not part of routine scoring.
        route_departures=None,
        target_success_rate=(sum(t.success for t in target_results.values()) / len(target_results)
                             if target_results else None),
        not_applicable=not_applicable,
        tokens=(tokens := codex_usage(sessions, ended) if harness == "codex" else usage(sessions, ended)),
        monitor_violations=violations,
        token_count_quality="measured" if tokens else "unavailable",
        integrity_pass=True,
        human_interventions=len(interventions) if sessions else None,
        interventions_by_type=by_type if sessions else None,
        executions=len(executions) if sessions else None,
        failed_executions=sum(e.failed for e in executions) if sessions else None,
    )
    return evaluation, results, interventions, executions


def write_evaluation(
    launch: dict[str, Any], evaluation: RunEvaluation, results: list[CheckResult],
    interventions: list[Intervention], executions: list[Execution],
) -> tuple[Path, ...]:
    """`evaluation.json`, its per-rubric `checks.json`, and the transcript's
    `interventions.jsonl`/`executions.jsonl` under `<run dir>/evaluation/`."""
    out_dir = _evaluation_dir(launch)
    out_dir.mkdir(parents=True, exist_ok=True)
    eval_path, checks_path = out_dir / "evaluation.json", out_dir / "checks.json"
    eval_path.write_text(evaluation.model_dump_json(indent=2) + "\n")
    checks_path.write_text(json.dumps([r.model_dump() for r in results], indent=2) + "\n")
    return eval_path, checks_path, *write_transcript(interventions, executions, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("launch", type=Path, help="the launch.json beside the arm's workspace")
    parser.add_argument("--write", action="store_true", help="write the evaluation files; default prints only")
    args = parser.parse_args()
    launch = json.loads(args.launch.read_text())
    try:
        evaluation, results, interventions, executions = score_run(launch)
    except (IntegrityFailure, EvaluationBundleError) as exc:
        raise SystemExit(f"integrity failure, not scored: {exc}")
    for r in results:
        print(f"{r.verdict:15} {r.rubric_id:45} {r.reason}")
    print(evaluation.model_dump_json(indent=2, exclude={"not_applicable"}))
    if args.write:
        for path in write_evaluation(launch, evaluation, results, interventions, executions):
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
