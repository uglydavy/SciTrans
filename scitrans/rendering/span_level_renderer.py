"""Span-level renderer stub.

Some rendering modes rely on a span-level renderer to draw translated text
inline with fine-grained control over each character or word. The full
implementation would take a page, a block and a set of spans with positions
and fonts, and draw the translated text accordingly. This stub provides
minimal functions to satisfy imports without performing any rendering.
"""

from __future__ import annotations

from typing import Any, Optional


def render_span_level(page: Any, block: Any, translated: str, config: Optional[Any] = None) -> None:
    """Placeholder span-level renderer.

    In the full system this would insert the ``translated`` text into the PDF
    page ``page`` at the location specified by ``block`` using details
    contained in ``config``. Here we perform no drawing.

    Args:
        page: A PyMuPDF page object or similar.
        block: A Block-like object describing the area to render into.
        translated: The text to insert.
        config: Optional rendering configuration.
    """
    # Intentionally does nothing in this stub.
    return None