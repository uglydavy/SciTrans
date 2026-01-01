"""
Metrics Collection

Collects and aggregates system metrics for monitoring.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TranslationMetrics:
    """Metrics for a single translation."""

    job_id: str
    backend: str
    source_lang: str
    target_lang: str
    num_blocks: int
    num_ok: int
    num_failed: int
    elapsed_time: float
    quality_score: float
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None


class MetricsCollector:
    """Collects and aggregates translation metrics."""

    def __init__(self):
        self.metrics: list[TranslationMetrics] = []
        self.backend_stats: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "total_time": 0.0,
                "total_blocks": 0,
                "total_ok": 0,
                "total_failed": 0,
            }
        )

    def record_translation(self, metrics: TranslationMetrics) -> None:
        """Record translation metrics."""
        metrics.end_time = time.time()
        self.metrics.append(metrics)

        # Update backend stats
        stats = self.backend_stats[metrics.backend]
        stats["count"] += 1
        stats["total_time"] += metrics.elapsed_time
        stats["total_blocks"] += metrics.num_blocks
        stats["total_ok"] += metrics.num_ok
        stats["total_failed"] += metrics.num_failed

    def get_backend_stats(self, backend: str) -> dict:
        """Get statistics for a specific backend."""
        return self.backend_stats.get(backend, {})

    def get_all_stats(self) -> dict:
        """Get aggregated statistics."""
        total_translations = len(self.metrics)
        if total_translations == 0:
            return {
                "total_translations": 0,
                "avg_quality": 0.0,
                "avg_time": 0.0,
                "total_blocks": 0,
                "backend_stats": {},
            }

        total_quality = sum(m.quality_score for m in self.metrics)
        total_time = sum(m.elapsed_time for m in self.metrics)
        total_blocks = sum(m.num_blocks for m in self.metrics)

        return {
            "total_translations": total_translations,
            "avg_quality": total_quality / total_translations,
            "avg_time": total_time / total_translations,
            "total_blocks": total_blocks,
            "backend_stats": dict(self.backend_stats),
        }

    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format."""
        stats = self.get_all_stats()

        if format == "json":
            import json

            return json.dumps(stats, indent=2)
        elif format == "csv":
            # Simple CSV export
            lines = ["backend,count,avg_time,avg_quality"]
            for backend, stats in self.backend_stats.items():
                avg_time = stats["total_time"] / stats["count"] if stats["count"] > 0 else 0
                lines.append(f"{backend},{stats['count']},{avg_time:.2f},0.0")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")


# Global metrics collector
_global_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    return _global_collector
