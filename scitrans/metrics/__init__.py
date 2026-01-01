"""Quality metrics and scoring for SciTrans."""

from scitrans.metrics.health import (
    BlockHealthScore,
    BlockHealthStatus,
    compute_block_health,
    compute_page_health,
)
from scitrans.metrics.layout import (
    LayoutMetrics,
    compute_block_overlap_metrics,
    compute_rendered_pdf_overlap_metrics,
)
# Quality metrics are computed via scoring module
from scitrans.metrics.scoring import (
    PostTranslationScore,
    PreTranslationScore,
    aggregate_scores,
    compute_post_translation_score,
    compute_pre_translation_score,
)

__all__ = [
    "BlockHealthScore",
    "BlockHealthStatus",
    "LayoutMetrics",
    "PostTranslationScore",
    "PreTranslationScore",
    "QualityMetrics",
    "aggregate_scores",
    "compute_block_health",
    "compute_block_overlap_metrics",
    "compute_rendered_pdf_overlap_metrics",
    "compute_page_health",
    "compute_post_translation_score",
    "compute_pre_translation_score",
]

