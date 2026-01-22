# Visualization Tools

This directory contains tools for visualizing translation quality, performance, and system behavior.

## Visualization Categories

### Quality Visualizations
- `viz_quality_heatmap.py` - Heatmap of block-level quality scores
- `viz_error_distribution.py` - Distribution of error types across documents
- `viz_score_breakdown.py` - Breakdown of quality dimensions (placeholder, numeric, format, etc.)
- `viz_acceptance_rate.py` - Acceptance rate trends over time

### Performance Visualizations
- `viz_latency_analysis.py` - Backend latency comparison
- `viz_throughput.py` - Translation throughput over time
- `viz_retry_patterns.py` - Retry frequency and success rates
- `viz_backend_usage.py` - Backend selection patterns (for cascade_free)

### Feature Impact Visualizations
- `viz_ablation_results.py` - Visualize ablation study results
- `viz_feature_correlation.py` - Correlation between features and quality
- `viz_reranking_impact.py` - Impact of reranking on candidate selection
- `viz_context_impact.py` - Impact of context window size

### Document Analysis
- `viz_block_types.py` - Distribution of block types (headers, paragraphs, tables)
- `viz_complexity_distribution.py` - Pre-translation complexity scores
- `viz_translation_length_ratio.py` - Source vs target length ratios
- `viz_placeholder_density.py` - Placeholder distribution across documents

## Running Visualizations

```bash
# Generate all visualizations for a translation
python tests/visualizations/generate_all.py --artifacts outputs/my_doc

# Generate specific visualization
python tests/visualizations/viz_quality_heatmap.py --artifacts outputs/my_doc --output quality_heatmap.png

# Generate comparison visualization
python tests/visualizations/compare_translations.py --artifacts1 outputs/doc1 --artifacts2 outputs/doc2
```

## Visualization Output Formats

- **PNG**: High-resolution images for papers/presentations
- **SVG**: Vector graphics for scalable figures
- **HTML**: Interactive visualizations (Plotly)
- **PDF**: Publication-ready figures

## Dependencies

```bash
pip install matplotlib seaborn plotly pandas numpy scipy
```

## Adding New Visualizations

1. Create a new file `viz_<visualization_name>.py`
2. Load data from artifacts directory (JSON files)
3. Process and transform data for visualization
4. Generate plot using matplotlib/seaborn/plotly
5. Save to output file
6. Add CLI interface using argparse
7. Add to this README

## Example Visualization Script

```python
#!/usr/bin/env python3
import json
import matplotlib.pyplot as plt
from pathlib import Path

def visualize_quality_scores(artifacts_dir: str, output_file: str):
    # Load post-translation scores
    scores_path = Path(artifacts_dir) / "post_scores.json"
    with open(scores_path) as f:
        scores = json.load(f)
    
    # Extract quality dimensions
    block_ids = [s["block_id"] for s in scores]
    overall_scores = [s["overall_score"] for s in scores]
    
    # Create bar chart
    plt.figure(figsize=(12, 6))
    plt.bar(range(len(block_ids)), overall_scores)
    plt.xlabel("Block Index")
    plt.ylabel("Quality Score")
    plt.title("Translation Quality by Block")
    plt.ylim(0, 1)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    print(f"✅ Saved visualization to {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--output", default="quality_scores.png")
    args = parser.parse_args()
    visualize_quality_scores(args.artifacts, args.output)
```

