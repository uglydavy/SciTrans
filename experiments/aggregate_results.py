#!/usr/bin/env python3
"""Aggregate results from all experiments for thesis analysis."""

import json
from pathlib import Path


def aggregate_all_experiments(results_dir: str = "experiments/results"):
    """Aggregate results from all 5 experiments."""
    print("Aggregating experimental results...")
    print("=" * 70)

    results_path = Path(results_dir)
    aggregated = {
        "metadata": {
            "author": "Franck Davy",
            "institution": "Wenzhou University",
            "year": 2025,
            "thesis": "Adaptive Document Translation Enhanced by Technology based on LLMs",
            "system": "SciTrans-LLMs v1.0.0",
        },
        "experiments": {},
    }

    # Experiment 1: Adaptive vs Fixed
    exp1_file = results_path / "exp1" / "experiment_1_results.json"
    if exp1_file.exists():
        exp1_data = json.load(open(exp1_file))

        fixed_quality = [r["fixed"]["quality"] for r in exp1_data]
        adaptive_quality = [r["adaptive"]["quality"] for r in exp1_data]

        aggregated["experiments"]["exp1_adaptive_vs_fixed"] = {
            "description": "Adaptive parameter selection vs fixed strategy",
            "num_documents": len(exp1_data),
            "avg_fixed_quality": sum(fixed_quality) / len(fixed_quality),
            "avg_adaptive_quality": sum(adaptive_quality) / len(adaptive_quality),
            "improvement": (sum(adaptive_quality) - sum(fixed_quality)) / len(fixed_quality),
            "details": exp1_data,
        }
        print(f"✓ Experiment 1: {len(exp1_data)} documents")

    # Experiment 2: Scoring validation
    # (Requires human ratings - placeholder for now)
    aggregated["experiments"]["exp2_scoring_validation"] = {
        "description": "Multi-dimensional scoring validation",
        "status": "pending_human_ratings",
        "note": "Run human_evaluation_template.py to collect data",
    }

    # Experiment 3: Repair efficiency
    exp3_dir = results_path / "exp3"
    if exp3_dir.exists():
        initial_report = exp3_dir / "initial" / "report.json"
        if initial_report.exists():
            report = json.load(open(initial_report))
            aggregated["experiments"]["exp3_repair_efficiency"] = {
                "description": "Selective repair vs full re-translation",
                "failed_blocks": report["scoring"]["blocks_need_retry"],
                "total_blocks": report["scoring"]["blocks_total"],
                "failure_rate": report["scoring"]["blocks_need_retry"]
                / report["scoring"]["blocks_total"],
            }
            print(f"✓ Experiment 3: {report['scoring']['blocks_need_retry']} blocks to repair")

    # Experiment 4: Cascade-free vs Premium
    exp4_dir = results_path / "exp4"
    if exp4_dir.exists():
        cascade_reports = list((exp4_dir / "cascade").glob("*/report.json"))
        if cascade_reports:
            cascade_quality = []
            for report_file in cascade_reports:
                report = json.load(open(report_file))
                cascade_quality.append(report["scoring"]["document_quality"])

            aggregated["experiments"]["exp4_cascade_quality"] = {
                "description": "Cascade-free backend quality vs premium",
                "num_documents": len(cascade_quality),
                "avg_cascade_quality": sum(cascade_quality) / len(cascade_quality),
                "note": "Compare with anthropic backend if API key available",
            }
            print(f"✓ Experiment 4: {len(cascade_quality)} documents tested")

    # Experiment 5: End-to-end
    exp5_dir = results_path / "exp5"
    if exp5_dir.exists():
        reports = list(exp5_dir.glob("*/report.json"))
        if reports:
            qualities = []
            complexities = []
            for report_file in reports:
                report = json.load(open(report_file))
                qualities.append(report["scoring"]["document_quality"])
                complexities.append(report["scoring"]["avg_source_complexity"])

            aggregated["experiments"]["exp5_endtoend"] = {
                "description": "End-to-end system evaluation",
                "num_documents": len(reports),
                "avg_quality": sum(qualities) / len(qualities),
                "avg_complexity": sum(complexities) / len(complexities),
                "min_quality": min(qualities),
                "max_quality": max(qualities),
            }
            print(f"✓ Experiment 5: {len(reports)} documents evaluated")

    # Save aggregated results
    output_file = results_path / "aggregated_results.json"
    output_file.write_text(json.dumps(aggregated, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print("AGGREGATION COMPLETE")
    print("=" * 70)
    print(f"\nResults saved to: {output_file}")
    print("\nSummary:")

    if "exp1_adaptive_vs_fixed" in aggregated["experiments"]:
        exp1 = aggregated["experiments"]["exp1_adaptive_vs_fixed"]
        print(f"  Exp 1: {exp1['improvement']:+.2%} quality improvement (adaptive vs fixed)")

    if "exp5_endtoend" in aggregated["experiments"]:
        exp5 = aggregated["experiments"]["exp5_endtoend"]
        print(f"  Exp 5: {exp5['avg_quality']:.2%} average translation quality")

    print("\nNext steps for thesis:")
    print("  1. Collect human ratings (Exp 2)")
    print("  2. Run statistical analysis: python experiments/statistical_analysis.py")
    print("  3. Generate thesis figures: python experiments/create_thesis_figures.py")

    return aggregated


if __name__ == "__main__":
    aggregate_all_experiments()
