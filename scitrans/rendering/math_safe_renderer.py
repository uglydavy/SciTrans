from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

from scitrans.core.models import Document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderConfig:
    """Configuration for layout-preserving rendering.

    CRITICAL: These defaults are tuned for maximum layout preservation and
    consistent font sizing across the document. The goal is to maintain the
    original document's visual appearance as closely as possible.
    
    - Moderate shrinking allowed (down to 85% of original)
    - Reasonable minimum font size (7.0pt - still readable)
    - Standard line height (1.2 for readability)
    - Minimal margins to maximize space while preventing overlaps
    """

    # Minimum font size. Use a smaller floor to avoid truncation in tight boxes.
    min_font_size: float = 6.0
    # Allow shrinking to 80% of original (more aggressive to fit text, but still readable)
    max_shrink_ratio: float = 0.80
    # Standard line height for readability
    line_height: float = 1.2
    # No padding to prevent overlaps
    redact_padding: float = 0.0
    # pts difference between left/right margins for centering
    align_threshold: float = 12.0
    # future
    preserve_color: bool = False
    debug_draw_boxes: bool = False
    # Break long blocks across pages if they don't fit
    enable_page_breaking: bool = True
    # 1% margin to prevent edge overflow (minimal margin for maximum space)
    overflow_margin: float = 0.01


def _infer_alignment(page_width: float, x0: float, x1: float, threshold: float) -> int:
    """Infer alignment from block margins.

    Returns fitz.TEXT_ALIGN_* constant.
    Defaults to LEFT alignment for better readability.
    """
    left = x0
    right = page_width - x1
    # Only center if margins are very close (likely centered text)
    # Otherwise default to left alignment
    if abs(left - right) <= threshold and left < 50:  # Only if close to center AND near left margin
        return fitz.TEXT_ALIGN_CENTER
    # Default to left alignment for paragraphs and most content
    return fitz.TEXT_ALIGN_LEFT


def _try_insert_textbox(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    fontname: str,
    fontfile: str | None,
    fontsize: float,
    align: int,
    line_height: float,
    color: tuple[float, float, float] | None = None,
) -> float:
    """Insert text into a textbox with optional color.
    
    Args:
        color: Optional RGB tuple (0-1 range) for text color
    """
    kwargs = {
        "fontname": fontname,
        "fontfile": fontfile,
        "fontsize": fontsize,
        "align": align,
        "lineheight": line_height,
    }
    if color:
        kwargs["color"] = color
    
    return page.insert_textbox(
        rect,
        text,
        **kwargs
    )


def _fit_font_size(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    fontname: str,
    fontfile: str | None,
    base_size: float,
    cfg: RenderConfig,
    align: int,
) -> float:
    """Binary-search the largest font size that fits inside rect.
    
    CRITICAL: Preserves original font size whenever possible.
    Only shrinks when absolutely necessary to prevent overflow.
    
    Strategy:
    1. Try original size first
    2. Only shrink if original doesn't fit
    3. Use moderate margins and conservative shrinking
    4. Maintain consistency by preferring original size
    """

    if not text.strip():
        return base_size

    # CRITICAL: Use minimal margin to maximize available space
    # Smaller margin = more space = less need to shrink = more consistent sizing
    margin = cfg.overflow_margin
    safe_rect = fitz.Rect(
        rect.x0 + rect.width * margin,
        rect.y0 + rect.height * margin,
        rect.x1 - rect.width * margin,
        rect.y1 - rect.height * margin,
    )
    
    # Ensure safe_rect is valid (not empty or inverted)
    if safe_rect.width <= 0 or safe_rect.height <= 0:
        safe_rect = rect  # Fallback to original if margin makes it invalid
        logger.debug(f"Safe rect became invalid, using original rect")

    # CRITICAL: Try original size first - prefer preserving it
    scratch = fitz.open()
    sp = scratch.new_page(width=page.rect.width, height=page.rect.height)
    ret = _try_insert_textbox(
        sp,
        safe_rect,
        text,
        fontname=fontname,
        fontfile=fontfile,
        fontsize=base_size,
        align=align,
        line_height=cfg.line_height,
    )
    scratch.close()
    
    if ret >= 0:
        # Original size fits - use it! This ensures consistency
        return base_size

    # Original size doesn't fit - need to shrink
    logger.debug(
        f"Original font size {base_size:.2f} doesn't fit, shrinking. "
        f"Text length: {len(text)}, Block size: {rect.width:.1f}x{rect.height:.1f}"
    )

    # Calculate bounds for binary search
    lo = max(cfg.min_font_size, base_size * cfg.max_shrink_ratio)
    hi = base_size
    
    # If base size is already below minimum, return it
    if base_size < cfg.min_font_size:
        return base_size

    best = lo
    # PHASE 3.1: Binary search with more iterations for precision (30 iterations)
    for iteration in range(30):
        mid = (lo + hi) / 2.0
        
        # Use scratch page for dry-run testing
        scratch = fitz.open()
        sp = scratch.new_page(width=page.rect.width, height=page.rect.height)
        ret = _try_insert_textbox(
            sp,
            safe_rect,
            text,
            fontname=fontname,
            fontfile=fontfile,
            fontsize=mid,
            align=align,
            line_height=cfg.line_height,
        )
        scratch.close()

        if ret >= 0:
            # Text fits - try larger size
            best = mid
            lo = mid
        else:
            # Text doesn't fit - try smaller size
            hi = mid
        
        # Early exit if we've converged (within 0.05pt - tighter convergence)
        if hi - lo < 0.05:
            break

    # Single verification pass to ensure text actually fits
    scratch = fitz.open()
    sp = scratch.new_page(width=page.rect.width, height=page.rect.height)
    final_check = _try_insert_textbox(
        sp,
        safe_rect,
        text,
        fontname=fontname,
        fontfile=fontfile,
        fontsize=best,
        align=align,
        line_height=cfg.line_height,
    )
    scratch.close()
    
    if final_check < 0:
        # Text still doesn't fit - reduce further as last resort
        best = max(cfg.min_font_size, best * 0.95)
        logger.warning(
            f"Font size {best:.2f} still doesn't fit after adjustment. "
            f"Text may be truncated. Text length: {len(text)}, Block size: {rect.width:.1f}x{rect.height:.1f}"
        )

    return best


def render_translated_pdf(
    *,
    source_pdf: str,
    doc: Document,
    translations: dict[str, str],
    output_pdf: str,
    cfg: RenderConfig | None = None,
    assets_dir: str | None = None,
) -> None:
    """Legacy entrypoint retained for compatibility.

    Delegates to the primary renderer for best font/style fidelity.
    """
    from scitrans.rendering.perfect_renderer import render_translated_pdf_perfect

    render_translated_pdf_perfect(
        source_pdf=source_pdf,
        doc=doc,
        translations=translations,
        output_pdf=output_pdf,
        cfg=cfg,
        assets_dir=assets_dir,
        translate_tables=False,
    )
