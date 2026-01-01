#!/usr/bin/env python3
"""Visualize benchmark results for SciTrans thesis/reports.

Reads experiments/results/benchmarks/summary.json and creates publication-quality figures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent to path if running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import matplotlib
    import matplotlib.pyplot as plt

    matplotlib.use("Agg")  # Non-interactive backend
except ImportError:
    print("Error: matplotlib not installed. Install with:")
    print("  pip install matplotlib")
    sys.exit(1)

import numpy as np


def load_benchmark_data(summary_path: Path) -> dict:
    """Load summary.json benchmark data and aggregate by backend."""
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary not found: {summary_path}")

    with open(summary_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    # If data is already a dict (old format), return as is
    if isinstance(raw_data, dict):
        return raw_data

    # Aggregate list format into backend-grouped dict
    aggregated = {}
    for entry in raw_data:
        backend = entry["backend"]
        if backend not in aggregated:
            aggregated[backend] = {
                "per_document": {},
                "total_blocks": 0,
                "total_ok": 0,
                "total_failed": 0,
                "total_time_sec": 0.0,
                "runs": 0,
            }

        pdf_name = entry["pdf"]
        aggregated[backend]["per_document"][pdf_name] = {
            "quality": entry.get("document_quality", 0) * 100,
            "confidence": entry.get("confidence", 0) or 0,
            "acceptance_rate": entry.get("acceptance_rate", 0) * 100,
            "duration_sec": entry.get("duration_sec", 0),
            "num_blocks": entry.get("num_blocks", 0),
            "cached_blocks": 0,  # Not in current format
        }

        aggregated[backend]["total_blocks"] += entry.get("num_blocks", 0)
        aggregated[backend]["total_ok"] += entry.get("num_ok", 0)
        aggregated[backend]["total_failed"] += entry.get("num_failed", 0)
        aggregated[backend]["total_time_sec"] += entry.get("duration_sec", 0)
        aggregated[backend]["runs"] += 1

    # Calculate averages
    for _backend, data in aggregated.items():
        docs = list(data["per_document"].values())
        data["avg_quality"] = sum(d["quality"] for d in docs) / len(docs) if docs else 0
        data["avg_confidence"] = sum(d["confidence"] for d in docs) / len(docs) if docs else 0
        data["avg_acceptance_rate"] = (
            sum(d["acceptance_rate"] for d in docs) / len(docs) if docs else 0
        )
        data["avg_health_ratio"] = (
            (data["total_ok"] / data["total_blocks"]) if data["total_blocks"] > 0 else 0
        )

    return aggregated


def plot_quality_by_document(data: dict, output_dir: Path):
    """Plot document quality scores by document type."""
    backends = list(data.keys())

    # Extract per-document data
    all_docs = set()
    for backend_data in data.values():
        for doc_name in backend_data.get("per_document", {}).keys():
            all_docs.add(doc_name)

    all_docs = sorted(all_docs)

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(all_docs))
    width = 0.8 / len(backends)

    for idx, backend in enumerate(backends):
        qualities = []
        for doc in all_docs:
            doc_data = data[backend].get("per_document", {}).get(doc, {})
            quality = doc_data.get("quality", 0)
            qualities.append(quality)

        offset = (idx - len(backends) / 2) * width + width / 2
        ax.bar(x + offset, qualities, width, label=backend, alpha=0.8)

    ax.set_xlabel("Document", fontsize=12)
    ax.set_ylabel("Quality Score (%)", fontsize=12)
    ax.set_title("Translation Quality by Document Type", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [d.replace(".pdf", "").replace("_", " ") for d in all_docs],
        rotation=45,
        ha="right",
        fontsize=9,
    )
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    output_path = output_dir / "quality_by_document.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def plot_acceptance_rates(data: dict, output_dir: Path):
    """Plot acceptance rates by backend."""
    backends = list(data.keys())
    acceptance_rates = [data[b]["avg_acceptance_rate"] for b in backends]

    fig, ax = plt.subplots(figsize=(8, 6))

    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(backends)))
    bars = ax.barh(backends, acceptance_rates, color=colors, alpha=0.8)

    # Add value labels
    for bar, rate in zip(bars, acceptance_rates):
        width = bar.get_width()
        ax.text(
            width + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax.set_xlabel("Acceptance Rate (%)", fontsize=12)
    ax.set_ylabel("Backend", fontsize=12)
    ax.set_title("Block Acceptance Rate by Backend", fontsize=14, fontweight="bold")
    ax.set_xlim(0, 105)
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    output_path = output_dir / "acceptance_rates.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def plot_health_scores(data: dict, output_dir: Path):
    """Plot health score distributions."""
    backends = list(data.keys())
    health_ratios = [data[b]["avg_health_ratio"] * 100 for b in backends]
    failed_rates = [
        (data[b]["total_failed"] / max(1, data[b]["total_blocks"])) * 100 for b in backends
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Health ratio
    colors1 = plt.cm.RdYlGn(np.array(health_ratios) / 100)
    bars1 = ax1.barh(backends, health_ratios, color=colors1, alpha=0.8)
    for bar, ratio in zip(bars1, health_ratios):
        width = bar.get_width()
        ax1.text(
            width + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{ratio:.1f}%",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax1.set_xlabel("Health Ratio (%)", fontsize=12)
    ax1.set_ylabel("Backend", fontsize=12)
    ax1.set_title("Average Health Score", fontsize=13, fontweight="bold")
    ax1.set_xlim(0, 105)
    ax1.grid(axis="x", alpha=0.3)

    # Failure rate
    colors2 = plt.cm.RdYlGn_r(np.array(failed_rates) / max(failed_rates + [1]))
    bars2 = ax2.barh(backends, failed_rates, color=colors2, alpha=0.8)
    for bar, rate in zip(bars2, failed_rates):
        width = bar.get_width()
        ax2.text(
            width + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax2.set_xlabel("Failure Rate (%)", fontsize=12)
    ax2.set_ylabel("Backend", fontsize=12)
    ax2.set_title("Block Failure Rate", fontsize=13, fontweight="bold")
    ax2.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    output_path = output_dir / "health_scores.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def plot_performance_metrics(data: dict, output_dir: Path):
    """Plot performance metrics (time, cache hit rate)."""
    backends = list(data.keys())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Time per document
    times = [
        data[b]["total_time_sec"] / max(1, len(data[b].get("per_document", {}))) for b in backends
    ]
    colors1 = plt.cm.plasma(np.linspace(0.2, 0.8, len(backends)))
    bars1 = ax1.barh(backends, times, color=colors1, alpha=0.8)
    for bar, t in zip(bars1, times):
        width = bar.get_width()
        ax1.text(
            width + 0.1,
            bar.get_y() + bar.get_height() / 2,
            f"{t:.2f}s",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax1.set_xlabel("Avg Time per Document (s)", fontsize=12)
    ax1.set_ylabel("Backend", fontsize=12)
    ax1.set_title("Processing Time", fontsize=13, fontweight="bold")
    ax1.grid(axis="x", alpha=0.3)

    # Cache hit rate (if available)
    cache_rates = []
    for b in backends:
        total_cached = sum(
            d.get("cached_blocks", 0) for d in data[b].get("per_document", {}).values()
        )
        total_blocks = data[b]["total_blocks"]
        cache_rate = (total_cached / max(1, total_blocks)) * 100
        cache_rates.append(cache_rate)

    colors2 = plt.cm.cool(np.array(cache_rates) / max(cache_rates + [1]))
    bars2 = ax2.barh(backends, cache_rates, color=colors2, alpha=0.8)
    for bar, rate in zip(bars2, cache_rates):
        width = bar.get_width()
        ax2.text(
            width + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax2.set_xlabel("Cache Hit Rate (%)", fontsize=12)
    ax2.set_ylabel("Backend", fontsize=12)
    ax2.set_title("Translation Cache Efficiency", fontsize=13, fontweight="bold")
    ax2.set_xlim(0, 105)
    ax2.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    output_path = output_dir / "performance_metrics.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def plot_summary_comparison(data: dict, output_dir: Path):
    """Create a comprehensive summary comparison."""
    backends = list(data.keys())

    # Metrics to compare
    metrics = {
        "Quality": [data[b]["avg_quality"] for b in backends],
        "Health": [data[b]["avg_health_ratio"] * 100 for b in backends],
        "Acceptance": [data[b]["avg_acceptance_rate"] for b in backends],
        "Confidence": [data[b]["avg_confidence"] for b in backends],
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(backends))
    width = 0.2

    colors = ["#2ecc71", "#3498db", "#e74c3c", "#f39c12"]

    for idx, (metric, values) in enumerate(metrics.items()):
        offset = (idx - len(metrics) / 2) * width + width / 2
        ax.bar(x + offset, values, width, label=metric, alpha=0.8, color=colors[idx])

    ax.set_xlabel("Backend", fontsize=12)
    ax.set_ylabel("Score (%)", fontsize=12)
    ax.set_title("Overall Performance Comparison", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(backends, fontsize=11)
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    output_path = output_dir / "summary_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {output_path}")


def main():
    """Generate all benchmark visualizations."""
    # Paths
    results_dir = Path(__file__).parent.parent / "experiments" / "results" / "benchmarks"
    summary_path = results_dir / "summary.json"
    output_dir = results_dir / "figures"
    output_dir.mkdir(exist_ok=True, parents=True)

    print("SciTrans Benchmark Visualization")
    print("=" * 50)

    # Load data
    try:
        data = load_benchmark_data(summary_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nRun benchmarks first:")
        print("  make bench")
        sys.exit(1)

    if not data:
        print("Error: No benchmark data found in summary.json")
        sys.exit(1)

    print(f"Loaded data for {len(data)} backend(s)")
    print(f"Output directory: {output_dir}")
    print()

    # Generate plots
    plot_quality_by_document(data, output_dir)
    plot_acceptance_rates(data, output_dir)
    plot_health_scores(data, output_dir)
    plot_performance_metrics(data, output_dir)
    plot_summary_comparison(data, output_dir)

    print()
    print("=" * 50)
    print(f"✓ Generated 5 figures in: {output_dir}")
    print()
    print("Figures:")
    print("  - quality_by_document.png")
    print("  - acceptance_rates.png")
    print("  - health_scores.png")
    print("  - performance_metrics.png")
    print("  - summary_comparison.png")


if __name__ == "__main__":
    main()
