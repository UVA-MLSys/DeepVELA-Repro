# Evaluation protocol

How reproduction runs are scored and compared, for any benchmark task. Scoring never authorizes a
weaker input, a substitute metric, or a relaxed threshold. Choices that belong to one deployment or
one study (paths, scheduler, models, suite, caps) are not written here: each rule below says what
is chosen, and the answers are recorded in [local preferences](../../../docs/local-preferences.md) the first
time they are needed. Choices that belong to one task are made at setup and frozen in its bundle.

The rules follow peer-reviewed agent-reproduction benchmarks:

- **CORE**: CORE-Bench, TMLR 2024
- **PaperBench**: ICML 2025
- **EXP**: EXP-Bench, ICLR 2026
- **SUPER**: EMNLP 2024
- **RExBench**: ACL 2026

Only what they share, or what one of them does and the others do not contradict, is used here.
Anything else is marked **project policy**; where a preprint does the same, it is named.

## Contents

- [Tasks](#tasks)
- [Agents](#agents)
- [What the agent may not see](#what-the-agent-may-not-see)
- [Setup](#setup)
- [Launch](#launch)
  - [The operator's configuration stays out of every run](#the-operators-configuration-stays-out-of-every-run)
- [Scores](#scores)
- [Effort](#effort)
- [Staging](#staging)
- [Analyses reported](#analyses-reported)
- [Gap to the current code](#gap-to-the-current-code)

## Tasks

- **Unit.** A task is one benchmark setup (for example one model, precision, and scenario) and the
  values its evaluator reports. CORE builds tasks the same way: several questions per paper, where
  each question is one reported value.
- **Multi-target definition.** A source with several documented results has one target per result
  row or experiment, with one terminal evaluator invocation. Differences in model, backend, precision,
  dataset, scenario, or mode make separate targets; multiple metrics printed by one evaluator call
  remain one target. A target records its source question, documented route, inputs, evaluator and
  metrics, dependencies, and whether the route is reproducible, repairable, or blocked. A target's
  work uses the task prompt's `<target id>/` layout. Shared inputs and derived artifacts are reused
  when their producing function, inputs, and parameters are identical.
- **Selection (user choice).** A benchmark repository can define several setups, quality classes,
  scenarios or modes, and metrics. At setup, author mode presents the ones the task's documentation
  defines, and the user chooses the evaluation setup(s), the metric(s), the reference for each, and
  the tolerance for each. The rubric records those answers, and every run of the task is scored
  against them. Nothing in the skills chooses for the user.
- **Correctness (user choice).** Each metric the rubric binds is within the tolerance the user set
  of the reference the user chose.
  - Author mode offers these recommendations; it never applies them as defaults: 1% relative
    error, or an absolute 1 point for a metric the evaluator prints as a percent; the task's
    standard quality class when it defines several; and, as reference, the latest and closest
    result in the task's published results.
  - Published results are wherever the task publishes them: a results table or repository outside
    the task (MLPerf's per-round submissions, for example) or a results directory inside it
    (a `results/<model>/all_results.csv` file, for example).
  - Latest and closest means the most recent publication that has the chosen setup (the last one,
    for a setup retired from later publications), and within it the entry closest to the
    deployment: same hardware, else same framework or implementation, else the most common value.
    Match setup names case-insensitively and across renamings between publications, and show the
    user which names were matched.
  - When the published results have no such entry, recommend the value the task's documentation
    states.
  - None of these recommendations is taken from the five studies. CORE (section 2.2, Figure 4)
    instead uses a 95% prediction interval of three manual runs.
  - A task that publishes no value for a metric has no reference. The user sets bounds for it or
    none, the reported value must still appear in an evaluator output and is checked against the
    user's tolerance instead of against a reference.
- **Inclusion (project policy).** Only benchmarks whose documentation defines the data, model, and
  evaluator (a user-confirmed `builder-reproduce` card may define the evaluator, metric, or sample
  set the documentation lacks, never the data or model), following the 4.5-of-5 MLCommons Ontology rating. It is not taken from the five
  studies.
- **Split (study choice).** Every task from one benchmark repository directory goes to the same
  split. Directories used while developing an arm form the dev split; results are reported on the
  held-out test split (CORE section 2.1 splits by paper, 45 train and 45 test; PaperBench section 3
  also keeps a development set and a held-out set). A task manifest's `suite_role` follows its
  directory's split. Which directories are dev and which are test is recorded per study.
- **Suite size (study choice).** Report the number of test tasks and runs per arm with the interval
  it allows: a difference between arms smaller than the width of a success rate's 95% Wilson
  interval cannot be separated from noise.

## Agents

- **Model (study choice).** The same model for every arm, selected before the prompt is sent. The
  scorer records the model IDs the transcript shows actually answered, not a declared one.
- **Arms (study choice).** Each arm uses the same model, task prompt, materials, and budget. Each
  arm's own system instructions, tools, and control loop are recorded with the run, because they are
  the variable under test. CORE (section 3) compares AutoGPT with the task-adapted CORE-Agent,
  PaperBench (section 5.3) compares BasicAgent with IterativeAgent, and EXP (section 4.1) compares
  OpenHands with IterativeAgent; a study compares at least a plain coding agent with the method under
  test.
- **Budget (study choice).** A fixed per-task cap on wall clock and API cost, the same for every arm
  and set before the run, never by the agent. CORE used $4 and 2 hours, PaperBench 12 hours, and
  EXP 40 minutes. The caps for each stage are set as in Staging.
- **Isolation.** Each run starts in a clean workspace with no memory of other runs (CORE section 3,
  "Evaluation harness"). Only the method under test differs between arms' workspaces.
- **Human help.** Each arm runs at help levels fixed before the run. RExBench (section 4.2) fixes two
  hint levels in advance and reports success at each.
  1. Autonomous: no human input after launch.
  2. Fixed answers: task-specific answers selected at setup are written before the run into a
     per-task answer file that every arm receives with the task prompt (**project policy**).
  3. Interactive: the human answers the agent's questions and intervenes when it goes the wrong way.
  Only levels 1 and 2 count toward the autonomous success rate. At level 3 every intervention is
  counted and typed (Effort).

## What the agent may not see

- **Rubric and ground truth.** The agent never sees the rubric or the ground-truth values
  (PaperBench section 2), and never authors or edits the bundle it is scored against.
- **Documented reference.** Every stated reference value for a chosen metric (result tables in
  documentation, targets in checker code, published results inside the repository) is masked in the
  source the run starts from, and the run gets no version history to recover it. EXP (section 3.2)
  masks README files and scripts that contain answers, so the agent cannot stop at a known target.
- **Blacklist.** Internet access is allowed for downloads, except for a per-task blacklist: the
  task's published results, wherever setup found them. A monitor reads each run's log. A
  blacklisted resource, or a metric that was hardcoded or copied rather than produced by the
  evaluator, sets the run's score to zero (PaperBench section 2.5; EXP section 4.1, monitor M).
- **Published results outside the task.** A copy kept for setup lives in the bundle root beside the
  bundles, outside every directory a reproducing agent reads. `evaluation.prepare` refuses to launch when the
  repository, the bundle root and the runs root contain one another.

## Setup

Setup runs once per task, in a session of its own started from the fixed author-mode prompt in
`SKILL.md`, never in a development session or a run (**project policy**). It freezes three things
under one bundle digest in `tasks/<task_id>/`:

- the rubric, with the user's metric, reference, and tolerance;
- `source.tar.gz`, the pinned commit without history and with the reference masked, and
  `masked.txt`, what was masked and where;
- `prompt.md`, the task prompt, rendered from the dataset record and `assets/task_prompt.md` by `evaluation.task_prompt`,
  and `tasks.json`, the selected tasks' records it points to, copied into the workspace at launch.

Every run and every arm of the task gets that prompt unchanged, with two exceptions:

- guidance the harness adds identically to every arm (`evaluation.prepare`: the Compute wording, the compute
  requirement on `reproduce.sh`, shared-environment ownership, and, with `--autonomy`, that no human will
  reply);
- for an arm whose method is a skill, a first line `/<skill>` naming its first skill (**project
  policy**). Pasted with the prompt, it reaches the agent inside the pasted text, and the agent
  invokes the skill itself. An
  arm with two skills (`builder-skill`) adds one last line naming the hand-off to the second.
  `evaluation.prepare` writes both and records both hashes in `launch.json`.

The scorer records, per skill of the arm, how it entered the session (`method_access`): `invoked`
(the `/<skill>` command or a `Skill` call), `read_as_file` (only its `SKILL.md` opened as a file, a
deviation: the agent read the text but did not run it as a skill), or `none`. Unless every skill is
`invoked`, the scorer sets `method_invoked: false` and `end_to_end_success: false`, and the run is
excluded from arm comparisons. The method invocation is the only thing that may differ between arms. Any other
change to the prompt changes the path a run takes, so the runs stop being comparable; it is a
change to the task and needs a new digest.

## Launch

Each run is an ordinary interactive coding-agent session whose transcript the harness keeps, so it
can be reopened and inspected after the operator's own session ends. Launch mode runs, once per arm:

    python -m evaluation.prepare <profile_id> <task_id> --arm <arm>

which creates `<runs root>/<task_id>/<arm>-<YYYY-MM-DD-HH-MM-SS>/`:

- `ws/repo/`: the task's `source.tar.gz`;
- the method under test, for its arm only, copied where the harness loads it from the workspace
  (for a skill, `ws/.claude/skills/<skill>/`). The method is not installed where every session would
  load it, so a workspace has it only when its arm provides it. Anything else the harness loads for
  every session loads in every arm alike;
- `ws/prompt.md`, the arm's prompt, which the operator sends from there;
- `launch.json` beside `ws/`: `profile_id`, `task_id`, `bundle_digest`, `arm`, the workspace path, the
  sha256 of `ws/prompt.md`, the Codex model and reasoning effort when given, and the Codex launch command
  (`codex exec` for an autonomous run, the interactive session otherwise). `evaluation.launch` adds `ended` and
  `canonical_trace` when the run ends.

An autonomous Codex arm is started by `python -m evaluation.launch <launch.json>`. For any other arm, the
operator opens exactly `ws/` as the session's workspace, selects the study's model, sends `ws/prompt.md`
unchanged, answers the agent, and stops the session at the wall-clock cap. A session opened in a parent of
`ws/` sees `launch.json` and other runs, so it is not a valid run. The harness records the
session under the workspace path, and the scorer finds it there, so nothing about the session is
recorded by hand.

### The operator's configuration stays out of every run

A coding-agent harness loads the operator's user-level configuration into every session it starts:
instructions files, globally installed skills, plugins and memory. A run receives none of it.
Otherwise every arm runs with the operator's instructions, and a global copy of the method under test
reaches the arms that must not have it. `evaluation.prepare` isolates each harness:

- Claude Code: `ws/.claude/settings.json` excludes the operator's `~/.claude/CLAUDE.md`
  (`claudeMdExcludes`). The operator's user-level skills and plugins are still listed to the session.
- Codex: there is no per-workspace exclude, so each run gets its own `CODEX_HOME` at
  `<run>/codex-home`, holding only a link to the credentials and a `config.toml` that names the study's model
  and reasoning effort and disables Codex's bundled skills, so a session lists only its arm's workspace skills.
  The operator's `AGENTS.md`, skills, MCP servers and profiles stay out. `evaluation.launch` runs
  `codex_command` without the evaluation's environment variables (bundle root, runs root) and without this
  repository's `.venv` on `PATH`, so the session cannot find the unmasked bundle. Codex saves the session file
  in `<run>/codex-home/sessions/`, beside the run.

Pitfalls seen in live runs:

- **Method installed as a user-level skill.** It loads in every session, so the plain arm has it too.
  Keep the method only in the workspaces of the arms that test it.
- **Session launched by hand with the default home.** Every plain-arm Codex session launched that way
  in one campaign was listed the operator's skills and opened the Reproduce `SKILL.md`.
- **Hiding the operator's configuration by renaming it.** Codex lists skills in subfolders, and a
  restore `mv` into a folder the harness had recreated nested the skills instead of restoring them.
  Never edit the operator's configuration to isolate a run; give the run its own home.

The scorer enforces this for every run whose `launch.json` has `codex_home`. It sets `isolated`
from where it finds the session: a Claude Code session is isolated while the workspace still excludes
the operator's `CLAUDE.md`, and a Codex session when it is saved in the run's own `codex-home`, not
in the operator's. A run with `isolated: false` has `end_to_end_success: false` and is excluded from
arm comparisons, as a run whose method was not invoked is. Runs prepared before this check have
`isolated: null`.

Before a campaign, launch mode checks isolation on one prepared `plain` workspace: it starts that session (for
Codex, with `codex exec` under the run's `CODEX_HOME`) with a short prompt that asks which instructions and
skills the session was given. The answer must name no operator instruction and no skill of a method under
test. For a Claude Code study, the agent gives the user that prompt to send in the `plain` workspace.

## Scores

- **Deliverable.** The agent must leave a single self-contained `reproduce.sh` entrypoint that
  meets the task prompt's Deliverable conditions: copied alone beside a fresh repository, with the
  stated inputs, `OUTPUT_DIR` set, and nothing built, it runs once per target from one directory and
  writes each target's outputs to `OUTPUT_DIR`.
- **Phase checks.** Binary checks per phase, read only from evidence every arm produces the same
  way: the command outputs in the transcript and the files in the workspace. Most are landmarks
  (SUPER, section 3.1.2): output patterns from the benchmark's own tools that show a step ran, such
  as a harness's mode line or the evaluator's summary line with the full sample count, so that a run
  that stops late scores above one that stops early. Phase progress is the share of checks passed
  and shows where a failed run stopped. A check that no output can decide is graded by the LLM judge.
  A record that one arm's method asks the agent to keep is never evidence: the other arms do not
  write it, and the agent can leave anything out of it. The phases are the profile's, confirmed by
  the user at setup (**project policy**).
- **Reported result.** Every value the rubric binds, as the agent reports it in `report.json`, is
  within tolerance of its reference and appears in an evaluator output, so a number the agent wrote
  itself does not count. The fixed prompt asks every arm for `report.json`; CORE scores the agent's
  `report.json` the same way.
- **Task success (primary).** Reported result, every phase check, and a clean monitor, all together.
  EXP reports its conjunctive All·E✓ beside the single metrics, because each single metric
  over-credits (section 4.2). A timeout, crash, missing `reproduce.sh`, or missing value scores zero,
  and every attempted run is in the denominator (CORE section 3, "Metrics").

## Effort

Effort is read from the harness's session transcript and the scheduler's job records, never from a
record the agent writes: an agent can leave a failure or a human message out of its own record.

- **Interventions.** Every human message after the task prompt, stored in `interventions.jsonl` with
  the agent's text before and after it. The LLM judge labels each one `clarification`,
  `error-fixing`, `correction` (the agent was going the wrong way), or `approval` (the agent proposed
  a decision and the human authorized it without supplying a correction or new task fact).
- **Executions.** Every shell command and its exit status, and the scheduler's final state of each
  job it submitted, in `executions.jsonl`. A command that exits non-zero or times out, or a job that
  does not complete, is a failed execution (**project policy**; the Paper-replication preprint counts
  "superseded executions", failed or later replaced, the same way).
- **Cost.** Wall clock from the task prompt to the agent's final report, tokens, API cost (CORE
  section 3, "Metrics"; EXP section 4.2), and accelerator hours from the scheduler.
  - GPU work outside the scheduler (`compute: local`, or `hybrid`) has no scheduler record and is
    reported as unmeasured.
  - Scheduler queue wait depends on cluster load, not on the agent, so it is reported apart, per
    job: `sacct` `Submit` to `Start` is the wait, and `Start` to `End` is the run.
  - The arm comparison uses measurements attributable to each run (job-level records and the
    resource measurement). The session's raw wall clock is compared only for arms that ran one
    after the other (**project policy**).
- **Judge model (study choice).** A stronger model than the agents under test, recorded with each
  label. It labels phase checks that no output decides and intervention types.
- **Judge validation.** Before judge labels are used, label a sample by hand and report the judge's
  agreement with those labels (PaperBench section 4.2, JudgeEval; EXP Appendix J.3). When the judge
  and the agents come from one vendor, draw the hand-labelled sample from every arm: the CrossAudit
  preprint reports that same-vendor judges favor their own generations.

## Staging

Each stage runs only after the previous one works.

- The pilot cap is set per task at authoring, from a preflight check: a reduced run of the task's own
  benchmark on the task's compute (the task's documented subset option if it has one), timed per
  stage and extrapolated to the full run. The extrapolation is labelled an estimate. The cap
  proposed to the user is that estimate plus the time to build the environment and fetch packages,
  with headroom for the agent's own turns, and it is written into the prompt only after the user
  confirms it. API cost is recorded but not capped until a cost has been measured.
- The dev and test caps are twice the largest wall clock and API cost of any successful pilot run.
  CORE (Figure 7) found that raising its cap from $4 to $10 did not raise accuracy, because failing
  runs stall rather than run out of budget (**project policy**).

1. **Pilot.** One dev task, one run per arm. Check that the masking, the monitor, the Deliverable,
   and the rubric work end to end. Measure the per-run cost and time.
2. **Dev.** All dev tasks, one run per arm. Grade a sample by hand to validate the judge. Fix the
   harness, not the agent's answers.
3. **Test.** The held-out tasks with three runs per arm, reporting the mean and the per-run range
   (CORE Table 5 and PaperBench section 5.2 both use three runs).

## Analyses reported

- Per arm and help level: task success rate and reported-result rate, each as per-task pass@1 and the macro-average over tasks with a 95% interval and the
  per-run range; phase progress.
- Effort per successful run: interventions by type, failed executions, and cost. Cost against success
  per arm (CORE Figure 6; EXP Figure 6a).
- Per-task comparison of two arms: the arm with the higher task success wins the task; on a tie, fewer
  interventions win, then fewer failed executions, then lower cost. EXP ranks agents by All·E✓ and
  breaks ties with C, an ordering rather than a weighted sum; this order is **project policy**.
  Report the share of tasks each arm wins.
- Numerical discrepancy from the reference, for successful runs only, beside the success rate and
  never in place of it.
- Failure analysis: failed runs' logs coded into failure types per phase (CORE section 4.6; EXP
  section 4.3).

## Gap to the current code

`evaluation/` scores one arm's run: `python -m evaluation.scorer <launch.json>`. It
checks landmarks, artifacts, hashes, LLM-judge claims (`builtin.judge`), and the reported values in
`report.json` against the transcript's command outputs and the workspace files, counts
interventions, executions, failed executions and tokens (from recorded usage), runs the monitor
over every tool call against the task's `forbidden_access`, and computes `end_to_end_success` once
`launch.json` records the frozen trace identity. It reads Claude Code and Codex transcripts, and job
states from Slurm (`sacct`) only, for Claude Code sessions. Not built: judge validation against hand
labels, the judge labels for interventions, and comparisons across runs. Not published in this repository:
the route-departure judge and the per-agent resource table.
