"""Span-level renderer utilities.

Some rendering modes rely on a span-level renderer to draw translated text
inline with fine-grained control over each character or word.

This project also expects:
- preserve_color_from_spans(block) -> Optional[(r,g,b)]  (0..1 floats)
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional, Tuple


def render_span_level(page: Any, block: Any, translated: str, config: Optional[Any] = None) -> None:
    """Placeholder span-level renderer (no-op)."""
    return None


def _int_to_rgb(color: int) -> Tuple[float, float, float]:
    """Convert 0xRRGGBB integer color to normalized (r, g, b) floats (0..1)."""
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return (r / 255.0, g / 255.0, b / 255.0)


def preserve_color_from_spans(block: Any) -> Optional[Tuple[float, float, float]]:
    """Pick the most common span color in the block and return it as (r,g,b) floats.

    If no span colors exist, return None.
    """
    colors = []

    lines = getattr(block, "lines", None) or []
    for line in lines:
        spans = getattr(line, "spans", None) or []
        for span in spans:
            style = getattr(span, "style", None)
            c = getattr(style, "color", None) if style is not None else None
            if isinstance(c, int):
                colors.append(c)

    if not colors:
        return None

    dominant = Counter(colors).most_common(1)[0][0]
    return _int_to_rgb(dominant)
