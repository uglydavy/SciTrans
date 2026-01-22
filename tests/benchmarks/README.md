# Benchmark Tests

This directory contains performance benchmarks and stress tests for the SciTrans translation pipeline.

## Benchmark Categories

### Performance Benchmarks
- `benchmark_translation_speed.py` - Measure translation throughput (blocks/second)
- `benchmark_backend_latency.py` - Compare backend response times
- `benchmark_parallel_vs_sequential.py` - Compare parallel vs sequential translation
- `benchmark_memory_usage.py` - Monitor memory consumption

### Scalability Benchmarks
- `benchmark_small_pdfs.py` - Test with small PDFs (1-5 pages)
- `benchmark_medium_pdfs.py` - Test with medium PDFs (10-50 pages)
- `benchmark_large_pdfs.py` - Test with large PDFs (100+ pages)
- `benchmark_concurrent_translations.py` - Test multiple simultaneous translations

### Quality Benchmarks
- `benchmark_translation_quality.py` - Measure quality across different backends
- `benchmark_retry_effectiveness.py` - Measure retry success rates
- `benchmark_reranking_improvement.py` - Measure reranking impact on quality
- `benchmark_context_window_impact.py` - Measure context window impact

### Stress Tests
- `stress_test_max_workers.py` - Test with varying worker counts
- `stress_test_long_documents.py` - Test with very long documents (500+ pages)
- `stress_test_complex_math.py` - Test with heavy mathematical content
- `stress_test_mixed_languages.py` - Test with multilingual documents

## Running Benchmarks

```bash
# Run all benchmarks
python -m pytest tests/benchmarks/ -v --benchmark-only

# Run specific benchmark
python tests/benchmarks/benchmark_translation_speed.py

# Generate benchmark report
python tests/benchmarks/generate_benchmark_report.py --output benchmark_results.html
```

## Benchmark Results Format

Each benchmark produces results in the following format:

```json
{
  "benchmark": "translation_speed",
  "date": "2026-01-09",
  "system": {
    "cpu": "Apple M1 Pro",
    "memory": "16GB",
    "python": "3.9.15"
  },
  "results": {
    "throughput": 2.5,  // blocks/second
    "latency_mean": 0.4,  // seconds
    "latency_p50": 0.35,
    "latency_p95": 0.8,
    "latency_p99": 1.2
  },
  "comparison": {
    "baseline": 1.8,  // blocks/second
    "improvement": "39%"
  }
}
```

## Continuous Benchmarking

Benchmarks are automatically run on:
- Every commit to main branch
- Every pull request
- Weekly scheduled runs

Results are tracked over time to detect performance regressions.

## Adding New Benchmarks

1. Create a new file `benchmark_<feature_name>.py`
2. Use `pytest-benchmark` for timing measurements
3. Measure relevant metrics (time, memory, quality)
4. Compare against baseline
5. Generate summary statistics
6. Add to CI/CD pipeline
7. Add to this README

