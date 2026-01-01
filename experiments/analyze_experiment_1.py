#!/usr/bin/env python3
"""Analyze Experiment 1 results and create visualizations."""

import json
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import pandas as pd

    HAS_PLOTTING = True
except ImportError:
    print("Warning: matplotlib/pandas not installed. Run: pip install matplotlib pandas")
    HAS_PLOTTING = False


def analyze(results_file: str = "experiments/results/exp1/experiment_1_results.json"):
    """Analyze Experiment 1 results."""
    print("Analyzing Experiment 1: Adaptive vs Fixed Strategy")
    print("=" * 70)

    # Load results
    results = json.load(open(results_file))

    # Create dataframe
    data = []
    for r in results:
        data.append(
            {
                "PDF": r["pdf"],
                "Fixed_Quality": r["fixed"]["quality"],
                "Adaptive_Quality": r["adaptive"]["quality"],
                "Quality_Improvement": r["improvement"]["quality_delta"],
                "Fixed_Time": r["fixed"]["time_seconds"],
                "Adaptive_Time": r["adaptive"]["time_seconds"],
                "Time_Delta": r["improvement"]["time_delta"],
            }
        )

    if HAS_PLOTTING:
        df = pd.DataFrame(data)

        # Summary statistics
        print("\nSummary Statistics:")
        print(df[["Fixed_Quality", "Adaptive_Quality", "Quality_Improvement"]].describe())

        # T-test for quality difference
        from scipy import stats

        try:
            t_stat, p_value = stats.ttest_rel(df["Adaptive_Quality"], df["Fixed_Quality"])
            print("\nPaired t-test:")
            print(f"  t-statistic: {t_stat:.4f}")
            print(f"  p-value: {p_value:.4f}")
            print(f"  Significant: {'Yes' if p_value < 0.05 else 'No'}")
        except ImportError:
            print("\nNote: scipy not installed. Run: pip install scipy")

        # Create visualizations
        output_dir = Path(results_file).parent / "figures"
        output_dir.mkdir(exist_ok=True)

        # Figure 1: Quality comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        x = range(len(df))
        ax.plot(x, df["Fixed_Quality"], marker="o", label="Fixed Strategy", linewidth=2)
        ax.plot(x, df["Adaptive_Quality"], marker="s", label="Adaptive Strategy", linewidth=2)
        ax.set_xlabel("Document", fontsize=12)
        ax.set_ylabel("Translation Quality", fontsize=12)
        ax.set_title(
            "Experiment 1: Quality Comparison (Adaptive vs Fixed)", fontsize=14, fontweight="bold"
        )
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_dir / "exp1_quality_comparison.png", dpi=300)
        print(f"\n✓ Saved: {output_dir / 'exp1_quality_comparison.png'}")

        # Figure 2: Quality improvement distribution
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.bar(range(len(df)), df["Quality_Improvement"], color="green", alpha=0.7)
        ax.axhline(y=0, color="r", linestyle="--", linewidth=1)
        ax.set_xlabel("Document", fontsize=12)
        ax.set_ylabel("Quality Improvement (Adaptive - Fixed)", fontsize=12)
        ax.set_title("Quality Improvement per Document", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3, axis="y")
        plt.tight_layout()
        plt.savefig(output_dir / "exp1_quality_improvement.png", dpi=300)
        print(f"✓ Saved: {output_dir / 'exp1_quality_improvement.png'}")

        # Figure 3: Time comparison
        fig, ax = plt.subplots(figsize=(10, 6))
        width = 0.35
        ax.bar([i - width / 2 for i in x], df["Fixed_Time"], width, label="Fixed", alpha=0.8)
        ax.bar([i + width / 2 for i in x], df["Adaptive_Time"], width, label="Adaptive", alpha=0.8)
        ax.set_xlabel("Document", fontsize=12)
        ax.set_ylabel("Translation Time (seconds)", fontsize=12)
        ax.set_title("Processing Time Comparison", fontsize=14, fontweight="bold")
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")
        plt.tight_layout()
        plt.savefig(output_dir / "exp1_time_comparison.png", dpi=300)
        print(f"✓ Saved: {output_dir / 'exp1_time_comparison.png'}")

        print(f"\n✓ All figures saved to: {output_dir}/")
    else:
        # Text-only summary
        print("\nResults:")
        for r in data:
            print(f"\n{r['PDF']}:")
            print(f"  Fixed quality:    {r['Fixed_Quality']:.2%}")
            print(f"  Adaptive quality: {r['Adaptive_Quality']:.2%}")
            print(f"  Improvement:      {r['Quality_Improvement']:+.2%}")

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    avg_improvement = sum(r["Quality_Improvement"] for r in data) / len(data)
    print(f"Average quality improvement: {avg_improvement:+.2%}")

    if avg_improvement > 0.05:
        print("✓ Adaptive strategy shows SIGNIFICANT improvement")
    elif avg_improvement > 0:
        print("✓ Adaptive strategy shows positive improvement")
    else:
        print("⚠ No significant improvement (consider parameter tuning)")


if __name__ == "__main__":
    import sys

    results_file = (
        sys.argv[1] if len(sys.argv) > 1 else "experiments/results/exp1/experiment_1_results.json"
    )
    analyze(results_file)
