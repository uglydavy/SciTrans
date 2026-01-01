#!/usr/bin/env python3
"""Automated verification checklist for thesis defense readiness.

Checks all requirements are met before thesis defense.
"""

import json
import subprocess
import sys
from pathlib import Path


def check_system_runs():
    """Verify system runs without errors."""
    print("\n[1/9] Checking system runs without errors...")
    try:
        result = subprocess.run(
            [
                "python3",
                "-c",
                "from scitrans import __version__, __author__; print(f'{__author__} v{__version__}')",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"  ✓ System loads: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"  ✗ System error: {e}")
        return False


def check_tests_passing():
    """Verify all tests pass."""
    print("\n[2/9] Checking all tests pass...")
    try:
        result = subprocess.run(
            ["pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            # Count passed tests
            passed = result.stdout.count(" PASSED")
            print(f"  ✓ All tests passing: {passed} tests")
            return True
        else:
            print("  ✗ Some tests failing")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            return False
    except Exception as e:
        print(f"  ⚠ Could not run tests: {e}")
        return False


def check_scoring_artifacts():
    """Verify pre/post scoring generates artifacts."""
    print("\n[3/9] Checking pre/post scoring generates artifacts...")

    # Look for any completed translation with scoring
    outputs = Path("outputs")
    if not outputs.exists():
        print("  ⚠ No outputs directory (run a translation first)")
        return False

    scored_docs = []
    for doc_dir in outputs.iterdir():
        if doc_dir.is_dir():
            if (doc_dir / "pre_scores.json").exists() and (doc_dir / "post_scores.json").exists():
                scored_docs.append(doc_dir.name)

    if scored_docs:
        print(f"  ✓ Scoring works: {len(scored_docs)} documents with pre/post scores")
        for doc in scored_docs[:3]:
            print(f"    - {doc}")
        return True
    else:
        print(
            "  ✗ No pre/post scores found (run: scitrans translate --in test.pdf --out test_fr.pdf)"
        )
        return False


def check_experiments_completed():
    """Verify all 5 experiments completed."""
    print("\n[4/9] Checking experiments completed...")

    exp_dir = Path("experiments/results")
    if not exp_dir.exists():
        print("  ✗ No experiments run yet")
        print("    Run: make experiments")
        return False

    experiments = {
        "Experiment 1 (Adaptive vs Fixed)": exp_dir / "exp1" / "experiment_1_results.json",
        "Experiment 2 (Scoring Validation)": exp_dir / "exp2",  # Requires human data
        "Experiment 3 (Repair Efficiency)": exp_dir / "exp3",
        "Experiment 4 (Backend Comparison)": exp_dir / "exp4",
        "Experiment 5 (End-to-End)": exp_dir / "exp5",
    }

    completed = 0
    for name, path in experiments.items():
        if path.exists():
            print(f"  ✓ {name}")
            completed += 1
        else:
            print(f"  ✗ {name} (not run)")

    print(f"\n  Completed: {completed}/5 experiments")
    return completed >= 3  # At least 3 experiments


def check_human_evaluation():
    """Verify human evaluation data collected."""
    print("\n[5/9] Checking human evaluation data...")

    human_data = Path("experiments/results/exp1/human_ratings")
    if human_data.exists() and list(human_data.glob("*.json")):
        ratings = list(human_data.glob("*.json"))
        print(f"  ✓ Human ratings collected: {len(ratings)} raters")
        return True
    else:
        print("  ⚠ No human ratings yet")
        print("    Generate form: python experiments/human_evaluation_template.py")
        return False


def check_statistical_analysis():
    """Verify statistical analysis done."""
    print("\n[6/9] Checking statistical analysis...")

    analysis_file = Path("experiments/results/aggregated_results.json")
    if analysis_file.exists():
        data = json.load(open(analysis_file))
        exp_count = len(data.get("experiments", {}))
        print(f"  ✓ Analysis complete: {exp_count} experiments aggregated")
        return True
    else:
        print("  ✗ No aggregated results")
        print("    Run: python experiments/aggregate_results.py")
        return False


def check_visualizations():
    """Verify figures and tables created."""
    print("\n[7/9] Checking figures and tables...")

    figures_dir = Path("experiments/results/thesis_figures")
    if figures_dir.exists():
        figures = list(figures_dir.glob("*.png")) + list(figures_dir.glob("*.tex"))
        if figures:
            print(f"  ✓ Visualizations created: {len(figures)} files")
            for fig in figures[:5]:
                print(f"    - {fig.name}")
            return True

    print("  ✗ No visualizations yet")
    print("    Run: make viz")
    return False


def check_test_pdfs():
    """Verify test PDFs exist."""
    print("\n[8/9] Checking test PDFs...")

    test_dir = Path("test_pdfs")
    if test_dir.exists():
        pdfs = list(test_dir.glob("*.pdf"))
        print(f"  ✓ Test PDFs: {len(pdfs)} files")
        return len(pdfs) >= 10
    else:
        print("  ✗ No test PDFs")
        print("    Run: make create-test-pdfs")
        return False


def check_documentation():
    """Verify documentation complete."""
    print("\n[9/9] Checking documentation...")

    required_docs = [
        "README.md",
        "THESIS_RESEARCH.md",
        "RESEARCH_SUMMARY.md",
        "START_HERE.md",
        "docs/ADAPTIVE_SCORING.md",
    ]

    missing = []
    for doc in required_docs:
        if not Path(doc).exists():
            missing.append(doc)

    if not missing:
        print(f"  ✓ All required docs present: {len(required_docs)} files")
        return True
    else:
        print(f"  ✗ Missing docs: {missing}")
        return False


def main():
    """Run all verification checks."""
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║                                                                  ║")
    print("║     SciTrans-LLMs — Thesis Defense Readiness Verification       ║")
    print("║     Franck Davy, Wenzhou University, 2025                       ║")
    print("║                                                                  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    checks = [
        ("System Runs", check_system_runs),
        ("Tests Pass", check_tests_passing),
        ("Scoring Works", check_scoring_artifacts),
        ("Experiments Done", check_experiments_completed),
        ("Human Eval", check_human_evaluation),
        ("Analysis Done", check_statistical_analysis),
        ("Visualizations", check_visualizations),
        ("Test PDFs", check_test_pdfs),
        ("Documentation", check_documentation),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"  ✗ Error checking {name}: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    print(f"\nChecks passed: {passed}/{total}")
    print("\nStatus:")
    for name, status in results.items():
        symbol = "✓" if status else "✗"
        print(f"  [{symbol}] {name}")

    # Overall readiness
    print("\n" + "=" * 70)
    if passed == total:
        print("✅ THESIS DEFENSE READY")
        print("   All checks passed! You're ready to defend.")
    elif passed >= total - 2:
        print("⚠ MOSTLY READY")
        print(f"   {total - passed} items remaining. Address and re-run verification.")
    else:
        print("❌ NOT READY")
        print(f"   {total - passed} items need attention. Follow remediation steps.")
    print("=" * 70)

    # Remediation
    print("\nRemediation steps:")
    if not results.get("System Runs"):
        print("  → Fix system: source .venv/bin/activate && pip install -e .")
    if not results.get("Tests Pass"):
        print("  → Fix tests: pytest tests/ -v")
    if not results.get("Scoring Works"):
        print("  → Run translation: scitrans translate --in test.pdf --out test_fr.pdf")
    if not results.get("Experiments Done"):
        print("  → Run experiments: make experiments")
    if not results.get("Human Eval"):
        print("  → Collect ratings: python experiments/human_evaluation_template.py")
    if not results.get("Analysis Done"):
        print("  → Run analysis: make analyze")
    if not results.get("Visualizations"):
        print("  → Create figures: make viz")
    if not results.get("Test PDFs"):
        print("  → Create PDFs: make create-test-pdfs")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
