from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scitrans.core.models import Block, TranslatedBlock

BlockHealthStatus = Literal["ok", "warning", "failed"]


@dataclass(frozen=True)
class BlockHealthScore:
    """Comprehensive health score for a translated block."""

    block_id: str
    status: BlockHealthStatus
    score: float  # 0.0-1.0, where 1.0 is perfect
    reason_codes: list[str]  # e.g., ["placeholder_missing", "overflow", "numeric_drift"]
    details: dict

    def is_healthy(self) -> bool:
        return self.status == "ok"

    def needs_repair(self) -> bool:
        return self.status == "failed"


def compute_block_health(
    block: Block,
    translated_block: TranslatedBlock,
    registry: dict[str, str],
    *,
    check_overflow: bool = True,
    original_bbox: Block | None = None,
) -> BlockHealthScore:
    """Compute health score for a translated block.

    Checks:
    - Placeholder preservation (hard gate)
    - Translation success flag
    - Numeric stability
    - Format preservation (bullets, line breaks)
    - Overflow (if bbox provided)
    """
    reason_codes: list[str] = []
    details: dict = {}
    score = 1.0

    # Hard gate: Check if translation failed or has validation errors
    # Placeholder validation happens in pipeline before restoration
    # Here we check the reported errors from the pipeline
    if translated_block.errors:
        for error in translated_block.errors:
            if "missing_placeholder" in error or "placeholder" in error.lower():
                reason_codes.append("placeholder_missing")
                score = 0.0
                details["placeholder_errors"] = translated_block.errors
                break
            if "validation_failed" in error:
                reason_codes.append("validation_failed")
                score = min(score, 0.5)
                break

    # Translation success flag
    if not translated_block.ok:
        reason_codes.append("translation_failed")
        score = min(score, 0.3)
        details["errors"] = translated_block.errors

    # Numeric stability check
    import re

    num_pattern = r"\b\d+\.?\d*(?:[eE][+-]?\d+)?\b"
    source_nums = set(re.findall(num_pattern, translated_block.source_text))
    translated_nums = set(re.findall(num_pattern, translated_block.translated_text))

    if source_nums:
        preserved = len(source_nums & translated_nums)
        num_ratio = preserved / len(source_nums)
        if num_ratio < 0.9:  # Allow small variations
            reason_codes.append("numeric_drift")
            score = min(score, 0.7)
            details["numeric_preservation"] = num_ratio
            details["missing_numbers"] = list(source_nums - translated_nums)

    # Format preservation
    source_bullets = len(re.findall(r"^[\s]*[-•*]\s", translated_block.source_text, re.MULTILINE))
    translated_bullets = len(
        re.findall(r"^[\s]*[-•*]\s", translated_block.translated_text, re.MULTILINE)
    )

    if source_bullets > 0:
        if translated_bullets < source_bullets * 0.8:  # Allow some variation
            reason_codes.append("format_drift")
            score = min(score, 0.6)
            details["bullet_preservation"] = (
                translated_bullets / source_bullets if source_bullets > 0 else 0.0
            )

    # Overflow check (if bbox provided)
    if check_overflow and original_bbox:
        # Estimate if translated text would overflow
        # This is approximate - actual overflow is checked during rendering
        # We use a simple heuristic: if translation is much longer, flag it
        source_len = len(translated_block.source_text)
        translated_len = len(translated_block.translated_text)
        if source_len > 0:
            length_ratio = translated_len / source_len
            if length_ratio > 1.5:  # Translation is 50% longer
                reason_codes.append("potential_overflow")
                score = min(score, 0.8)
                details["length_ratio"] = length_ratio

    # Determine status
    # Only mark as failed if there are CRITICAL errors (placeholders, translation failure)
    critical_errors = ["placeholder_missing", "translation_failed"]
    has_critical = any(code in reason_codes for code in critical_errors)

    if has_critical or score < 0.5:
        status: BlockHealthStatus = "failed"
    elif score >= 0.85 and len(reason_codes) == 0:
        status = "ok"
    else:
        status = "warning"

    return BlockHealthScore(
        block_id=block.id,
        status=status,
        score=score,
        reason_codes=reason_codes,
        details=details,
    )


def compute_page_health(health_scores: list[BlockHealthScore]) -> dict:
    """Aggregate health scores for a page."""
    total = len(health_scores)
    if total == 0:
        return {
            "total_blocks": 0,
            "ok_blocks": 0,
            "warning_blocks": 0,
            "failed_blocks": 0,
            "mean_score": 1.0,
        }

    ok_count = sum(1 for h in health_scores if h.status == "ok")
    warning_count = sum(1 for h in health_scores if h.status == "warning")
    failed_count = sum(1 for h in health_scores if h.status == "failed")
    mean_score = sum(h.score for h in health_scores) / total

    return {
        "total_blocks": total,
        "ok_blocks": ok_count,
        "warning_blocks": warning_count,
        "failed_blocks": failed_count,
        "mean_score": mean_score,
        "health_ratio": ok_count / total if total > 0 else 0.0,
    }
