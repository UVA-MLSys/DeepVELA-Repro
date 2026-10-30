# The MLCommons Science Benchmarks Ontology

Source: Hawks et al., "An MLCommons Scientific Benchmarks Ontology," arXiv:2511.05614
(companion effort to the MLCommons Science Working Group, https://mlcommons-science.github.io/benchmark/)

This file condenses the paper: the definition of a benchmark (Section II), the rubric that rates
one (Section III), and the domain and task taxonomy that classifies one (Section IV). Read it in
full before interviewing a user or scoring a benchmark. The rubric wording matters because the
scoring script and the user both depend on you applying it consistently.

## Contents

- [Purpose](#purpose)
- [Part 1: The five definitional elements of a benchmark](#part-1-the-five-definitional-elements-of-a-benchmark)
- [Part 2: The six-category rating rubric](#part-2-the-six-category-rating-rubric)
- [Part 3: Motif taxonomy](#part-3-motif-taxonomy)
- [Part 4: Users the ontology serves](#part-4-users-the-ontology-serves)

## Purpose

Scientific ML benchmarking is fragmented: siloed efforts, datasets without concrete tasks,
non-reproducible code, undefined metrics. The ontology gives every benchmark a common structure
(five elements) and a common rating (six categories), so that ML practitioners, domain scientists,
and hardware vendors can find and trust benchmarks outside their own subfield. The goal is a
benchmark all three audiences can use, not a maximal rubric score.

## Part 1: The five definitional elements of a benchmark

A benchmark is "a carefully defined standardized version of a scientific application that
is used for making quantifiable comparisons of solutions." It has five required parts.

### A. Problem specification and constraints

A short statement of the benchmark **task**:

- the input data: its origin and representation (image, time series, point cloud, text, graph);
- the expected output: the transformation (regression, classification, anomaly detection,
  generation);
- any **system constraints**.

Constraints are quantifiable bounds (power, latency, throughput) or system specifications
(hardware platform, technology node) that are not part of the performance metric. A solution must
satisfy them; it does not optimize them.

### B. Dataset

The input data, and truth labels where they apply. It must follow **FAIR**:

- **Findable**: each instance is uniquely identified and documented.
- **Accessible**: access uses persistent, open protocols.
- **Interoperable**: formats and metadata follow community standards.
- **Reusable**: the data is versioned, with preprocessing scripts, so it can be reproduced in full.

The dataset is **bounded**: no augmentation, enrichment, or post-hoc curation unless the benchmark
explicitly allows it, because the target must stay stable. The benchmark provides a canonical,
non-overlapping train/validation/test split.

### C. Performance metrics

Quantifiable measures for comparison. Metrics are what is optimized or compared; constraints are
fixed bounds. A benchmark can be multi-dimensional (a Pareto front, for example accuracy and
latency). Metrics must be well defined, reproducible, and computable from the validation or test
data. One dataset can support several benchmarks with different metrics or constraints; for
example, one variant bounds accuracy and measures throughput, another measures accuracy only.

### D. Reference solution

A solution that satisfies the problem specification and constraints on the defined dataset, with
its metrics measured as the **baseline** other solutions are compared against.

### E. Documentation and reproducible protocol

A protocol to reproduce the reference solution, so other submissions can be compared directly.
Usually this is reference code in a versioned, well-defined software environment. If hardware is
involved, it includes thorough documentation and a bill of materials.

## Part 2: The six-category rating rubric

Each of the six categories is scored **0 to 5**. The overall rating is the **average of the six
category scores**, so it is also out of 5, not out of 30. A benchmark with an overall average of
**≥ 4.5 / 5** earns the "MLCommons Science Benchmark Endorsement."

Five of the six categories are checklists: one point per true statement, maximum 5. Dataset and
Performance Metrics have their own internal weighting, given below so that scoring is
deterministic.

### 1. Software environment (1 point each, max 5)

- [ ] Code is available to reproduce the baseline reference solution.
- [ ] The provided code is complete.
- [ ] The code itself is well documented.
- [ ] The code does not require any modifications to run.
- [ ] The environment is either containerized, or environment details and setup
      instructions are provided.

### 2. Problem specification and constraints (1 point each, max 5)

- [ ] System constraints (power, latency, throughput, etc.) are provided.
- [ ] The benchmark task is clear.
- [ ] The dataset format is clearly specified.
- [ ] The task inputs are clearly specified.
- [ ] The task outputs are clearly specified.

### 3. Dataset (max 5)

One point for each FAIR principle followed (max 4), plus one point if well-defined
train/test(/validation) splits are present (max 1).

- [ ] Findable
- [ ] Accessible
- [ ] Interoperable
- [ ] Reusable
- [ ] Well-defined train/test(/validation) splits are present

### 4. Performance metrics (max 5)

Two sub-scales that sum to the category score. This category grades on a scale rather than a
checklist because a half-defined metric is a different failure from a well-defined metric that
does not capture performance.

**Metric definitions (max 3):**

- 3: metrics are fully defined.
- 2: metrics are clearly mentioned, but specific details or implementation are not defined.
- 1: some metrics are mentioned but not clearly defined (what is tracked is ambiguous).
- 0: no metrics are mentioned or defined.

**Metric quality (max 2):**

- 2: the metrics fully capture the solution's performance.
- 1: the metrics partially capture the solution's performance.
- 0: the metrics do not capture the solution's performance.

Category score = definitions + quality (max 3 + 2 = 5).

### 5. Reference solution (1 point each, max 5)

- [ ] A reference solution is publicly available.
- [ ] The provided reference solution is well documented.
- [ ] All hardware and/or software requirements to run the reference solution are listed.
- [ ] All metrics defined as part of the benchmark are evaluated as part of the reference
      solution.
- [ ] The baseline solution/model is openly available for study (and if a neural network,
      the architecture, hyperparameters, and training code are provided).

### 6. Documentation (1 point each, max 5)

- [ ] The task is explained and well documented.
- [ ] The task and benchmark background (scientific and otherwise) is clearly explained.
- [ ] The motivation for the benchmark is clearly explained.
- [ ] The evaluation criteria are clearly explained.
- [ ] An academic paper about the benchmark exists.

### Scoring notes

- Check every criterion against evidence you can point to: a file, a repository section, a
  sentence in the documentation. If you cannot point to it, it is not met.
- Several criteria are judgment calls ("well documented", "clear task"). Make the call and state
  why. When the evidence is ambiguous, ask the user instead of scoring generously: an inflated
  self-score misleads anyone who later applies for endorsement.
- `scripts/score_benchmark.py` implements this arithmetic against a filled-in
  `assets/rubric_template.yaml`. Use it instead of averaging by hand; it computes the same way
  every time and explains its output.

## Part 3: Motif taxonomy

Tag every benchmark with its **scientific motif(s)** (domain; a benchmark can have several) and
exactly **one AI/ML motif** (task type). The rubric does not score this, but the ontology's website
and search use it to make a benchmark findable (the Findable FAIR criterion above).

**Scientific motifs** (domains in the current ontology; more are added over time):
High-Energy Physics, Chemistry, Materials Science, Biology & Medicine, Climate & Earth Science,
Computational Science & AI, Mathematics.

**AI/ML motifs** (task types; pick the single best fit):
Classification, Regression, Sequence Prediction/Forecasting, Anomaly Detection,
Reinforcement Learning/Control, Generative, Multimodal Reasoning, Surrogate Modeling,
Reasoning & Generalization.

**Computing motifs** (optional; the typical resource bottleneck; a benchmark can have more than
one): Latency Bound, Memory Bound, Throughput Bound, Utilization Bound.

### Metrics comparable benchmarks use

The ontology has no default metric suite. Metric choice follows from the AI/ML motif and the
scientific question. Do not let the regression metrics in `scripts/metrics.py` (R², SMAPE, RMSE)
become the assumed answer for a benchmark that is not regression. When helping a user pick metrics
for element C, start from what benchmarks with the same AI/ML motif measure. The ontology paper
(Section IV-B2) gives examples per motif:

| AI/ML motif | Example benchmark | What it measures |
|---|---|---|
| Classification | Jet Classification, Smart Pixels for LHC, SatImgNet | Class accuracy (often per-class/multi-task) |
| Regression | FEABench | Solve-time and error norm |
| Regression | CFDBench | L2 error, MAE |
| Regression | OCP, Materials Project | MAE/error on physical quantities (adsorption energy, band-gap, formation energy) |
| Sequence Prediction/Forecasting | ClimateLearn | Forecast error on ERA5-based medium-range weather prediction |
| Sequence Prediction/Forecasting | GB-Biology | Standardized eval protocols for node/link/graph property prediction |
| Anomaly Detection | HDR ML Anomaly Challenge (Sea-Level Rise, Gravitational Waves) | ROC-AUC, precision/recall |
| Reinforcement Learning/Control | Beam Control | Stability loss, control-latency |
| Reinforcement Learning/Control | Quench Detection | ROC-AUC, detection latency |
| Generative | MOLGEN | log-P, QED, docking scores (chemistry-specific validity/quality measures) |
| Generative | SuperCon3D | MAE + validity |
| Multimodal Reasoning | SPIQA | Accuracy, F1 |
| Multimodal Reasoning | SeafloorAI | Segmentation pixel accuracy + QA accuracy (two metrics, one per modality) |
| Surrogate Modeling | CFDBench, The Well | L2 error, MAE |
| Reasoning & Generalization | MedQA, FrontierMath, AIME | Task accuracy |

The table shows what a fitting answer looks like for each motif; it is not a menu to copy. A new
anomaly-detection benchmark, for example, should ask whether ROC-AUC or precision/recall fits its
own class balance and cost structure, not adopt them because two earlier anomaly benchmarks did.
Several motifs (Generative, Reinforcement Learning/Control, Multimodal Reasoning) have no
implementation in `scripts/metrics.py` on purpose. They need task-specific code. A generic
substitute would give a benchmark whose metrics do not capture what it claims, which loses points
under Category 4's metric quality sub-score.

## Part 4: Users the ontology serves

Keep these three users in mind while interviewing a user about their benchmark. A benchmark
package should serve all three, not only the person building it.

1. **Specific-benchmark seekers** want one benchmark matching a domain and task type. Good
   metadata and motif tags serve them.
2. **Category seekers** want a slice of benchmarks ("all HEP benchmarks", or "all classification
   tasks in HEP"). Consistent, accurate motif tags serve them.
3. **Compute-pattern seekers** are hardware vendors and systems researchers looking for workloads
   with similar computational behavior regardless of domain. Documented system constraints and
   computing motifs (Part 3) serve them, plus profiling data where relevant.
