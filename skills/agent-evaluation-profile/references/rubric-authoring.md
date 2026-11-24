# Rubric authoring

How to write a task's evaluation bundle: its layout, rubric files, task manifest, and digest.
Scores and verdicts are defined in [protocol](protocol.md).

## Contents

- [Bundle layout](#bundle-layout)
- [One profile, many metrics](#one-profile-many-metrics)
- [What is a rubric](#what-is-a-rubric)
- [Rubric file](#rubric-file)
- [Criticality](#criticality)
- [Cold and warm cache conditions](#cold-and-warm-cache-conditions)
- [Task manifest](#task-manifest)
- [Multi-target tasks](#multi-target-tasks)
- [Before reporting the bundle done](#before-reporting-the-bundle-done)

## Bundle layout

```text
<profile folder>/                   # the bundle root itself, or <bundle_root>/<profile_id>/ in a root holding several profiles
  bundle.yaml                       # profile ID/version, phase order/labels, template registry; the only copy of this content
  rubrics/<template_id>.yaml        # one atomic claim each, profile-wide defaults
  <task_id>/                        # older bundles nest it as tasks/<task_id>/; the code reads either
    manifest.yaml                   # task identity, quality contract, input-reuse contract
    rubrics/<rubric_id>.yaml        # task-specific rubrics and per-task overrides
  checkers/<name>.py                # only when a built-in primitive cannot express the check
  MANIFEST.sha256                   # sorted "sha256  relative/path" for every file above
```

A controlled study (one task under several reference conditions) gets one folder of its own, recorded
in local preferences: its profile folder, with `runs/` inside as its runs root. Each version is one folder
and each condition one task folder in it, so the task id is `<task>-<version>/<condition>`
(`3d-unet-kits19-v2/c5`); runs then land in `runs/<task>-<version>/<condition>/`. Its prompts render from
its own dataset record, `dataset/tasks/<study>/<name>.json`; never edit the full task's shared
record for a study.

A starting `bundle.yaml` is in [assets/bundle.yaml](../assets/bundle.yaml).

## One profile, many metrics

`profile_id` names a reproduction *shape* (the phase list and rubric claim shapes), not a task and
not a metric. One shape covers every source: the profile
`reproduce`, with one `tasks/<task_id>/` per task underneath it and four phases:

- `environment`: the toolchain and dependencies work;
- `inputs`: source, data, and model are present;
- `execution`: the documented route ran in full on the required scope;
- `result`: the benchmark's own evaluator ran and its value is accepted.

The phases follow the stages related work separates (PaperBench's Execution and Result Match
leaves, ResearchEnvBench's environment stages). A task never
gets its own profile just because its metric differs.

The metric's identity lives entirely in the task, never in the profile (models in
`evaluation/schema.py`; the bundle loads with `python -m evaluation.scorer`):

- `QualityContract.result_name_type_and_direction` and `acceptance_rule` are free text, authored
  per task from that task's own documentation: `"mean_dice, float, higher_is_better"` for 3D-UNet,
  `"F1, float, higher_is_better"` for BERT, `"MSE, float, lower_is_better"` for a regression task.
  Nothing in this skill enumerates metric names.
- `PhaseRubric.checker` is an untyped `{kind, args}` dict. Each task names its quality rubric in
  its manifest's `quality_rubric_id`, and the scorer reports that rubric's metric as the task's
  quality result. Its claim ("the reported metric satisfies the acceptance rule the user chose")
  can be shared across the tasks of a profile, while each task sets its own checker args at setup.
- For a relative tolerance, use `builtin.numeric_relative_error_within` with `references` (one
  entry per metric the user chose) and `max_relative_error` (the user's tolerance: one number, or
  one per metric).
  - Cite the reference the user chose in `source_refs`: the published-results file or page, the
    fields that identify the entry, and the value's excerpt exactly as written there.
  - For an MLPerf `runs.csv` row: round, submitter, system, benchmark, and scenario, with the
    `accuracy_raw` excerpt (CSV doubles embedded quotes).
  - This checker compares symmetric relative error, which is the wrong tolerance for a metric that
    is already a percent: a 1% relative band around an error rate of 2% is 0.02 points.
- For a one-sided or absolute rule the user chooses instead, such as MLPerf's `accuracy-target`
  (lower bounds) or `accuracy-upper-limit`, or an absolute band such as the reference plus or minus
  1 point, use `builtin.metric_bounds` with `bounds: {<metric>: {min: <x>, max: <y>}}`, either side
  optional. Cite where each bound comes from; for MLPerf, the `constants.py` line, e.g.
  `"resnet": ("acc", 76.46 * 0.99)` gives `accuracy: {min: 75.6954}`.
- For a metric the task publishes no value for, use `builtin.metric_bounds` when the user sets
  bounds, else `builtin.reported_value_in_output` alone as the quality rubric, with
  `reference_value` left unset. The reported value must still be supported by evaluator output.
- A metric rubric names the metric by the key the evaluator prints (`metric_name`, or the keys of
  `references`), because the fixed task prompt asks every arm to write `report.json` with those
  keys. Without it, the scorer falls back to the first field of `result_name_type_and_direction`
  and fails closed on any other name.
- Pair a metric rubric with `builtin.reported_value_in_output` on the same metrics, with `files`
  globs for the evaluator's log, so a reported value counts only when the evaluator printed it.
- The reference value and thresholds live only in the rubric args, which the agent never sees.
- A bundle authored before these rules is re-authored this way the next time its task is
  reproduced, with the user, not in bulk.

Only author a new `profile_id` when the reproduction *structure* itself differs: no calibration
set, no backend a preflight check can exercise, a fundamentally different evaluator shape, or a
non-MLPerf domain using `source_setup`/`build`/`execution`/`test_validation` phases and a pass/fail
test-suite verdict instead of a numeric metric.

Seal the bundle last, which checks the task manifest and regenerates `MANIFEST.sha256`. The harness reads
the lines for `bundle.yaml`, `checkers/`, `rubrics/` and the task's folder only
(`evaluation.bundle.bundle_digest`), so authoring one task never changes another task's digest:

```bash
python -m evaluation.bundle seal <profile_id> <task_id>
```

The manifest lists every file under the profile folder except `runs/`, `audit/`, `README.md` and itself, as
`sha256  ./relative/path`.

## What is a rubric

A rubric is one verifiable outcome with a single pass/fail answer, checkable from evidence every
arm produces the same way: the workspace files, the command outputs in the transcript, and
`report.json`. A record that one arm's skill asks the agent to keep (`effect_ledger.jsonl`,
`reproduction.md`) is never evidence, because the other arms do not write it.

- "The KiTS19 evaluation split contains the 42 documented case directories" is a rubric.
- "The agent prepared the data" is not: it names an activity, not an outcome.
- "The agent ran `make download_kits19`" is not: it names a command, and a different supported
  route reaching the same outcome must pass.

Write the claim so that the benchmark's own documentation is the reason it is required. If the
source does not require it, it is not a rubric for this task.

## Rubric file

```yaml
rubric_id: kits19_eval_split_case_count
phase_id: data_model_preparation          # must exist in the bundle's phase list
claim: The acquired KiTS19 evaluation split contains exactly the documented case directories.
critical: true                            # required for phase success and end-to-end success
cache_conditions: [cold, warm_raw_inputs_v1]
source_refs:
  - path: vision/medical_imaging/3d-unet-kits19/README.md
    sha256: <64 hex>
    excerpt: "the inference set consists of 42 cases"
prerequisites: []                         # other rubric IDs, only when logically necessary
evidence_contract:
  artifacts:
    - kind: directory
      path_from: manifest.inputs.kits19_eval_dir
checker:
  kind: builtin.directory_entry_count     # or external: checkers/<name>.py
  args:
    path_from: manifest.inputs.kits19_eval_dir
    expected: 42
    pattern: "case_*"
pass_threshold: 1.0
```

Prefer the `builtin.*` kinds in `evaluation/checkers.py`:

- `builtin.landmark` (`pattern`, optional `files` globs): an output pattern from the benchmark's own
  tools that shows a step ran, found in any command output in the transcript or a workspace file.
  This is SUPER's landmark ([protocol](protocol.md), "Phase checks"). Take the pattern from the
  tool's source or documentation and cite it in `source_refs` (for MLPerf, LoadGen's mode and
  scenario lines in `mlperf_log_detail.txt`, or the evaluator's summary line with the full sample
  count). Never take it from a previous run's log, and never use a string only one route prints;
  A landmark asserts no more than the task prompt requires: for a log line the prompt names by prefix
  (`log_lines`), the pattern is that prefix and the value the prompt describes, not the exact spacing or
  punctuation of one implementation. The checker treats runs of spaces and tabs as one space;
- `builtin.artifact_exists`, `builtin.file_hash_equals`, `builtin.artifact_hash_matches`,
  `builtin.directory_entry_count`, `builtin.directory_contains_all`: files, hashes, and counts. A
  `path` is a glob under the workspace; a `path_from` resolves through the manifest's
  `artifact_paths`, absolute for an input read from the cache, else under the workspace's `repo/`;
- `builtin.numeric_relative_error_within`, `builtin.metric_bounds`: the values in `report.json`;
- `builtin.reported_value_in_output`: each value in `report.json` appears in an evaluator output
  file selected by the rubric's required `files` globs.

When a check needs benchmark knowledge, write it as an external checker file inside the bundle.

## Criticality

`critical: true` only when the benchmark's own contract fails without it. A critical rubric that
fails makes its phase and the end-to-end result fail, so a rubric that encodes a preference rather
than a requirement must be `critical: false`.

## Cold and warm cache conditions

A rubric that only exists because inputs had to be acquired belongs to the cold condition. In a
warm run it is `not_applicable` with the cache condition as the recorded reason. It is not a free
pass, and it is not counted in the denominator.

- Cold only: dataset download completed, checkpoint download completed, download provenance
  recorded.
- Both conditions: input identity, integrity, structure, preprocessing, calibration, and every
  rubric in the inference and validation phases.

Preprocessing outputs, environments, converted models, logs, metrics, and evaluator output are
never inheritable in any condition. State that in the task manifest's input-reuse contract:

```yaml
input_reuse_contract:
  cache_condition_id: warm_raw_inputs_v1
  allowed_cache_roots: [.cache/3d-unet-kits19/kits19_raw_data, .cache/3d-unet-kits19/model]
  allowed_artifact_classes: [raw_dataset_download, model_checkpoint_download]
  package_cache_class: pip_wheel_cache     # declared separately; it changes environment build time
  forbidden_artifact_classes: [environment, preprocessed_data, converted_model, log, output, metric]
  required_identity_and_hashes: [...]
```

For the cold condition, name per-run cache roots in `allowed_cache_roots` instead of the
deployment's shared cache locations. Otherwise the shared `HF_HOME`, `HF_HUB_CACHE`, and
`PIP_CACHE_DIR` values make a cold run impossible.

## Task manifest

```yaml
task_id: <task_id>
profile_id: <profile_id>
profile_version: 1
suite_role: development              # development | regression | held_out
source_revision: <git sha>
objective: <the exact objective text the run will receive>
quality_rubric_id: <the rubric whose checker decides the quality result>
domain_identity:                     # the identity fields the task's documentation defines
  <field>: ...
quality_contract:
  evaluator_identity: <official evaluator path>
  result_name_type_and_direction: <metric>, <type>, <higher_is_better | lower_is_better>
  reference_value: <the reference the user chose>
  acceptance_rule: <quoted from the benchmark source>
  source_path_sha256_excerpt: {path: ..., sha256: ..., excerpt: "..."}
input_reuse_contract: {...}
authored_by:
  model_id: <authoring model>
  authored_at: <date>
  source_revision: <git sha>
  reviewed_by: <human or "pending">
```

`suite_role` follows the split of the task's benchmark directory: every task under one directory
shares a split ([protocol](protocol.md), "Split").

`suite_role: held_out` requires that no prior reproduction run, generated result, or
developer-guided repair trace for this workload is visible to the run. Check
the runs root and the benchmark's own run directory before claiming it.

## Multi-target tasks

A source with several documented results is one task with a `targets:` map in `manifest.yaml`
(`protocol.md`, Tasks section, defines a target). Replace `quality_contract` and
`quality_rubric_id` by one entry per target holding its own `quality_rubric_id`, `quality_contract`,
and `shared_rubrics`; other keys describe the target.

- The task's `rubrics/` holds every rubric file; the bundle's phase templates are not used. Each file
  names its `phase_id` and a `target` (a key of `targets`, or null for a rubric shared by targets).
- A target is scored on its own rubrics plus the target-less rubrics in the closure of their
  `prerequisites`; `shared_rubrics` must list exactly those, and the loader rejects a mismatch. A
  rubric shared by two targets (a raw dataset both read) is authored once.
- Rubrics that read `report.json` set `report_path: [<target id>]` and `metric_name` in
  `checker.args`; the task prompt asks for a report nested by target id.
- A target's rubric reads workspace files only. The scorer drops transcript command output for it,
  since one command may have run several targets.
- The prompt must state where each target's logs and outputs go (`<target id>/`), and the rubric
  globs must be satisfiable from that layout.
- A requirement that only a log can show (for example the execution provider of a GPU run) is a
  prompt requirement plus a landmark rubric on that log.

## Before reporting the bundle done

- every `phase_id` exists in the bundle's phase list;
- every `source_refs` hash matches the file it names, verified with `sha256sum`;
- every excerpt appears verbatim in that file;
- no rubric names a command;
- no rubric duplicates the terminal quality acceptance rule;
- `MANIFEST.sha256` is regenerated last and reported.
