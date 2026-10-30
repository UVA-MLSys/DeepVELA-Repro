# {{BENCHMARK_NAME}}

> One or two sentences: what does this benchmark measure, and why does it exist? A reader
> who has never heard of this task should know what they're looking at after this sentence.

**Scientific Motif(s):** {{e.g. High-Energy Physics}}
**AI/ML Motif:** {{e.g. Regression}}
**Computing Motif(s) (optional):** {{e.g. Latency Bound}}

This benchmark card follows the structure defined by the MLCommons Science Benchmarks
Ontology (arXiv:2511.05614) — see `references/ontology.md` in the builder-reproduce skill
for the full definition of each section below.

---

## 1. Problem Specification and Constraints

**Task.** What transformation is being asked for? State it as: given `<input
representation>`, produce `<output>`. Be concrete about representation (image / time-series
/ point cloud / graph / text / tabular / …) and about what "output" means (a label, a
regression target, a generated sample, a policy action, …).

**Inputs.** Exact format, shape, and any preprocessing assumed to already be applied.

**Outputs.** Exact format and shape of what a submission must produce.

**System constraints.** Fixed bounds a valid solution must satisfy that are *not* being
optimized (e.g. target hardware, power budget, latency ceiling, memory ceiling, software
version pins). If there are none, say so explicitly rather than leaving this blank —
"no constraints" is a valid but different answer from "unspecified."

---

## 2. Dataset

**Summary.** Size, source/provenance, and how it was generated or collected.

**Splits.** State the exact split sizes/counts and how they were constructed (random,
stratified, held-out-by-construction, etc.), and confirm they're non-overlapping.

| Split | Size | Purpose |
|---|---|---|
| Train | | |
| Validation | | |
| Test | | |
| (optional) Exemplar / held-out generalization set | | |

**Schema.** Document every field/column in a sample, not just a link to "the data." If
samples are structured records (JSON/Parquet/etc.), list each top-level field and what it
contains.

**Access.** Where the dataset is hosted, under what license, and how it's versioned.

**FAIR checklist** (see `references/ontology.md` Part 2, Category 3):
- [ ] Findable — instances uniquely identified and documented
- [ ] Accessible — persistent, open access protocol
- [ ] Interoperable — community-standard formats/metadata
- [ ] Reusable — versioned, with the generation/preprocessing code public

**Bounded-ness.** State whether augmentation/enrichment of the dataset is permitted for
submissions (default: no, per the ontology's definition of a stable comparison target).

---

## 3. Performance Metric(s)

List every metric, fully defined (formula, not just a name), including how edge cases
(division by zero, empty predictions, ties, etc.) are handled. If there are multiple
targets, state whether metrics are computed per-target, aggregated, or both.

| Metric | Formula / definition | What it captures | Computed on |
|---|---|---|---|
| | | | |

If this is a multi-dimensional (Pareto) benchmark — e.g. accuracy under a fixed latency
bound — say so explicitly and explain how the dimensions relate (which are metrics being
optimized vs. constraints being satisfied).

---

## 4. Reference Solution

**Summary.** What is the reference solution (model/method), and where does its code live?

**Architecture / method.** Enough detail that someone could reimplement it without reading
the code — for a model, this typically means layer structure, hyperparameters, training
procedure, and compute used to train it.

**Results.** The reference solution's own scores on every metric defined above, on every
split they're computed on. This is what a new submission gets compared against.

**Requirements.** Hardware and software needed to run the reference solution.

---

## 5. Documentation and Reproducible Protocol

**Reproduction steps.** Numbered, copy-pasteable steps from a clean environment to
reproducing the reference solution's reported numbers.

**Environment.** Containerized (link the image/Dockerfile) or an explicit, versioned
dependency list plus setup instructions.

**Motivation.** Why does this benchmark need to exist — what gap does it fill, and who
is it for?

**Background.** The scientific/domain context a non-specialist needs to understand why the
task matters.

**Citation.** How to cite this benchmark (paper, if one exists; otherwise a preferred
citation for the dataset/code).

---

## Submission Guidelines

> See `assets/submission_report_template.md` for the report format a new submission to this
> benchmark should follow.
