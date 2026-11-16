# Run protocol

How a benchmark task is set up and how each arm's run is launched so that runs of different arms are
comparable. Choices that belong to one deployment or study (paths, scheduler, arms, model, help level) are not
written here; they are recorded in [local preferences](../../../docs/local-preferences.md) the first time they
are needed. Choices that belong to one task are made at setup and frozen in its bundle.

The rules follow published agent-reproduction benchmarks: CORE-Bench (TMLR 2024), PaperBench (ICML 2025),
EXP-Bench (ICLR 2026), and RExBench (ACL 2026). Rules none of them state are marked **project policy**.

## Contents

- [Tasks](#tasks)
- [Arms](#arms)
- [What the agent may not see](#what-the-agent-may-not-see)
- [Setup](#setup)
- [Launch](#launch)
  - [The operator's configuration stays out of every run](#the-operators-configuration-stays-out-of-every-run)
- [Staging](#staging)

## Tasks

- **Unit.** A task is one benchmark setup (for example one model, precision, and scenario) and the values its
  evaluator reports. CORE-Bench builds tasks the same way: several questions per paper, each one reported value.
- **Targets.** A source with several documented results has one target per result row or experiment, with one
  terminal evaluator invocation. A different model, backend, precision, dataset, scenario, or mode is a separate
  target; several metrics printed by one evaluator call remain one target.
- **Selection (user choice).** A benchmark repository can define several setups, quality classes, scenarios or
  modes, and metrics. At setup, author mode presents the ones the documentation defines, and the user chooses.
  Nothing in the skills chooses for the user.

## Arms

- **Same inputs.** Each arm uses the same model, task prompt, materials, and budget. Only the method under test
  differs: `plain` has no reproduction skill, `skill` has Reproduce, `builder-skill` has Builder + Reproduce.
- **Isolation.** Each run starts in a clean workspace with no memory of other runs (CORE-Bench section 3).
- **Help level.** Fixed before the run: autonomous (no human input after launch) or interactive (the human
  answers the agent's questions). RExBench (section 4.2) likewise fixes help levels in advance.
- **Budget.** A fixed per-task wall-clock cap, the same for every arm and set before the run, never by the agent.

## What the agent may not see

- **Documented reference.** Every stated reference value for a chosen result (result tables in documentation,
  targets in checker code, published results inside the repository) is masked in the source the run starts
  from, and the run gets no version history to recover it. EXP-Bench (section 3.2) masks README files and
  scripts that contain answers, so the agent cannot stop at a known target.
- **Blacklist.** Internet access is allowed for downloads, except for the task's published results, which the
  record's `policy.forbidden` names and the prompt forbids.
- **Bundle.** The bundle root lies outside every directory a reproducing agent reads. `evaluation.prepare`
  refuses to launch when the repository, the bundle root, and the runs root are not disjoint.

## Setup

Author mode freezes, under one digest in `<bundle root>/<task_id>/`:

- `source.tar.gz`, the pinned commit without history and with the reference masked, and `masked.txt`, what was
  masked and where;
- `prompt.md`, rendered from the dataset record and `assets/task_prompt.md` by `evaluation.task_prompt`, and
  `tasks.json`, the selected tasks' records it points to;
- `manifest.yaml`, naming the task, its dataset record, and the commit.

Every run and every arm of the task gets that prompt unchanged, with two exceptions:

- guidance `evaluation.prepare` adds identically to every arm: the Compute wording, how the grader re-runs
  `reproduce.sh`, shared-environment ownership, and, with `--autonomy`, that no human will reply;
- for an arm whose method is a skill, a first line `/<skill>` naming its first skill (**project policy**). An
  arm with two skills (`builder-skill`) adds one last line naming the hand-off to the second.

Any other change to the prompt changes the path a run takes, so the runs stop being comparable; it is a change to
the task and needs a new bundle.

## Launch

Each run is an ordinary coding-agent session whose transcript the harness keeps. Launch mode runs, once per arm,
`python -m evaluation.prepare <task_id> --arm <arm>`, which creates `<runs root>/<task_id>/<arm>-<timestamp>/`:

- `ws/repo/`: the task's `source.tar.gz`, extracted;
- the method under test, for its arm only: the Claude Code packages in `ws/.claude/skills/`, the Codex packages
  in `ws/.agents/skills/`. The method is not installed where every session would load it, so a workspace has it
  only when its arm provides it;
- `ws/prompt.md`, the arm's prompt, which the operator sends from there;
- `launch.json` beside `ws/`: the task, the bundle digest, the arm, the workspace path, the sha256 of
  `ws/prompt.md`, the model when given, and the Codex launch command (`codex exec` for an autonomous run, the
  interactive session otherwise).

The operator opens `ws/` as the session's workspace, selects the study's model, sends `ws/prompt.md` unchanged,
answers the agent if the run is interactive, and stops the session at the wall-clock cap.

### The operator's configuration stays out of every run

A coding-agent harness loads the operator's user-level configuration into every session it starts:
instructions files, globally installed skills, plugins and memory. A run must receive neither the operator's
instructions nor a copy of the method under test: otherwise every arm runs with the operator's instructions, and
a global copy of the method reaches the arms that must not have it. `evaluation.prepare` isolates each harness:

- Claude Code: `ws/.claude/settings.json` excludes the operator's `~/.claude/CLAUDE.md` (`claudeMdExcludes`).
  The operator's user-level skills and plugins are still listed to the session, so do not install the
  Reproduce skills at user level.
- Codex: there is no per-workspace exclude, so each run gets its own `CODEX_HOME` at `<run>/codex-home`,
  holding only a link to the credentials and a copy of `config.toml`. The operator's `AGENTS.md` and skills stay
  out. The copied `config.toml` keeps provider and model settings, but anything else in it (MCP servers,
  profiles) reaches every arm alike, so keep it minimal for a study. Launch the session with `codex_command`
  from `launch.json`; Codex then saves the session in `<run>/codex-home/sessions/`.

Never edit the operator's configuration to isolate a run, for example by renaming it; give the run its own home.
Before a study, launch mode checks isolation on one prepared `plain` workspace: it starts that session (for Codex,
with `codex exec` under the run's `CODEX_HOME`) with a short prompt that asks which instructions and skills the
session was given. The answer must name no operator instruction and no skill of a method under test. For a
Claude Code study, the agent gives the user that prompt to send in the `plain` workspace.

## Staging

The wall-clock cap is set per task at authoring, from a preflight check: a reduced run of the task's own
benchmark on the task's compute (the task's documented subset option if it has one), timed per stage and
extrapolated to the full run. The extrapolation is labelled an estimate. The cap proposed to the user is that
estimate plus the time to build the environment and fetch packages, with headroom for the agent's own turns,
and it is written into the record only after the user confirms it.
