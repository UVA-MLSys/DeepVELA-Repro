# Task dataset schema

A dataset record describes one benchmark source and the tasks it provides. `evaluation/task_prompt.py` renders a
task prompt from a record through the fixed template `skills/agent-evaluation-profile/assets/task_prompt.md`, and
writes the selected tasks' records to `tasks.json`, which the agent receives beside the prompt. Records live in
`dataset/tasks/<source_id>.json`; a controlled study's records live in `dataset/tasks/<study>/<name>.json`.
Author mode (`agent-evaluation-profile`) writes and edits records from your answers; this page is the format it
follows.

## Unit

A **source** is a repository at a pinned commit. It provides one or more **tasks**, each one terminal evaluator
invocation (a target, in the Reproduce skill's terms). An **env group** is a set of tasks that share one
environment build; one session covers the env groups its bundle selects. The record holds the documentation's
entry command, not the environment procedure: recovering that procedure is part of the run.

## Example

```json
{
  "source_id": "mlperf-language-bert",
  "repo": {"url": "https://github.com/mlcommons/inference.git", "path": ".cache/sources/inference",
           "commit": "3fbc3299...", "directory": "language/bert"},
  "domain": "question answering", "language": "Python",
  "support_level": "readme_only",
  "policy": {
    "compute": "slurm",
    "platform": "one NVIDIA A100 80GB GPU per run.",
    "inputs": {"SQUAD_DIR": {"path": ".cache/bert-squad/data", "holds": "dev-v1.1.json"}},
    "forbidden": "the MLPerf Inference results repositories (mlcommons/inference_results_*), ...",
    "wall_clock_cap": "2 hours"
  },
  "env_groups": [{"id": "bert-squad-env", "tasks": ["bert-squad"]}],
  "tasks": [{"id": "bert-squad",
             "task_prompt": "Run `python3 run.py --backend=pytorch --accuracy` ...",
             "results": ["exact_match", "f1"],
             "outputs": {"accuracy.txt": "the evaluator's stdout"},
             "log_lines": {"pytorch device: ": "the device the model's parameters are on"}}]
}
```

## Fields

| Field | Meaning |
|---|---|
| `repo` | `url` to clone, `path` of the local clone relative to this repository's root, pinned `commit`, and the benchmark `directory` inside the repository |
| `support_level` | `readme_only`: the repository's documentation, with no prepared environment or Dockerfile |
| `policy` | Source-level answers, given once for every task. A field left out has not been answered, and rendering stops naming it |
| `policy.compute` | Default for `evaluation.prepare --compute`: `local`, `slurm`, `hybrid`, or `cpu` |
| `policy.platform` | The hardware each run gets |
| `policy.inputs` | Read-only input directories, relative to this repository's root, each with what it `holds`; `{}` when the agent fetches every input |
| `policy.forbidden` | Resources the run may not access, such as the task's published results |
| `policy.wall_clock_cap` | The session's time limit, confirmed by the user at setup |
| `task_prompt` | Entry instruction: the documented command, the dataset it runs over, and the evaluator |
| `results` | Names the evaluator prints; the keys of `report.json` |
| `outputs` | Files `./reproduce.sh` writes to `OUTPUT_DIR`, each mapped to what it holds |
| `platform` | Per task, when it differs from `policy.platform` |
| `log_lines` | A line prefix the run's logs must contain, and what follows it |
| `hints` | Help fixed before the run, the same for every arm |
| `inputs` | Per task, repository files the agent fetches itself |

## Writing a record

The prompt is the record rendered through a fixed template, so a sentence in the prompt is a sentence someone
wrote in the record. Every fact appears once, in the one field that owns it.

| Field | Write | Do not write |
|---|---|---|
| `task_prompt` | The entry command the documentation gives, the dataset it runs over, and the evaluator. | Environment steps, paths (the Inputs block gives them), or anything `results`, `outputs`, `log_lines` or `platform` already carry. |
| `holds` | What the directory contains, only when no `task_prompt` says it. | A file name or model a `task_prompt` already names. |
| `outputs` | Each task's own files, with what each holds. | A file nothing reads. |
| `log_lines`, `platform` | Only what a run must show, or what differs from `policy.platform`. | A restatement of the policy value. |
| any field | A decided value. | A placeholder (`<device>`) or a choice such as "CPU or GPU"; rendering stops on a `<...>` left in `task_prompt` or `platform`. |

Do not repeat a shared path prefix by hand; the renderer states it once as `CACHE_ROOT`. Before using a new
record, render it and read the prompt once for any sentence that repeats another.

## Records shipped

The MLPerf Inference sources (`mlperf-*.json`) and the 3D U-Net controlled-study record
(`mlperf-c0-c6/3d-unet-kits19.json`). Every shipped record renders.
