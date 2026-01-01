#!/bin/bash
# Run all 5 thesis experiments

set -e  # Exit on error

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     SciTrans-LLMs — Running All Thesis Experiments           ║"
echo "║     Franck Davy, Wenzhou University, 2025                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Activate venv
source .venv/bin/activate

# Create experiments directory
mkdir -p experiments/results

echo "Creating test PDFs..."
make create-test-pdfs

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "EXPERIMENT 1: Adaptive vs Fixed Strategy"
echo "════════════════════════════════════════════════════════════════"
python experiments/experiment_1_adaptive_vs_fixed.py

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "EXPERIMENT 2: Multi-Dimensional Scoring Validation"
echo "════════════════════════════════════════════════════════════════"
echo "Note: Requires human ratings"
echo "Run: python experiments/human_evaluation_template.py"
echo "Then: python experiments/analyze_scoring_correlation.py"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "EXPERIMENT 3: Repair Efficiency"
echo "════════════════════════════════════════════════════════════════"
echo "Testing repair vs full re-translation..."

# Use complex PDF for repair test
TEST_PDF="test_pdfs/10_complex_realworld.pdf"

# Initial translation
echo "  → Initial translation..."
time scitrans translate --in "$TEST_PDF" --out "experiments/results/exp3/initial.pdf" \
  --artifacts "experiments/results/exp3/initial" --backend cascade_free

# Simulate some failures (for now, use actual failures from translation)
FAILED_COUNT=$(cat experiments/results/exp3/initial/health_scores.json | jq '[.[] | select(.status=="failed")] | length')
echo "  → Failed blocks: $FAILED_COUNT"

if [ "$FAILED_COUNT" -gt 0 ]; then
    # Repair
    echo "  → Repairing failed blocks..."
    time scitrans repair --in "$TEST_PDF" --out "experiments/results/exp3/repaired.pdf" \
      --artifacts "experiments/results/exp3/initial" --backend cascade_free
    
    # Full re-translation (for comparison)
    echo "  → Full re-translation (for comparison)..."
    time scitrans translate --in "$TEST_PDF" --out "experiments/results/exp3/retranslated.pdf" \
      --artifacts "experiments/results/exp3/retranslated" --backend cascade_free --no-cache
else
    echo "  → No failed blocks to repair (system too good!)"
    echo "  → Consider using more challenging PDFs or weaker backend for testing"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "EXPERIMENT 4: Cascade-Free vs Premium Quality"
echo "════════════════════════════════════════════════════════════════"
echo "Comparing cascade_free (free) vs anthropic (paid)..."

# Pick representative PDFs
TEST_PDFS=(
    "test_pdfs/02_math_equations.pdf"
    "test_pdfs/09_scientific_paper.pdf"
    "test_pdfs/10_complex_realworld.pdf"
)

for PDF in "${TEST_PDFS[@]}"; do
    BASENAME=$(basename "$PDF" .pdf)
    echo "  → Testing $BASENAME..."
    
    # Cascade free
    scitrans translate --in "$PDF" \
      --out "experiments/results/exp4/${BASENAME}_cascade.pdf" \
      --artifacts "experiments/results/exp4/cascade/$BASENAME" \
      --backend cascade_free
    
    # Note: Anthropic requires API key
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        scitrans translate --in "$PDF" \
          --out "experiments/results/exp4/${BASENAME}_anthropic.pdf" \
          --artifacts "experiments/results/exp4/anthropic/$BASENAME" \
          --backend anthropic
    else
        echo "    ⚠ ANTHROPIC_API_KEY not set, skipping premium comparison"
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "EXPERIMENT 5: End-to-End Evaluation"
echo "════════════════════════════════════════════════════════════════"
echo "Full system evaluation on all test PDFs..."

for PDF in test_pdfs/*.pdf; do
    BASENAME=$(basename "$PDF" .pdf)
    echo "  → Processing $BASENAME..."
    
    scitrans translate --in "$PDF" \
      --out "experiments/results/exp5/${BASENAME}.pdf" \
      --artifacts "experiments/results/exp5/$BASENAME" \
      --backend cascade_free
done

# Aggregate results
echo ""
echo "Aggregating results..."
python experiments/aggregate_results.py

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ ALL EXPERIMENTS COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Results saved to: experiments/results/"
echo ""
echo "Next steps:"
echo "  1. Review automated results: experiments/results/*/experiment_*_results.json"
echo "  2. Collect human ratings: python experiments/human_evaluation_template.py"
echo "  3. Analyze results: python experiments/analyze_all.py"
echo "  4. Generate visualizations: make viz"
echo ""
echo "For thesis writing:"
echo "  - Figures: experiments/results/*/figures/*.png"
echo "  - Tables: experiments/results/*/*.json"
echo "  - Statistics: experiments/results/analysis_summary.json"
echo ""

