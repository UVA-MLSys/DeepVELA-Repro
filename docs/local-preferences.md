# Local preferences

This deployment's answers, read by `skills/agent-evaluation-profile`. The file ships unanswered. The agent asks
each item once, the first time a mode needs it, with its recommendation, writes the answer here, and reuses it
in later sessions until the user says it changed. A path is recorded relative to this repository's root when it
can be. Nothing task-specific belongs here: task answers go into the task's dataset record and bundle.

An item reads `Answer: unanswered` until it is answered. A `{{...}}` value in a Compute wording is unanswered;
`evaluation.prepare` refuses to launch with one left in the wording it uses.

Contents: 1 Bundle root; 2 Runs root; 3 Compute and environment; 4 Study; 5 Shared caches.

## 1. Bundle root

Where task bundles (rubrics, masked source, rendered prompt, manifest) and their withheld references live. It must be outside every directory a
reproducing agent reads, so a run cannot see another run's bundle or the unmasked references.

Recommendation: `../evaluation-profiles`.

Answer: unanswered

## 2. Runs root

Where launch mode creates each arm's run directory, `ws/` and `launch.json`. It must be outside this repository
and must not contain, or lie inside, the bundle root.

Recommendation: `../evaluation-runs`.

Answer: unanswered

## 3. Compute and environment

### Where runs execute

Ask first: on this machine (`local`), or through an HPC scheduler. Only Slurm is supported for scheduler runs.

Answer: unanswered

### Scheduler (ask only if runs go through Slurm)

Skip this subsection for `local`. Otherwise ask each item, then fill the `slurm`, `cpu` and `hybrid` wordings
below with the answers.

- Account: unanswered
- GPU partition, and reservation if one is required: unanswered
- GPU request string with the GPU type, for example `--gres=gpu:a100:<count>`. Name one GPU type when the cluster
  has several: throughput is comparable only on one type. Answer: unanswered
- CPU-only partition: unanswered
- Default job time limit: unanswered (recommendation: `01:00:00` unless a task's estimate needs longer)

### Environment strategy

Recommendation: a fresh uv-managed virtual environment per run; a container only if uv cannot build it or imports
need OS libraries this machine lacks.

Answer: unanswered

### Compute wording: local

Appended to a task prompt by `evaluation.prepare --compute local`: every run on this machine's GPU, no scheduler.

```
Compute: run directly on this machine. Do not submit Slurm jobs; every run uses this local GPU. Run GPU work one run at a time; while one runs, start other ready work that uses no GPU (environment builds, downloads, preprocessing) in the background instead of waiting; read launched work's output as it is written, tracking it by its process ID.
```

### Compute wording: slurm

Appended by `--compute slurm`: smoke tests on this machine when safe, every long or full run as a Slurm job.

```
Compute: Run a smoke test on this machine only when it can run safely here: the hardware it needs is present, and it is bounded to a few samples and a few minutes. Otherwise submit it as a short Slurm job. Treat a run as long unless you are confident it is short. Run every long run and every full run as Slurm jobs, account {{account}}: a run that uses GPUs on {{GPU partition and reservation}}, with the GPU count the Platform line states ({{GPU request string}}); a CPU-only run on partition {{CPU partition}}. Do not run long work on the login node. Start every command whose inputs are ready, in the background or as a Slurm job, and continue with other ready work instead of waiting; read launched work's output as it is written, tracking it by its process or job ID. Cancel or modify only Slurm jobs you started.
```

### Compute wording: cpu

Appended by `--compute cpu`: a task that uses no GPU.

```
Compute: Run a smoke test on this machine only when it can run safely here: it is bounded to a few minutes and a few cores. Otherwise submit it as a short Slurm job. Treat a run as long unless you are confident it is short. Run every long run and every full run as Slurm jobs, account {{account}}, partition {{CPU partition}}, with the core and memory count the Platform line states. Do not run long work on the login node. Start every command whose inputs are ready, in the background or as a Slurm job, and continue with other ready work instead of waiting; read launched work's output as it is written, tracking it by its process or job ID. Cancel or modify only Slurm jobs you started.
```

### Compute wording: hybrid

Appended by `--compute hybrid`: GPU work on this machine's GPU, every CPU-only run longer than a few minutes on Slurm.

```
Compute: run every run that uses a GPU directly on this machine's GPU, and submit no GPU Slurm job. Submit every run that uses no GPU and takes longer than a few minutes, including CPU-only targets, environment builds, downloads and preprocessing, as a Slurm job: account {{account}}, partition {{CPU partition}}, time limit at most {{CPU job time limit}}. Run GPU work on this machine one run at a time; while one runs, start other ready work that uses no GPU (environment builds, downloads, preprocessing), in the background or as a Slurm job, instead of waiting; read launched work's output as it is written, tracking it by its process or job ID. Cancel or modify only processes and Slurm jobs you started.
```

## 4. Study

Choices that hold for every task of one study ([protocol](../skills/agent-evaluation-profile/references/protocol.md)).

- Arms to run: `plain` (no reproduction skill), `skill` (Reproduce), `builder-skill` (Builder + Reproduce).
  Recommendation: all three. Answer: unanswered
- Agent harness and model, the same for every arm: Claude Code or Codex, and, for Codex, the model ID and
  reasoning effort, which launch mode passes as `--model` and `--effort`. Answer: unanswered
- Judge for claims a rubric checks by reading the transcript (`EVALUATION_JUDGE`): `codex` (the `codex` CLI must
  be on `PATH`, or `CODEX_BIN` set) or `claude:<model ID>`. A judge from the same vendor as the agents under test
  favors their output, so recommend the other vendor. Answer: unanswered
- Help level: autonomous (`--autonomy`, no human replies) or interactive (the user answers the agent).
  Recommendation: autonomous for comparisons between arms. Answer: unanswered

## 5. Shared caches

Every cache, dataset and package store is shared across runs and arms, never made per run: the uv package cache
at `.cache/uv`, raw inputs under `.cache/<task_id>/`, and benchmark source clones under `.cache/sources/`, all in
this repository's root. Each task prompt names `UV_CACHE_DIR` and the input paths. Only generated artifacts
(environments, preprocessed data, logs, outputs) are per run.
