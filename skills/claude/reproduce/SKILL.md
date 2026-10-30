---
name: reproduce
description: Reproduce a documented benchmark from its task prompt and repository documentation through a measured, clean-copy result.
---

# Reproduce

The task prompt is the run contract. The repository's documentation and source come second.

- Do not reopen what the prompt fixes: benchmark, target, commit, inputs, resources, cache, metric,
  budget, layout, report.
- The prompt's compute rule bounds the schedule: where each kind of work runs and what must run one
  at a time. Within those bounds, the plan chooses the order and the parallelism.
- A missing convenience mechanism, such as a download or launch wrapper, is the agent's work.

## Stages

The stages give the execution order; they are not approval gates. Their names follow the paper's
description of the human-in-the-loop workflow.

Order:

1. Read contract, Plan the full run, and Report measured results cover the whole run. Every other step runs per target: each target moves through it on its own.
2. Plan the full run follows the preflight of the targets it measures, not of every target. The plan schedules the remaining targets' steps.
3. Move on when the step's output exists.
4. Read each target's output as soon as it is written, not when its batch ends.
5. A target whose full run fails returns to Preflight check and repair; the other targets continue.
6. On resume, of a session or of a batch, find the last step that succeeded and continue there. Never redo a step that succeeded.

| Stage | Step | Reads | Leaves behind |
|---|---|---|---|
| Establish and plan | Read contract | task prompt, `docs/local-preferences.md` and a benchmark card (`BENCHMARK_CARD.md`) when the workspace has them | fixed facts and open questions, stated together before work begins |
| Inspect and prepare | Inspect source | README, launcher, evaluator, environment files, configuration, existing scripts | per target: route, inputs, evaluator, metrics, supporting source paths |
| Inspect and prepare | Set up environment and data | environment and HPC/container instructions, input requirements | working environment; inputs present and counted, with checksums where published |
| Inspect and prepare | Preflight check and repair | documented route, environment, inputs, any quick mode | per target, the evaluator output of a bounded run of `reproduce.sh`; per-stage time and resource use |
| Establish and plan | Plan the full run | preflight measurements, the resources the compute rule gives, the time limit | `plan.md` (see Plan and re-plan), written before launch |
| Execute and wait | Full run and evaluation | `reproduce.sh`, documented command, prompt resource requirements | full-run logs, prompt-required files, output directory, evaluator output |
| Record and close | Report measured results | evaluator output of the full run, prompt report contract | `report.json` and every required artifact |

```
./                              workspace
├── repo/                       pinned source
├── reproduce.sh                written in Preflight check and repair, run unchanged in Full run and evaluation
├── <target id>/                multi-target tasks only
│   └── out/                    that target's OUTPUT_DIR
├── plan.md                     written in Plan the full run, updated on each re-plan
├── report.json                 written in Report measured results
├── reproduction.md             optional record
└── effect_ledger.jsonl         optional record
```

## Situations

| Situation | Class | Action |
|---|---|---|
| Download or launch wrapper missing for a documented source | repairable | write it, semantics unchanged |
| Dataset, split, metric, or task definition unspecified | blocked | stop, show evidence, ask |
| Route must change backend, precision, dataset, model, evaluator, scenario, profile, preprocessing, or generation semantics | departure | propose, wait for an explicit human reply, then edit or launch |
| The same failure type persists after 3 repair attempts, in Preflight or the Full run | stop | show evidence, ask |
| Full run covers less than the scope fixed in Read contract and Inspect source | stop | show evidence, ask |
| Anything else in the stage table | proceed | no question |

Scope and replies:

- A blocked or stop situation ends the work on that target only (the run, for a single target). The other targets continue.
- If the prompt does not state that no human will reply, the actions above stand and the default is to stop and ask.
- If it does, no situation waits for a reply:
  - departure: state it, its reason, and its evidence in the message before the edit, then apply it;
  - blocked or stop: record what was measured in `report.json`, state the failure with its evidence, and stop that target's work.

## Step rules

