"""A small toolkit of generic building blocks for the "Performance Metric(s)" element of
the MLCommons Science Benchmarks Ontology (arXiv:2511.05614) -- NOT a default metric suite.

There is no universal "the metrics" for this ontology. What a benchmark should measure is a
function of its AI/ML motif and scientific question (see references/ontology.md's "What
metrics do comparable existing benchmarks actually use?" table): a generative-chemistry
benchmark needs validity/docking scores, an RL/control benchmark needs stability loss and
control latency, a multimodal-reasoning benchmark needs task-specific accuracy per modality.
None of those are implemented here, on purpose -- they're genuinely bespoke, and a benchmark
whose metrics don't actually fit its task loses rubric Category 4 (Performance Metrics)
credit regardless of how polished the code computing them is.

What IS implemented here are primitives for the two motifs common enough, and generic
enough, to be worth not reimplementing every time: regression (r_squared, smape, rmse, mae,
relative_l2_error, relative_percent_error + plot_rpe_boxplot) and classification/anomaly
detection (classification_report, roc_auc). The regression functions document their edge-case
handling because it is easy to get subtly wrong, not because R^2/SMAPE/RMSE are the
"correct" choice for every regression benchmark -- swap in mae or relative_l2_error instead
where those fit better (see FEABench/CFDBench in the ontology.md table), or write something
else entirely if the task calls for it.

This module only requires numpy for the metric functions; matplotlib is only imported
inside plot_rpe_boxplot, so importing this module doesn't require a display backend.

Usage:
    import numpy as np
    from metrics import r_squared, smape, rmse, relative_percent_error, plot_rpe_boxplot

    y_true = np.array([...])
    y_pred = np.array([...])
    print(r_squared(y_true, y_pred), smape(y_true, y_pred), rmse(y_true, y_pred))
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Regression metrics
# ---------------------------------------------------------------------------


def r_squared(y_true, y_pred):
    """Coefficient of determination (R^2). 1.0 is perfect; can go negative for a fit
    worse than predicting the mean. Returns nan if y_true is constant (variance is zero) --
    check for that case explicitly before relying on the result."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def smape(y_true, y_pred, epsilon=None):
    """Symmetric mean absolute percentage error, as a percentage (0-200 range).

    `epsilon` avoids division by zero when both y_true and y_pred are 0. For integer counts,
    1 is a reasonable default; for a continuous target, pick the smallest meaningful unit
    rather than an arbitrary tiny constant.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    eps = 1.0 if epsilon is None else epsilon
    denom = np.abs(y_true) + np.abs(y_pred) + eps
    return float(200.0 * np.mean(np.abs(y_true - y_pred) / denom))


def rmse(y_true, y_pred):
    """Root mean square error. Same units as the target; sensitive to outliers."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mae(y_true, y_pred):
    """Mean absolute error. Same units as the target; unlike RMSE, doesn't disproportionately
    punish outliers -- often the better fit when large errors on rare samples shouldn't
    dominate the score (e.g. Delta^2-DFT, SuperCon3D; see ontology.md's motif table)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def relative_l2_error(y_true, y_pred, axis=None):
    """Relative L2 (norm-ratio) error: ||y_pred - y_true||_2 / ||y_true||_2. Common for
    field/surrogate-modeling benchmarks (e.g. CFDBench, PDE surrogate models) where the
    quantity of interest is a whole spatial/temporal field rather than independent scalar
    samples, so a plain per-element average like RMSE/MAE undersells how correlated the
    errors are across the field. Pass `axis` to compute per-sample errors over a batch of
    fields rather than one number over the whole array (e.g. axis=-1 if each row is one
    flattened field)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    num = np.linalg.norm(y_pred - y_true, axis=axis)
    denom = np.linalg.norm(y_true, axis=axis)
    return num / denom if axis is not None else float(num / denom)


