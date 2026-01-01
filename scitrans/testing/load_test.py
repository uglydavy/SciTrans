"""
Load Testing Utilities

Provides tools for testing system performance under load.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)


class LoadTest:
    """Load testing for translation pipeline."""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.results: list[dict[str, Any]] = []

    def run_translation(
        self,
        input_pdf: str,
        backend: str,
        source_lang: str = "en",
        target_lang: str = "fr",
    ) -> dict[str, Any]:
        """Run a single translation and return metrics."""
        from scitrans.cli.main import _get_backend
        from scitrans.pipeline import PipelineConfig, run_pipeline
        from scitrans.utils.env_loader import load_environment_variables

        load_environment_variables()

        start_time = time.time()

        try:
            be = _get_backend(backend, model=backend)
            cfg = PipelineConfig(
                source_lang=source_lang,
                target_lang=target_lang,
                model=backend,
                render_mode="perfect",
                n_candidates=1,  # Fast mode for load testing
            )

            output_pdf = f"load_test_output_{int(time.time())}.pdf"

            report = run_pipeline(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                backend=be,
                cfg=cfg,
            )

            elapsed = time.time() - start_time

            return {
                "success": True,
                "elapsed_time": elapsed,
                "num_blocks": report.get("num_blocks", 0),
                "num_ok": report.get("num_ok", 0),
                "num_failed": report.get("num_failed", 0),
                "quality": report.get("scoring", {}).get("document_quality", 0.0),
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "success": False,
                "elapsed_time": elapsed,
                "error": str(e),
            }

    def run_concurrent(
        self,
        input_pdf: str,
        backend: str,
        num_requests: int = 10,
        source_lang: str = "en",
        target_lang: str = "fr",
    ) -> dict[str, Any]:
        """Run concurrent translation requests."""
        logger.info(f"Starting load test: {num_requests} requests, {self.max_workers} workers")

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(
                    self.run_translation,
                    input_pdf,
                    backend,
                    source_lang,
                    target_lang,
                )
                for _ in range(num_requests)
            ]

            results = [future.result() for future in futures]

        total_time = time.time() - start_time

        # Aggregate results
        successful = sum(1 for r in results if r.get("success", False))
        failed = num_requests - successful
        avg_time = sum(r["elapsed_time"] for r in results) / len(results) if results else 0
        total_blocks = sum(r.get("num_blocks", 0) for r in results)

        return {
            "total_requests": num_requests,
            "successful": successful,
            "failed": failed,
            "total_time": total_time,
            "avg_time_per_request": avg_time,
            "requests_per_second": num_requests / total_time if total_time > 0 else 0,
            "total_blocks_processed": total_blocks,
            "results": results,
        }
