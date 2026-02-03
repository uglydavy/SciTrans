from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class FormatChecks:
    missing_placeholders: int
    numeric_mismatch: int
    dropped_bullets: int


_NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_BULLET_RE = re.compile(r"^[\s]*[-•*]\s", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"@@SCITRANS_[A-Z_]+_\d{4}_[A-F0-9]{8}@@")


def quick_format_checks(source: str, translated: str) -> FormatChecks:
    """Heuristic checks that catch common catastrophic failures."""

    # Numeric stability
    src_nums = Counter(_NUM_RE.findall(source))
    tgt_nums = Counter(_NUM_RE.findall(translated))
    numeric_mismatch = 0 if src_nums == tgt_nums else 1

    # Bullets
    src_bullets = len(_BULLET_RE.findall(source))
    tgt_bullets = len(_BULLET_RE.findall(translated))
    dropped_bullets = 1 if (src_bullets > 0 and tgt_bullets == 0) else 0

    # Placeholders (the real check happens in masking engine)
    src_placeholders = _PLACEHOLDER_RE.findall(source)
    tgt_placeholders = _PLACEHOLDER_RE.findall(translated)
    missing_placeholders = 1 if len(tgt_placeholders) < len(src_placeholders) else 0

    return FormatChecks(
        missing_placeholders=missing_placeholders,
        numeric_mismatch=numeric_mismatch,
        dropped_bullets=dropped_bullets,
    )
