# Experiments

Automated experiment scripts for thesis research, data analysis, and visualization.

## Experiment Scripts

### `experiment_1_adaptive_vs_fixed.py`
Compare adaptive translation strategies vs. fixed parameters.

**Purpose:** Validate the adaptive scoring innovation.

**Usage:**
```bash
python3 experiments/experiment_1_adaptive_vs_fixed.py --pdfs "corpus/*.pdf"
```

**Output:** `experiments/results/exp1/`
- `comparison.json` — Per-document quality scores
- `summary.txt` — Statistical summary

**Hypothesis:** Adaptive parameter selection improves quality by 5-10% vs fixed parameters.

---

### `human_evaluation_template.py`
Generate HTML form for human evaluation of translations.

**Purpose:** Collect human quality ratings for correlation with automated metrics.

**Usage:**
```bash
python3 experiments/human_evaluation_template.py
```

**Output:** `experiments/results/exp1/evaluation_form.html`

**Workflow:**
1. Run script to generate form
2. Open form in browser
3. Review translated PDFs side-by-side
4. Fill in ratings (1-5 scale)
5. Save ratings as JSON
6. Analyze correlation with automated scores

---

### `aggregate_results.py`
Aggregate all experimental results into a single dataset.

**Purpose:** Combine data from all experiments for analysis.

**Usage:**
```bash
python3 experiments/aggregate_results.py
```

**Output:** `experiments/results/aggregated_results.json`

**Includes:**
- All experimental runs
- Benchmark results
- Human ratings (if available)
- Statistical summaries

---

### `analyze_experiment_1.py`
Statistical analysis of adaptive vs. fixed comparison.

**Purpose:** Test significance of adaptive strategy improvements.

**Usage:**
```bash
python3 experiments/analyze_experiment_1.py
```

**Analysis:**
- Paired t-test (adaptive vs. fixed)
- Effect size calculation
- Confidence intervals
- Correlation analysis

**Requirements:**
```bash
pip install -e ".[thesis]"  # scipy, pandas
```

---

### `create_thesis_figures.py`
Generate publication-quality figures for thesis.

**Purpose:** Create all thesis figures in one command.

**Usage:**
```bash
python3 experiments/create_thesis_figures.py
```

Or via Make:
```bash
make viz
```

**Generated figures (300 DPI PNG):**
- Adaptive strategy comparison
- Quality distribution
- Processing time comparison
- Cache efficiency
- Repair workflow illustration

**Output:** `experiments/results/thesis_figures/`

**Requirements:**
```bash
pip install -e ".[thesis]"  # matplotlib, seaborn
```

---

### `verify_thesis_readiness.py`
Automated checklist for thesis defense preparation.

**Purpose:** Verify all experiments, tests, and documentation are complete.

**Usage:**
```bash
python3 experiments/verify_thesis_readiness.py
```

**Checks:**
- System runs without errors
- All tests pass
- Pre/post scoring artifacts generated
- Experimental data available
- Figures generated
- Documentation complete

---

### `run_all_experiments.sh`
Run all experiments in sequence.

**Usage:**
```bash
bash experiments/run_all_experiments.sh
```

Or via Make:
```bash
make experiments
```

**What it does:**
1. Runs `experiment_1_adaptive_vs_fixed.py`
2. Generates human evaluation template
3. Aggregates results
4. Performs statistical analysis
5. Creates thesis figures

**Duration:** Depends on corpus size (10-60 minutes typical)

---

## Experiment Results Structure

```
experiments/results/
├── exp1/                    # Experiment 1: Adaptive vs Fixed
│   ├── comparison.json
│   ├── summary.txt
│   └── human_ratings/       # Optional: human evaluation data
├── benchmarks/              # Benchmark results
│   ├── cascade_free/
│   ├── anthropic/
│   ├── summary.json
│   ├── summary.csv
│   └── figures/             # Benchmark visualizations
├── thesis_figures/          # Publication-ready figures
│   ├── adaptive_comparison.png
│   ├── quality_distribution.png
│   └── ...
└── aggregated_results.json  # Combined dataset
```

## Running Experiments for Thesis

### Complete workflow:

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Install thesis dependencies
pip install -e ".[thesis]"

# 3. Setup API keys (if using paid backends)
export ANTHROPIC_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."

# 4. Collect corpus (20-30 scientific PDFs)
mkdir -p corpus/
# Add your PDFs to corpus/

# 5. Run all experiments
make experiments

# 6. Generate visualizations
make viz
make viz-bench

# 7. Verify readiness
python3 experiments/verify_thesis_readiness.py

# 8. (Optional) Collect human ratings
python3 experiments/human_evaluation_template.py
# Follow instructions in generated form
```

## Data Analysis

All experimental data is in JSON format for easy analysis:

```python
import json
import pandas as pd

# Load aggregated results
with open("experiments/results/aggregated_results.json") as f:
    data = json.load(f)

# Convert to DataFrame
df = pd.DataFrame(data)

# Analyze
print(df["quality"].mean())
print(df.groupby("backend")["quality"].mean())
```

## Experiment Design

### Experiment 1: Adaptive vs. Fixed
- **IV:** Parameter selection strategy (adaptive vs. fixed)
- **DV:** Translation quality score
- **Control:** Same corpus, same backend
- **Hypothesis:** Adaptive > Fixed by 5-10%

### Future Experiments
- Reranking efficacy (1 vs. 3 vs. 5 candidates)
- Context window impact (0 vs. 2 vs. 4 blocks)
- Backend comparison (cascade_free vs. premium)
- Cache efficiency (first run vs. repeated)
- Repair workflow efficiency

## Troubleshooting

### Missing dependencies
```bash
pip install -e ".[thesis]"
```

### No results generated
```bash
# Check if experiments ran successfully
ls experiments/results/
```

### Visualization errors
```bash
# Ensure matplotlib backend is set
export MPLBACKEND=Agg
```

## Contact

**Author:** Franck Davy (aknk.v@pm.me)  
**Institution:** Wenzhou University  
**Thesis:** "Adaptive Document Translation Enhanced by Technology based on LLMs"  
**Year:** 2025

