#!/usr/bin/env python3
"""Experiment 1: Adaptive vs Fixed Translation Strategy

Research Question: Does adaptive parameter selection improve quality/cost tradeoff?

Compares:
- Control: Fixed strategy (all blocks same parameters)
- Experimental: Adaptive strategy (parameters adapt to complexity)
"""

import json
import time
from pathlib import Path

from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.cascade_free import CascadeFreeBackend


def run_experiment(test_pdfs_dir: str = "test_pdfs", output_dir: str = "experiments/results/exp1"):
    """Run Experiment 1."""
    print("=" * 70)
    print("EXPERIMENT 1: Adaptive vs Fixed Strategy")
    print("=" * 70)

    test_pdfs = list(Path(test_pdfs_dir).glob("*.pdf"))
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    backend = CascadeFreeBackend()
    results = []

    for pdf in test_pdfs:
        print(f"\nProcessing: {pdf.name}")

        # Control: Fixed strategy
        print("  → Fixed strategy...")
        cfg_fixed = PipelineConfig(
            source_lang="en",
            target_lang="fr",
            output_dir=str(output_path / "fixed"),
            n_candidates=3,
            context_window=0,
            temperature=0.1,
            use_cache=False,  # Disable cache for fair comparison
            enable_reranking=True,
            retry_failed=True,
        )

        t1 = time.time()
        report_fixed = run_pipeline(
            input_pdf=str(pdf),
            output_pdf=str(output_path / "fixed" / f"{pdf.stem}_fixed.pdf"),
            backend=backend,
            cfg=cfg_fixed,
        )
        time_fixed = time.time() - t1

        # Experimental: Adaptive strategy (uses pre-scoring)
        print("  → Adaptive strategy...")
        cfg_adaptive = PipelineConfig(
            source_lang="en",
            target_lang="fr",
            output_dir=str(output_path / "adaptive"),
            n_candidates=3,  # Will be adapted per block
            context_window=2,
            temperature=0.1,  # Will be adapted per block
            use_cache=False,  # Disable cache for fair comparison
            enable_reranking=True,
            retry_failed=True,
        )

        t2 = time.time()
        report_adaptive = run_pipeline(
            input_pdf=str(pdf),
            output_pdf=str(output_path / "adaptive" / f"{pdf.stem}_adaptive.pdf"),
            backend=backend,
            cfg=cfg_adaptive,
        )
        time_adaptive = time.time() - t2

        # Collect results
        results.append(
            {
                "pdf": pdf.name,
                "fixed": {
                    "quality": report_fixed["scoring"]["document_quality"],
                    "acceptance_rate": report_fixed["scoring"]["acceptance_rate"],
                    "time_seconds": time_fixed,
                    "failed_blocks": report_fixed["scoring"]["blocks_need_retry"],
                },
                "adaptive": {
                    "quality": report_adaptive["scoring"]["document_quality"],
                    "acceptance_rate": report_adaptive["scoring"]["acceptance_rate"],
                    "time_seconds": time_adaptive,
                    "failed_blocks": report_adaptive["scoring"]["blocks_need_retry"],
                },
                "improvement": {
                    "quality_delta": report_adaptive["scoring"]["document_quality"]
                    - report_fixed["scoring"]["document_quality"],
                    "time_delta": time_adaptive - time_fixed,
                },
            }
        )

    # Save results
    results_file = output_path / "experiment_1_results.json"
    results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Print summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    avg_quality_fixed = sum(r["fixed"]["quality"] for r in results) / len(results)
    avg_quality_adaptive = sum(r["adaptive"]["quality"] for r in results) / len(results)

    print("\nAverage Quality:")
    print(f"  Fixed:    {avg_quality_fixed:.2%}")
    print(f"  Adaptive: {avg_quality_adaptive:.2%}")
    print(f"  Improvement: {(avg_quality_adaptive - avg_quality_fixed):.2%}")

    print(f"\nResults saved to: {results_file}")
    print("\nNext steps:")
    print("  1. Run: python experiments/analyze_experiment_1.py")
    print("  2. Review: experiments/results/exp1/experiment_1_results.json")

    return results


if __name__ == "__main__":
    import sys

    test_dir = sys.argv[1] if len(sys.argv) > 1 else "test_pdfs"
    run_experiment(test_dir)