def relative_percent_error(y_true, y_pred, epsilon=1.0):
    """Per-sample relative percent error: (y_true - y_pred) / (y_true + epsilon) * 100.
    Signed -- positive means under-prediction, negative means over-prediction. This is a
    per-sample array, meant for distribution visualization (see plot_rpe_boxplot), not a
    single scalar summary."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return (y_true - y_pred) / (y_true + epsilon) * 100.0


def regression_report(y_true, y_pred, epsilon=None):
    """Convenience: compute the R^2/SMAPE/RMSE trio at once, returned as a dict. This is
    one possible regression report, not "the" regression report -- if mae or
    relative_l2_error fit your benchmark's task better (see the ontology's motif table),
    call them directly and build your own dict rather than assuming this one is complete
    for your case."""
    return {
        "r_squared": r_squared(y_true, y_pred),
        "smape": smape(y_true, y_pred, epsilon=epsilon),
        "rmse": rmse(y_true, y_pred),
    }


def plot_rpe_boxplot(errors_by_target, out_path, title="Relative Percent Error", symlog=True):
    """Box plot of per-target RPE distributions: one box per target variable, median and
    mean both marked, y-axis on a
    symmetric log scale by default (RPE distributions are typically heavy-tailed).

    Args:
        errors_by_target: dict of {target_name: array_of_rpe_values}, e.g.
            {"BRAM": rpe_bram, "DSP": rpe_dsp, ...} where each array comes from
            relative_percent_error().
        out_path: file path to save the figure to (png/pdf, inferred from extension).
        title: plot title.
        symlog: use a symmetric log y-axis (handles the long tails typical of RPE data);
            set False for a linear axis if your errors are small and tightly distributed.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(errors_by_target.keys())
    data = [np.asarray(errors_by_target[k]) for k in labels]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.5), 5))
    bp = ax.boxplot(data, labels=labels, showmeans=True, meanline=True, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#a6c8ff")
    for median in bp["medians"]:
        median.set_color("orange")
        median.set_linestyle("--")
    for mean in bp["means"]:
        mean.set_color("green")
        mean.set_linestyle("--")

    if symlog:
        ax.set_yscale("symlog")
    ax.set_ylabel("Relative Percent Error [%]")
    ax.set_title(title)
    ax.axhline(0, color="gray", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Classification / anomaly-detection metrics (numpy only, no sklearn dependency)
# ---------------------------------------------------------------------------


def confusion_counts(y_true, y_pred, positive_label=1):
    """Binary confusion matrix counts. For multi-class, one-vs-rest: pass the class of
    interest as positive_label and treat everything else as negative."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    tp = int(np.sum((y_true == positive_label) & (y_pred == positive_label)))
    tn = int(np.sum((y_true != positive_label) & (y_pred != positive_label)))
    fp = int(np.sum((y_true != positive_label) & (y_pred == positive_label)))
    fn = int(np.sum((y_true == positive_label) & (y_pred != positive_label)))
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def classification_report(y_true, y_pred, positive_label=1):
    """Accuracy, precision, recall, and F1 for a binary (or one-vs-rest) classification
    task. Returns 0.0 for precision/recall/F1 when the denominator is zero rather than
    raising, since "no positive predictions/labels" is a valid, if degenerate, outcome
    worth reporting rather than crashing on."""
    c = confusion_counts(y_true, y_pred, positive_label=positive_label)
    total = c["tp"] + c["tn"] + c["fp"] + c["fn"]
    accuracy = (c["tp"] + c["tn"]) / total if total else float("nan")
    precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
    recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        **c,
    }


def roc_auc(y_true, y_score):
    """ROC-AUC via the rank-sum (Mann-Whitney U) method -- no sklearn required. y_true
    must be binary (0/1); y_score is the predicted probability/score for the positive
    class. Returns nan if y_true is all one class (AUC is undefined)."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    n_pos = np.sum(y_true == 1)
    n_neg = np.sum(y_true == 0)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(y_score)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(y_score) + 1)
    # handle ties by averaging ranks
    _, inv, counts = np.unique(y_score, return_inverse=True, return_counts=True)
    sum_ranks = np.zeros(len(counts))
    np.add.at(sum_ranks, inv, ranks)
    avg_ranks = sum_ranks / counts
    ranks = avg_ranks[inv]
    sum_ranks_pos = np.sum(ranks[y_true == 1])
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(auc)


if __name__ == "__main__":
    # Smoke test / usage example.
    rng = np.random.default_rng(0)
    y_true = rng.integers(10, 1000, size=200).astype(float)
    y_pred = y_true * rng.normal(1.0, 0.1, size=200)

    print("Regression report:", regression_report(y_true, y_pred))

    rpe = relative_percent_error(y_true, y_pred)
    print("RPE mean/median:", np.mean(rpe), np.median(rpe))

    y_true_c = rng.integers(0, 2, size=200)
    y_pred_c = rng.integers(0, 2, size=200)
    print("Classification report:", classification_report(y_true_c, y_pred_c))
    print("ROC-AUC (random scores):", roc_auc(y_true_c, rng.random(200)))
