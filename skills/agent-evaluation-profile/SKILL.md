---
name: agent-evaluation-profile
description: Set up a benchmark task for reproduction runs (pinned and masked source, fixed task prompt) and prepare each arm's workspace for a run. Use when asked to reproduce a benchmark task with the Reproduce skills, to set up a task, or to launch or prepare a reproduction run or arm.
---

# Agent evaluation profile

The skill has two modes: author a task before any run, and launch each arm's run. Both run in a chat opened in
this repository, which provides this skill as a project skill. The reproducing agent never runs either mode; it
runs in the arm's own workspace with only the arm's skills.

Never ask the user to do something you can do yourself. Do it, using the saved answers in
[local preferences](../../docs/local-preferences.md) where they apply, and report the result. The user's part is
only what needs a person:

- the decisions that are theirs (author mode);
- for an arm you cannot start yourself: open `ws/`, send the text of its `prompt.md`, answer the agent if the
  run is interactive, stop at the cap.

## Contents

- [Deployment answers](#deployment-answers)
- [Pick the mode](#pick-the-mode)
- [Author mode](#author-mode)
- [Launch mode](#launch-mode)

## Deployment answers

Read [local preferences](../../docs/local-preferences.md) the first time a mode needs a deployment answer.

- For an item still `unanswered`, ask the user once, with its recommendation, and record the answer there,
  relative to this repository's root when it can be. Ask the scheduler items only when the user says runs go
  through Slurm, and fill the Compute wordings from those answers.
- Run every `evaluation.*` command from the repository root with `EVALUATION_BUNDLE_DIR` and
  `REPRODUCTION_RUNS_DIR` set from sections 1 and 2. The code has no default for either.
- Install the Python dependencies once: `python -m pip install -r requirements.txt`.
- Never write a deployment answer into this skill, its references, or the code.

## Pick the mode

- **author**: a benchmark task is named that has no bundle under the bundle root yet.
- **launch**: a set-up task is named, and runs are to start.
- When the user asks to reproduce a task, run author mode if the task has no bundle, then launch mode for each
  arm of the study (section 4 of the preferences).

If the mode is ambiguous, ask.

## Author mode

Inputs, asked in one question when missing: the benchmark (a record in `dataset/tasks/`, or a repository link
or path for a new one), and the `task_id` (default: the benchmark directory name plus dataset, for example
`3d-unet-kits19`).

1. Find or write the dataset record `dataset/tasks/<source_id>.json` ([schema](../../docs/dataset-schema.md)).
   Clone `repo.url` into `repo.path` if the clone is missing, then check out `repo.commit` in it, every time:
   records share clones (every MLPerf record uses `.cache/sources/inference`), so the clone may be at another
   record's commit. Ask the user to approve the commit when the record is new.
2. Read the task repository's own documentation, evaluator, and configuration. Every fact written into the
   record must come from that source, not from this skill and not from memory. Present the options the task
   defines, each with a recommendation, and let the user choose:
   - target(s): each evaluation setup the documentation defines (variants, accuracy or quality classes,
     scenarios or modes), named as the documentation names them;
   - where the task's inputs are cached for runs, as read-only paths under `.cache/<task_id>/`. Fetch the
     datasets and checkpoints there by the documentation's own procedure, and check their counts and published
     checksums, before the preflight check;
   - the result names the evaluator prints, one or several, and the output files each run must write;
   - wall-clock cap: run the preflight check ([protocol](references/protocol.md), "Staging"), a reduced run of
     the task's own benchmark on the task's compute, timed per stage. Show the measured times, the extrapolated
     full-run estimate (labelled an estimate), and a proposed cap. The cap is whatever the user confirms.

   Write the answers into the record. A recommendation the user has not confirmed is not an answer.
3. Mask the reference ([protocol](references/protocol.md), "What the agent may not see").
   - Find every file in the pinned commit that states a reference value for a chosen result: result tables in
     READMEs, accuracy targets in submission or checker code. List each path and line with its excerpt in
     `<bundle root>/<task_id>/masked.txt`.
   - Write `<bundle root>/<task_id>/source.tar.gz` with those values replaced by `<masked>`. It is a
     `git archive` of the pinned commit, so it has no history, limited to the directories the task uses (the
     benchmark directory and what it builds from).
   - Every masked file must still parse and import; check code files with their own parser, for example
     `python -m py_compile`. A value that cannot be removed without breaking the code stays in place, is listed
     as unmasked in `masked.txt`, and the user is told.
   - When the commit states no reference value, `masked.txt` says so and the archive is the unmasked commit.
4. Render the task prompt from the record; never write it by hand:

   ```bash
   python -m evaluation.task_prompt <source_id> [--tasks <the env group's task ids>] \
     --out <bundle root>/<task_id>/prompt.md
   ```

   - The template, [assets/task_prompt.md](assets/task_prompt.md), is fixed; only the record varies.
   - `--out` also writes `tasks.json` beside the prompt: the selected tasks' records, which the prompt points
     to and `prepare` copies into the workspace.
   - When the renderer names a field the record lacks, put the user's answer in the record and render again.
   - Every run and every arm of this task gets this prompt unchanged; a skill arm gets only the added
     invocation line ([protocol](references/protocol.md), "Setup"). A different prompt is a different task.
   - The prompt names no reference value.
5. Write `<bundle root>/<task_id>/manifest.yaml` with `task_id`, `source_id`, and `commit` (the record's pinned
   commit), then seal the bundle. Sealing refuses a manifest that disagrees with the record or the prompt:

   ```bash
   python -m evaluation.bundle seal <task_id>
   ```

   Never edit a sealed bundle while a run against it is in progress. To change a task, edit the record,
   render again, and seal again.
6. Report the `task_id`, the digest, and the masked paths.

Hard rule: the bundle root must resolve outside every directory the reproducing agent works in and reads.
Confirm with `python -c "from pathlib import Path; print(Path('<bundle root>').resolve())"` before writing.

## Launch mode

Prepare each arm of the study ([local preferences](../../docs/local-preferences.md), section 4;
[protocol](references/protocol.md), "Launch") from the repository root:

```bash
EVALUATION_BUNDLE_DIR=<section 1> REPRODUCTION_RUNS_DIR=<section 2> \
  python -m evaluation.prepare <task_id> --arm <plain|skill|builder-skill>
```

- Add `--compute local|slurm|hybrid|cpu` only to override the record's `policy.compute`. Use `local` when the
  preferences say runs execute on this machine.
- Add `--autonomy` when the study's help level is autonomous. Without it, the session stops to ask.
- Add `--model <ID>` with the study's model (section 4). `launch.json` records it, and the Codex command passes
  it; for Claude Code, the user selects it in the session.
- With `--compute local`, compare this machine's GPU (`nvidia-smi`) with the record's `platform` before
  preparing. If they differ, tell the user: the platform is a task fact, so changing it means editing the
  record, rendering again, and sealing again.
- Before the first arm of a study, check isolation on one prepared `plain` workspace ([protocol](references/protocol.md),
  "The operator's configuration stays out of every run").
- Arms whose GPU work runs on the same machine's GPU (`local` or `hybrid`) run one after another; others may
  run at the same time.

Then start each arm yourself where you can; the user should only have to send a prompt or wait:

- Autonomous Codex arm: run `codex_command` from `launch.json` in the background, never a hand-written command,
  so the run receives none of the operator's instructions or skills ([protocol](references/protocol.md), "The
  operator's configuration stays out of every run"). Report the workspace path and that the run has started.
- Any other arm (Claude Code, or an interactive run): reply with only the workspace path the command prints and
  tell the user to open `ws/` itself, not the run directory, as the workspace in a new editor window, and send the
  text of `ws/prompt.md` there unchanged, keeping its first line first. Do not repeat the prompt in the chat.

Tell the user to send every later message to you (the repository chat), only after the run has ended, never in
`ws/`.

After a run, its results are in `ws/report.json`, its delivered script in `ws/reproduce.sh`, and its logs under
`ws/<target id>/out/`.
