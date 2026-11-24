---
name: agent-evaluation-profile
description: Reproduce a benchmark task with and without the Reproduce skills. Sets up the task (frozen rubric, masked source, fixed task prompt), prepares and starts each arm's run, and scores a finished run. Use when asked to reproduce, set up, launch, score, grade, or evaluate a benchmark task or run.
---

# Agent evaluation profile

The skill has two modes with the same authority: author the task before any run and launch each
arm's run. The reproducing agent never runs either.
Every mode runs in a chat opened in this repository, which provides this skill as a project skill.

Never ask the user to do something you can do yourself. Do it, using the saved answers in
[local preferences](../../docs/local-preferences.md) where they apply, and report the result. The
user's part is only what needs a person:

- the decisions that are theirs (author mode);
- sending the prompt of an arm you cannot start yourself, and answering the agent if the run is
  interactive;
- hand-labelling the judge-validation sample.

## Contents

- [Deployment answers](#deployment-answers)
- [Pick the mode](#pick-the-mode)
- [Inputs to ask for](#inputs-to-ask-for)
- [Author mode](#author-mode)
- [Launch mode](#launch-mode)
- [Score](#score)

## Deployment answers

Read [local preferences](../../docs/local-preferences.md) the first time a mode needs a deployment
answer.

- For an item not yet answered, ask the user once, with its recommendation, and record the answer
  there, relative to this repository's root when it can be.
- Install the Python dependencies once: `python -m pip install -r requirements.txt`.
- Run every `evaluation.*` command from the repository root with `EVALUATION_BUNDLE_DIR`,
  `REPRODUCTION_RUNS_DIR` and `EVALUATION_JUDGE` set from those answers (sections 1, 2 and 4). The
  code has no default for any of them.
- For scheduler runs, ask the account, partition and GPU items only when the user says runs go through
  Slurm, and fill the Compute wordings from those answers.
- Never write a deployment answer into this skill, its references, or the code.

## Pick the mode

- **author**: a task repository or benchmark link is given, and no run exists yet.
- **launch**: a set-up task is named to start a run, or a finished run's `launch.json` is given to
  freeze or score it.

If the mode is ambiguous, ask. Do not author and launch in the same pass.

## Inputs to ask for

Ask only for what is missing, in one question, then proceed.

Author mode:

| Input | Default if not given |
|---|---|
| Task repository link or path | ask, required |
| Bundle root | [local preferences](../../docs/local-preferences.md), section 1 |
| `profile_id` | ask, required; check `<bundle_root>/INDEX.md` first and reuse an existing profile when the domain matches |
| `task_id` | benchmark directory name plus dataset, e.g. `3d-unet-kits19` |
| Suite role | the split of the task's benchmark directory ([protocol](references/protocol.md), "Split"); `held_out` only if no prior reproduction run of any task in that directory is visible |
| Cache condition(s) to support | `cold` and `warm_raw_inputs_v1` |

Launch mode: `profile_id` and `task_id` of a set-up task (required). For an existing run, use its
`launch.json`. When the user names only an arm and a task, use the
newest `<arm>-*` run under `<runs root>/<task_id>/` and say which one. Do not ask for the path.

## Author mode

1. Find or write the dataset record `dataset/tasks/<source_id>.json` ([schema](../../docs/dataset-schema.md)).
   Clone `repo.url` into `repo.path` if the clone is missing, then check out `repo.commit` in it, every time:
   records share clones (every MLPerf record uses `.cache/sources/inference`), so the clone may be at another
   record's commit. Ask the user to approve the commit when the record is new.
   Read the task repository's own documentation, evaluator, and configuration first. Every rubric
   claim must come from that source, not from this skill and not from memory. Author one task at a
   time, when the user first reproduces it; never author ahead for tasks nobody has asked for.
   Present the options the task defines, each with a recommendation, and let the user choose:
   - evaluation setup(s): each choice the task's documentation defines (variants, accuracy or
     quality classes, scenarios or modes), named as the documentation names them;
   - where the task's inputs are cached for runs, as read-only paths the task prompt will give. Fetch the
     datasets and checkpoints there by the documentation's own procedure, and check their counts and published
     checksums, before the preflight check;
   - metric(s) the evaluator prints, one or several;
   - reference for each metric: the candidate entries from the task's published results, wherever
     the task publishes them (recommend the latest and closest, [protocol](references/protocol.md),
     "Correctness"), and the value the task's documentation states. Find where the task publishes
     results from its own documentation, and show the user the source you found. When the task
     publishes no value for a metric, say so; the user then chooses bounds or no reference
     ([protocol](references/protocol.md), "Correctness");
   - tolerance for each metric: recommend 1% relative error, or an absolute 1 point for a metric
     the evaluator prints as a percent;
   - wall-clock cap: run the preflight check ([protocol](references/protocol.md), "Staging"), a
     reduced run of the task's own benchmark on the task's compute, timed per stage. Show the user
     the measured times, the extrapolated full-run estimate (labelled an estimate), and a proposed
     cap. The cap is whatever the user confirms.

   Write the answers into the quality rubric as given. This skill never picks any of them itself,
   and a recommendation the user has not confirmed is not an answer.
2. Read `<bundle_root>/INDEX.md` before touching any single profile's `bundle.yaml`.
   - If a listed profile's domain/reproduction-shape row already matches this repository, reuse its
     `profile_id` and skip to step 3 with a new task folder in it ([layout](references/rubric-authoring.md#bundle-layout)). Do not author a
     second profile for the same shape.
   - If this profile already exists, read its phase list (`id`/`label`/`templates` per phase) from
     that bundle's own `bundle.yaml`.
   - If no listed profile fits, propose a new phase list (id, label, and rubric-template membership
     per phase) and get it confirmed before writing rubrics or `bundle.yaml`.
3. Write one rubric YAML per atomic claim under `<bundle_root>/<profile_id>/`. Follow
   [rubric authoring](references/rubric-authoring.md) for the schema, the claim rules,
   criticality, and the cold/warm split.
4. Mask the reference.
   - Pin the commit, and ask the user to approve it.
   - Find every file in that commit that states a reference value for a chosen metric: result
     tables in READMEs, accuracy targets in submission or checker code. List each path and line
     with its excerpt in `tasks/<task_id>/masked.txt`.
   - Write `tasks/<task_id>/source.tar.gz` with those values replaced by `<masked>`. It is a
     `git archive` of the pinned commit, so it has no history, limited to the directories the task
     uses (the benchmark directory and what it builds from), because each run extracts its own
     copy. The run starts from this archive ([protocol](references/protocol.md), "What the agent
     may not see").
   - Every masked file must still parse and import; check code files with their own parser, e.g.
     `python -m py_compile`. A value that cannot be removed without breaking the code stays in
     place, is listed as unmasked in `masked.txt`, and the user is told.
   - When the commit states no reference value, `masked.txt` says so and the archive is the
     unmasked pinned commit.
5. Render the task prompt from the source's dataset record (`dataset/tasks/<source_id>.json`; a
   controlled study's own record is `dataset/tasks/<study>/<name>.json`,
   [schema](../../docs/dataset-schema.md)); never write it by hand:

   ```bash
   python -m evaluation.task_prompt <source_id> [--tasks <the env group's task ids>] \
     --out <task folder>/prompt.md
   ```

   - The template, [assets/task_prompt.md](assets/task_prompt.md), is fixed, as CORE-Bench's
     `benchmark_prompts.json` is; only the record varies.
   - `--out` also writes `tasks.json` beside the prompt: the selected tasks' records, which the
     prompt points to and `prepare` copies into the workspace.
   - When the renderer names a field the record lacks, put the user's answer in the record and render
     again.
   - Record `source_id: <source_id>` and `source_revision: <the record's commit>` in
     `tasks/<task_id>/manifest.yaml`.
   - Every run and every arm of this task gets this prompt unchanged; a skill arm gets only the
     added invocation line ([protocol](references/protocol.md), "Setup"). A different prompt is a
     different task and needs re-authoring and a new digest.
   - The prompt names no reference value and no evaluation identifier (`profile_id`, `task_id`,
     digest). The harness records those at launch.
   - The record carries what selects the result (commit, entry instruction, metric names), the
     acceptance criteria (output files, log lines, report keys),
     deployment facts, and forbidden evidence.
   - Its `task_prompt` names the entry command the documentation gives, as the CORE-Bench and
     SocSci-Repro-Bench task prompts do. The environment procedure stays out, as in CORE-Bench
     Hard, and recovering it is part of the task.
6. Write `bundle.yaml`, then seal the bundle, which checks the task manifest against the record and the
   prompt, writes `MANIFEST.sha256`, and prints the task's digest:

   ```bash
   python -m evaluation.bundle seal <profile_id> <task_id>
   ```

   The manifest covers `prompt.md`, `tasks.json`, `masked.txt`, and `source.tar.gz` with the rubrics.
7. Update `<bundle_root>/INDEX.md` in this same pass:
   - if step 2 created a new `profile_id`, add one row: `profile_id`, domain/reproduction-shape
     summary, and the new `task_id`;
   - if step 2 reused an existing `profile_id`, append the new `task_id` to that row's Tasks column
     instead of adding a row.
8. Report the `profile_id`, the `task_id`, the digest, the rubric count per phase, and the masked
   paths. Launch mode needs the two IDs. The harness records the digest in the run's launch record
   ([protocol](references/protocol.md), "Launch"); the reproducing agent never sees it.

Hard rules:

- The bundle root must resolve outside the repository the reproducing agent works in and reads, so
  that the agent cannot see the rubric. Confirm with
  `python -c "from pathlib import Path; print(Path('<bundle_root>').resolve())"` before writing.
- A claim with no source path, SHA-256, and quoted excerpt is not a rubric. The source is the task
  repository or, for a task-defining fact the repository lacks (evaluator, metric, sample set), a
  user-confirmed `builder-reproduce` card frozen in `tasks/<task_id>/`; the prompt then states that
  fact (step 5). Otherwise drop the claim or record it as an open question for the user.
- Do not choose the metric, the reference, or the tolerance: the user does (step 1). The rubric
  records their answers and checks the run's reported values against them.
- Do not write commands the agent should run. A rubric states an observable outcome.
- Author in a session separate from the run it scores, and never edit a bundle while a run against
  it is in progress. The reproducing session never authors or edits its own rubric
  ([protocol](references/protocol.md), "What the agent may not see").

## Launch mode

Prepare the study's arms ([local preferences](../../docs/local-preferences.md), section 4;
[protocol](references/protocol.md), "Launch") in any order.

- Arms may run at the same time, except arms whose GPU work runs on the same machine's GPUs
  (`compute: local` or `hybrid`). Those run one after another.
- Every arm's prompt tells the session to cancel or modify only work it started.
- Compare session wall clock only for arms that ran one after the other.

To start an arm, run this yourself from the repository root:

```bash
EVALUATION_BUNDLE_DIR=<section 1> REPRODUCTION_RUNS_DIR=<section 2> \
  python -m evaluation.prepare <profile_id> <task_id> --arm <arm>
```

- Add `--compute local|slurm|hybrid|cpu` only to override the default, which is the dataset
  `policy.compute` of the manifest's `source_id`. A manifest without `source_id` needs the flag. Use
  `local` when the preferences say runs execute on this machine, and compare this machine's GPU
  (`nvidia-smi`) with the record's `platform` first: the platform is a task fact, so a mismatch means
  editing the record, rendering again, and sealing again.
- Add `--autonomy` when the study's help level is autonomous. Without it, the session stops to ask.
- Add `--model <ID>` and `--effort <level>` with the study's Codex model and reasoning effort (section 4).
  `prepare` writes them into the run's `CODEX_HOME` and `launch.json` records them; for Claude Code, the
  user selects the model in the session.

These choices are recorded in `launch.json`. Runs on different compute are never pooled for wall clock.
Before the first arm of a study, check isolation on one prepared `plain` workspace
([protocol](references/protocol.md), "The operator's configuration stays out of every run").

Then start each arm yourself where you can; the user should only have to send a prompt or wait:

- Autonomous Codex arm: run `python -m evaluation.launch <launch.json>` in the background, never a
  hand-written command, so the run receives none of the operator's configuration or the evaluation's
  variables. It runs the prepared command, then freezes the run by recording `ended` and
  `canonical_trace`. Report the workspace path and that the run has started.
- Any other arm (Claude Code, or an interactive run): reply with only the workspace path the command
  prints, and tell the user to open exactly that `ws/` directory, not the run directory or any parent, as
  the workspace of a new editor window, start a new chat there, and send the text of `ws/prompt.md`
  unchanged, keeping its first line first. A session opened in a parent sees `launch.json` and other
  runs. Do not repeat the prompt in the chat. For an interactive Codex run, give the user the
  `codex_command` from `launch.json` to run in a terminal.

Tell the user to send every later message to you (the repository chat), only after the run has ended,
never in `ws/`.

## Score

When the user says a run has ended, confirm with `sacct -j` that its Slurm jobs are terminal (the job IDs
are in the `executions.jsonl` that `python -m evaluation.transcript extract <ws> --out <dir>` writes), and
touch no job another arm started. Freeze a run that `evaluation.launch` did not start with
`python -m evaluation.launch <launch.json> --freeze-only`, then score it with
`python -m evaluation.scorer <launch.json> --write`. A digest mismatch is an integrity failure; report it rather than
scoring around it. Report `token_count_quality: unavailable` unless recorded usage exists, and never
reconstruct token counts. Cold-cache and warm-cache runs are separate conditions and must not be pooled.
Delete a run's generated data only after it is scored: rubrics read files such as the accuracy log.
