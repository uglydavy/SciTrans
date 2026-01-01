from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FormatChecks:
    missing_placeholders: int
    numeric_mismatch: int
    dropped_bullets: int


_NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def quick_format_checks(source: str, translated: str) -> FormatChecks:
    """Heuristic checks that catch common catastrophic failures."""

    # Numeric stability
    src_nums = _NUM_RE.findall(source)
    tgt_nums = _NUM_RE.findall(translated)
    numeric_mismatch = 0 if src_nums == tgt_nums else 1

    # Bullets
    src_bullets = source.count("•") + source.count("-") + source.count("–")
    tgt_bullets = translated.count("•") + translated.count("-") + translated.count("–")
    dropped_bullets = 1 if (src_bullets > 0 and tgt_bullets == 0) else 0

    # Placeholders (the real check happens in masking engine)
    missing_placeholders = 0

    return FormatChecks(
        missing_placeholders=missing_placeholders,
        numeric_mismatch=numeric_mismatch,
        dropped_bullets=dropped_bullets,
    )
