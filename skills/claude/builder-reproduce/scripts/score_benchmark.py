#!/usr/bin/env python3
"""Score a filled-in rubric YAML against the MLCommons Science Benchmarks Ontology
(arXiv:2511.05614, Section III) and print/write a markdown report.

Usage:
    python score_benchmark.py path/to/rubric.yaml [--out report.md] [--json]

The rubric YAML must follow the schema in assets/rubric_template.yaml. Every checklist
item's `met` field (or, for performance_metrics, the two `*_level` fields) must be filled
in with true/false or a numeric level -- this script refuses to score a category that has
unanswered items, rather than silently treating a `null` as false, because that would
quietly under- or over-score the benchmark depending on which way you'd have guessed.
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(
        "Missing dependency: pyyaml. Install it with `pip install pyyaml` and re-run."
    )

ENDORSEMENT_THRESHOLD = 4.5
CHECKLIST_CATEGORIES = [
    ("software_environment", "Software Environment"),
    ("problem_specification", "Problem Specification and Constraints"),
    ("reference_solution", "Reference Solution"),
    ("documentation", "Documentation"),
]


class RubricError(Exception):
    pass


def _score_checklist(items, category_label):
    if not items:
        raise RubricError(f"{category_label}: no checklist items found.")
    unanswered = [i["id"] for i in items if i.get("met") is None]
    if unanswered:
        raise RubricError(
            f"{category_label}: unanswered item(s) {unanswered} -- fill in `met: true/false` "
            f"for each before scoring."
        )
    met = [i for i in items if i["met"] is True]
    unmet = [i for i in items if i["met"] is False]
    score = float(len(met))
    return score, unmet


def _score_dataset(dataset):
    fair_items = dataset.get("fair", [])
    if len(fair_items) != 4:
        raise RubricError(
            f"Dataset: expected 4 FAIR criteria, found {len(fair_items)}."
        )
    unanswered = [i["id"] for i in fair_items if i.get("met") is None]
    splits = dataset.get("splits_defined", {})
    if splits.get("met") is None:
        unanswered.append("splits_defined")
    if unanswered:
        raise RubricError(
            f"Dataset: unanswered item(s) {unanswered} -- fill in `met: true/false` for each."
        )
    fair_met = [i for i in fair_items if i["met"] is True]
    fair_unmet = [i for i in fair_items if i["met"] is False]
    score = float(len(fair_met))
    unmet = list(fair_unmet)
    if splits.get("met") is True:
        score += 1.0
    else:
        unmet.append(
            {"id": "splits_defined", "description": splits.get("description", "")}
        )
    return score, unmet


def _score_performance_metrics(pm):
    definition_level = pm.get("definition_level")
    quality_level = pm.get("quality_level")
    if definition_level is None or quality_level is None:
        raise RubricError(
            "Performance Metrics: `definition_level` (0-3) and `quality_level` (0-2) "
            "must both be set."
        )
    if definition_level not in (0, 1, 2, 3):
        raise RubricError("Performance Metrics: definition_level must be 0, 1, 2, or 3.")
    if quality_level not in (0, 1, 2):
        raise RubricError("Performance Metrics: quality_level must be 0, 1, or 2.")
    score = float(definition_level + quality_level)
    notes = []
    if definition_level < 3:
        notes.append(
            f"definition_level={definition_level}/3 -- {pm.get('definition_evidence') or 'no evidence recorded; metrics are not fully defined yet.'}"
        )
    if quality_level < 2:
        notes.append(
            f"quality_level={quality_level}/2 -- {pm.get('quality_evidence') or 'no evidence recorded; metrics do not fully capture performance yet.'}"
        )
    return score, notes


def score_rubric(rubric):
    results = {}
    gaps = {}

    for key, label in CHECKLIST_CATEGORIES:
        items = rubric.get(key)
        score, unmet = _score_checklist(items, label)
        results[label] = score
        gaps[label] = unmet

    dataset_score, dataset_unmet = _score_dataset(rubric.get("dataset", {}))
    results["Dataset"] = dataset_score
    gaps["Dataset"] = dataset_unmet

    pm_score, pm_notes = _score_performance_metrics(rubric.get("performance_metrics", {}))
    results["Performance Metrics"] = pm_score
    gaps["Performance Metrics"] = pm_notes

    overall = sum(results.values()) / len(results)
    endorsed = overall >= ENDORSEMENT_THRESHOLD
    return results, gaps, overall, endorsed


def render_report(rubric, results, gaps, overall, endorsed):
    name = rubric.get("benchmark_name") or "(unnamed benchmark)"
    lines = [f"# Rubric score: {name}", ""]
    if rubric.get("scored_date"):
        lines.append(f"Scored: {rubric['scored_date']}")
    lines.append("")
    lines.append("| Category | Score |")
    lines.append("|---|---|")
    for label, score in results.items():
        lines.append(f"| {label} | {score:.1f} / 5 |")
    lines.append(f"| **Overall (mean of categories)** | **{overall:.2f} / 5** |")
    lines.append("")

    if endorsed:
        lines.append(
            f"**Meets the MLCommons Science Benchmark Endorsement threshold** "
            f"(overall >= {ENDORSEMENT_THRESHOLD})."
        )
    else:
        gap_to_go = ENDORSEMENT_THRESHOLD - overall
        lines.append(
            f"Below the MLCommons Science Benchmark Endorsement threshold "
            f"(overall >= {ENDORSEMENT_THRESHOLD}) by {gap_to_go:.2f} points."
        )
    lines.append("")

    lines.append("## Gaps and next steps")
    lines.append("")
    any_gaps = False
    for label, unmet in gaps.items():
        if not unmet:
            continue
        any_gaps = True
        lines.append(f"### {label}")
        for item in unmet:
            if isinstance(item, dict) and "description" in item:
                lines.append(f"- [ ] {item['description']}")
            else:
                lines.append(f"- {item}")
        lines.append("")
    if not any_gaps:
        lines.append("No unmet checklist items -- every category is maxed out.")
        lines.append("")

    motifs = rubric.get("motifs", {})
    if motifs:
        lines.append("## Motif tags")
        lines.append(
            f"- Scientific motif(s): {', '.join(motifs.get('scientific_motifs') or []) or '(none set)'}"
        )
        lines.append(f"- AI/ML motif: {motifs.get('ai_ml_motif') or '(none set)'}")
        computing = motifs.get("computing_motifs") or []
        if computing:
            lines.append(f"- Computing motif(s): {', '.join(computing)}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rubric_path", type=Path, help="Path to a filled-in rubric YAML")
    parser.add_argument("--out", type=Path, help="Write the markdown report to this path")
    parser.add_argument(
        "--json", action="store_true", help="Also print raw scores as JSON to stdout"
    )
    args = parser.parse_args()

    if not args.rubric_path.exists():
        sys.exit(f"No such file: {args.rubric_path}")

    with open(args.rubric_path, "r", encoding="utf-8") as f:
        rubric = yaml.safe_load(f)

    try:
        results, gaps, overall, endorsed = score_rubric(rubric)
    except RubricError as e:
        sys.exit(f"Cannot score yet -- {e}")

    report = render_report(rubric, results, gaps, overall, endorsed)
    print(report)

    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"\n(written to {args.out})", file=sys.stderr)

    if args.json:
        import json

        print(
            json.dumps(
                {"categories": results, "overall": overall, "endorsed": endorsed}, indent=2
            )
        )


if __name__ == "__main__":
    main()
