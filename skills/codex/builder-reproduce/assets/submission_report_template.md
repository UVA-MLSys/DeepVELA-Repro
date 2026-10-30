# Submission Report: {{SOLUTION_NAME}} on {{BENCHMARK_NAME}}

Use the three-tier (required / strongly recommended / suggested) structure below as a starting
point. Adjust the tiers to match what this benchmark's own benchmark card actually requires; this
file is not a fixed standard.

## Required

- [ ] **Predicted values** for every metric defined in the benchmark card, on every split
      the benchmark specifies (typically the test set, and any held-out generalization set).
- [ ] **Visual comparison** between predicted and actual values. For regression targets, a
      box plot of relative/absolute error per target (see `scripts/metrics.py`'s
      `plot_rpe_boxplot` when appropriate); for classification, a confusion matrix or ROC/PR curve as
      appropriate to the task.
- [ ] **Metric table**: every defined metric, computed exactly as specified in the
      benchmark card, reported per target/class if the task has more than one.

## Strongly recommended

- [ ] **Architecture/method description**: enough detail to reimplement without reading the
      submitted code — design choices, key hyperparameters, and why they were chosen.
- [ ] **Source code and trained weights**, shared openly, to support reproducibility and
      direct comparison by future submitters.
- [ ] **Inference hardware specification** and measured inference time — a solution's
      accuracy numbers mean something different on a workstation GPU vs. an embedded part.

## Suggested / as applicable

- [ ] **Additional constraints used**: any extra training data, target configurations, or
      precision/optimization strategies applied beyond what the benchmark's dataset provides
      — document these so results aren't silently non-comparable to other submissions.

---

## Metric results

| Metric | Target 1 | Target 2 | … |
|---|---|---|---|
| | | | |

## Visual comparisons

_(embed or link plots here)_

## Reproduction

```bash
# exact commands to regenerate this report's numbers from a clean environment
```
