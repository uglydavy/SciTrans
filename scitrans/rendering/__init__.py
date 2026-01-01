"""PDF rendering module for SciTrans."""

from scitrans.rendering.enhanced_block_renderer import render_translated_pdf_enhanced
from scitrans.rendering.math_aware_renderer import render_translated_pdf_math_aware
from scitrans.rendering.math_safe_renderer import RenderConfig, render_translated_pdf
from scitrans.rendering.perfect_renderer import render_translated_pdf_perfect

__all__ = [
    "RenderConfig",
    "render_translated_pdf",
    "render_translated_pdf_enhanced",
    "render_translated_pdf_math_aware",
    "render_translated_pdf_perfect",
]

