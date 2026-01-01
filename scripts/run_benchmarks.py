#!/usr/bin/env python3
"""Run benchmark translations across multiple backends.

Defaults to free backends (cascade_free, dummy) so it can run with no secrets.
If API keys are present, paid backends can be included with --include-paid.
Outputs per-doc artifacts plus an aggregate summary (JSON + CSV).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Ensure repo root on PYTHONPATH when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scitrans.cli.main import _get_backend  # noqa: E402
from scitrans.pipeline import PipelineConfig, run_pipeline  # noqa: E402

DEFAULT_MODELS: dict[str, str] = {
    "cascade_free": "cascade_free",
    "dummy": "dummy",
    "anthropic": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o-mini",
    "google": "google-translate",
    "huggingface": "Helsinki-NLP/opus-mt-en-fr",
    "ollama": "llama3",
}


def detect_backends(user_backends: list[str], include_paid: bool) -> list[str]:
    """Build backend list respecting available keys."""
    if user_backends:
        return user_backends

    backends = ["cascade_free", "dummy"]
    if include_paid:
        if os.getenv("ANTHROPIC_API_KEY"):
            backends.append("anthropic")
        if os.getenv("OPENAI_API_KEY"):
            backends.append("openai")
    return backends


def collect_metrics(report: dict) -> dict:
    scoring = report.get("scoring", {}) or {}
    return {
        "num_blocks": report.get("num_blocks"),
        "num_ok": report.get("num_ok"),
        "num_failed": report.get("num_failed"),
        "document_quality": scoring.get("document_quality"),
        "confidence": scoring.get("confidence"),
        "acceptance_rate": scoring.get("acceptance_rate"),
    }


def main():
    parser = argparse.ArgumentParser(description="Run SciTrans benchmarks.")
    parser.add_argument(
        "--pdfs",
        default="test_pdfs/*.pdf",
        help="Glob for PDFs to benchmark (default: test_pdfs/*.pdf)",
    )
    parser.add_argument(
        "--backends",
        default="",
        help="Comma-separated backends to run (default: auto: cascade_free,dummy; plus paid if --include-paid and keys set)",
    )
    parser.add_argument(
        "--include-paid",
        action="store_true",
        help="Include paid backends if keys are set (anthropic/openai)",
    )
    parser.add_argument(
        "--out",
        default="experiments/results/benchmarks",
        help="Output directory for benchmark artifacts",
    )
    parser.add_argument(
        "--source",
        default="en",
        help="Source language (default: en)",
    )
    parser.add_argument(
        "--target",
        default="fr",
        help="Target language (default: fr)",
    )
    parser.add_argument(
        "--translate-tables",
        action="store_true",
        help="Enable table translation (default: preserve tables)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable translation cache",
    )
    args = parser.parse_args()

    pdf_paths = sorted([p for g in args.pdfs.split(",") for p in Path().glob(g)])
    if not pdf_paths:
        raise SystemExit(f"No PDFs found for pattern(s): {args.pdfs}")

    user_backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    backends = detect_backends(user_backends, args.include_paid)

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for backend_name in backends:
        model = DEFAULT_MODELS.get(backend_name, backend_name)
        backend = _get_backend(backend_name, model=model)
        backend_out = out_root / backend_name
        backend_out.mkdir(parents=True, exist_ok=True)

        for pdf in pdf_paths:
            t0 = time.time()
            out_pdf = backend_out / f"{pdf.stem}_{backend_name}.pdf"

            cfg = PipelineConfig(
                source_lang=args.source,
                target_lang=args.target,
                model=model,
                output_dir=str(backend_out),
                n_candidates=3,
                context_window=2,
                use_cache=not args.no_cache,
                enable_reranking=True,
                retry_failed=True,
                render_math_aware=True,
                translate_tables=args.translate_tables,
            )

            try:
                report = run_pipeline(
                    input_pdf=str(pdf),
                    output_pdf=str(out_pdf),
                    backend=backend,
                    cfg=cfg,
                )
            except Exception as e:  # pragma: no cover - defensive logging
                rows.append(
                    {
                        "pdf": pdf.name,
                        "backend": backend_name,
                        "duration_sec": round(time.time() - t0, 3),
                        "error": str(e),
                    }
                )
                continue

            metrics = collect_metrics(report)
            rows.append(
                {
                    "pdf": pdf.name,
                    "backend": backend_name,
                    "duration_sec": round(time.time() - t0, 3),
                    **metrics,
                }
            )

    # Write summary JSON/CSV
    summary_json = out_root / "summary.json"
    summary_csv = out_root / "summary.csv"

    summary_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    if rows:
        fieldnames = list(rows[0].keys())
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"✓ Benchmarks complete. Results in {out_root}")


if __name__ == "__main__":
    main()