| Step | Rule |
|---|---|
| Read contract | Ask only for facts the prompt omits and the saved preferences lack or contradict (see Preferences). |
| Read contract | A benchmark card states the task, data, metrics, evaluator and reference command with their sources. Use those facts in Inspect source; the prompt still fixes scope, and a conflict between card, prompt and source is stated with its evidence. |
| Inspect source | Use the documented environment and route. |
| Inspect source | Start from the documented command and its documented flag values. Where the documentation is silent, or a documented value fails, choose the value, and state the change, its reason, and its evidence in the message before applying it. |
| Inspect source | Reuse existing launchers, wrappers, containers, checkpoints, and evaluators before writing replacements. |
| Inspect source | Establish source revision, dataset version and split, input structure and counts, model or checkpoint, backend and precision, evaluator metrics and direction, and launch protocol. |
| Inspect source | A target is one terminal evaluator invocation. A different model, backend, precision, dataset, scenario, or mode is a separate target. |
| Inspect source | The user may name one target, several, or all. If the user names none, list them and ask, offering all. |
| Inspect source | Reuse a derived artifact across targets only when its producer, inputs, and parameters are identical. |
| Set up environment and data | Inspect compatible modules before installing packages or compiling extensions. |
| Set up environment and data | Use a documented container workflow only when the module path is unavailable or fails the stated constraints. |
| Set up environment and data | Resolve dataset, checkpoint, cache path, split, structure, counts, and checksums before any expensive run. |
| Preflight check and repair | Get the quickest safe evidence that each target runs end to end, cheapest first: startup, import, model or checkpoint load, one preprocessed input, a few samples through the evaluator, official quick mode. |
| Preflight check and repair | Size each check to what the machine it runs on can hold. |
| Preflight check and repair | A bounded run is evidence only for the workload it contains. Split the full run's input into its sub-workloads (datasets, languages, input kinds, stages) and include samples from every one in the bounded run that sizes the plan. A sub-workload left out is a cost the plan does not cover. |
| Preflight check and repair | For a multi-target task, measure a few targets of different sizes, not only the first in the list. |
| Full run and evaluation | Only bounded validation precedes the first full run. |
| Full run and evaluation | Validate a change to throughput, batching, memory or output on a bounded run of the sub-workload it affects before submitting it as a full run. The full run tests the delivered script; it is not where a fix is tried. |
| Full run and evaluation | The first full run is the delivered `reproduce.sh` under the clean-copy conditions the grader uses. Never run a full benchmark from a prepared environment and rebuild the script afterward. |
| Full run and evaluation | Keep any wrapper the prompt requires around the benchmark command enabled in that run. |
| Full run and evaluation | Split `reproduce.sh` into stages wherever the resource kind changes: environment build, input download and preprocessing (CPU-only), and the accelerator run. Each stage runs alone (`--stage <name>`) and hands its output to the next through files. |
| Full run and evaluation | With no `--stage`, the script runs every stage under the prompt's compute rule. It never requests an allocation its caller already holds, and it submits a job only where the compute rule assigns submission to the script. Each job it submits requests only the resource its stage uses and starts after the jobs whose output it reads have finished. |
| Full run and evaluation | Preflight runs stages alone. The full run is the no-`--stage` path, as the grader runs it. |
| Report measured results | Run the benchmark-owned evaluator over the scope fixed in Read contract and Inspect source, and write the requested report exactly. |
| Report measured results | Do not self-score. |

## Plan and re-plan

Plan the full run from measurements before launching it. While it runs, derive the plan again from
what has finished and failed.

### The plan

| Field | Content |
|---|---|
| Workload | the targets, their stages, and what each stage depends on |
| Measured costs | time and resource use (CPU cores, accelerator, memory) per stage, from preflight |
| Resources | what the compute rule gives each kind of work: for work on this machine, its cores, accelerators, and memory, less what other users hold; for scheduler jobs, what a job can request |
| Schedule | stage order, parallelism per resource, and what overlaps with what, within Batches over targets |
| Expected time | the total, from in order: repository documentation, comparable runs, the preflight measurements |
| Reserve | time held back before the limit for `report.json`, the required artifacts, and a final check of `reproduce.sh` |

Rules:

1. Treat the full run as long unless the estimate shows it is short. A reduced run is estimation evidence, not the full run.
2. When the expected time exceeds the time limit less the reserve, change the schedule before launch. If no schedule fits, say so with the numbers.
3. State which measured number drives each scheduling decision.

### Re-plan

| Trigger | Action |
|---|---|
| The first few percent of the full run have finished | Compare the measured rate with the plan. If the projection moves past the limit less the reserve, change the schedule. |
| Failures appear | Group them by failure type from the log line that shows it. Fix each type once for every target it affects, then queue those targets again. |
| A resource sits idle while work waits for it, or is saturated | Change the parallelism of the stages that use it. |
| The projection still passes the limit less the reserve | State which targets will not finish and why, with the numbers. |
| The remaining time reaches the reserve | Start no new work. Write `report.json` and the required artifacts from what was measured. |

Record each re-plan in `plan.md` and state it in one message: the trigger, what changed, and the new projection.

## Batches over targets

A multi-target task runs as a pipeline, not as one stage at a time across all targets.

1. The driver calls the delivered `./reproduce.sh --target` from the workspace, never a copy of it or of the repository.
2. A target's accelerator stage starts as soon as that target's own earlier stages succeed. It never waits for other targets' builds or downloads.
3. CPU stages (downloads, builds, repairs) run beside it on the cores the accelerator stage leaves free. Under contention, lower their parallelism; do not stop them.
4. A repaired target goes back into the queue; the queue keeps moving while repairs happen.
5. A step succeeded when its stage wrote a success marker file beside its output after every command of the stage exited 0 (for the run stage, its evaluator too). A stage shared by several targets under the reuse rule has one marker, beside the shared output. The driver skips each step whose marker exists, so restarting it, or a new session, never repeats finished work and needs no chat history.
6. A repair deletes the markers of the stage it changes and of every later stage that reads its output, so the changed stage and everything after it run again.

## Preferences

Preferences cover what the prompt does not fix. Use them only when the workspace has
`docs/local-preferences.md`; without one, do not create it.

1. Read the file and show which saved answers still apply.
2. Ask once for the rest.
3. Write the resolved values back to the file and show what was written.

| Field | Values |
|---|---|
| Execution target | local or scheduler; account, partition, reservation, GPU string, wall time |
| Environment strategy | documented route; modules first; container as fallback |
| Cache and download locations | paths |

- Never guess an account, partition, reservation, or cache path.
- Never store task facts (revision, target, metric) in the file.

## Optional records

Write these only when the user requests them. They support resuming and auditing long or
multi-session runs. They never replace transcript or workspace evidence, and the scorer does not
read them.

| File | Content |
|---|---|
| `reproduction.md` | source facts, route decisions, links to raw artifacts; per target: `id`, `question`, `design`, `data`, `inputs`, `evaluator`, `depends_on`, `status`, `reference` |
| `effect_ledger.jsonl` | one JSON object per action: action, effect, timestamp, evidence paths |

After a mid-run repair of this skill:

1. Replace the workspace copy from the committed revision and record that revision.
2. Invoke the skill again and resume.
