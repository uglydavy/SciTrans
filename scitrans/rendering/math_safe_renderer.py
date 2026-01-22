from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

from scitrans.core.models import Document
from scitrans.rendering.font_manager import FontManager

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

    # Minimum font size. Set to 10.0pt for readability (NEVER go below this)
    # Increased from 7.0pt to ensure text is readable
    min_font_size: float = 10.0
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
    """Render translated blocks onto the original PDF.

    IMPORTANT behavior:
    - Redacts the original block rectangles before inserting translation.
    - Inserts translated text with font fitting to avoid overflow.
    - Never creates new pages.
    """
    cfg = cfg or RenderConfig()
    font_mgr = FontManager(assets_dir=assets_dir)
    pdf = fitz.open(source_pdf)

    if len(pdf) != len(doc.pages):
        raise ValueError("Parsed document pages != PDF pages")

    for page_idx, page_model in enumerate(doc.pages):
        page = pdf[page_idx]

        # 1) Add redactions for all text blocks first
        for block in page_model.blocks:
            if block.type != "text":
                continue
            rect = fitz.Rect(
                block.bbox.x0 - cfg.redact_padding,
                block.bbox.y0 - cfg.redact_padding,
                block.bbox.x1 + cfg.redact_padding,
                block.bbox.y1 + cfg.redact_padding,
            )
            page.add_redact_annot(rect, fill=(1, 1, 1))

        # Apply redactions once per page (fast + avoids redacting newly inserted text)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # 2) Insert translations
        for block in page_model.blocks:
            if block.type != "text":
                continue

            # Source text (debug)
            source_text = "".join(sp.text for ln in block.lines for sp in ln.spans)

            target_text = translations.get(block.id, "")
            if not target_text:
                # Deterministic fallback: if missing, use source text (but pipeline should avoid)
                target_text = source_text

            # Baseline style from the first span
            base_font = "Times-Roman"
            base_size = 11.0
            if block.lines and block.lines[0].spans:
                st = block.lines[0].spans[0].style
                base_font = st.font
                base_size = st.size

            font = font_mgr.pick(base_font)
            rect = fitz.Rect(block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
            align = _infer_alignment(
                page_model.width, block.bbox.x0, block.bbox.x1, cfg.align_threshold
            )

            fitted_size = _fit_font_size(
                page,
                rect,
                target_text,
                fontname=font.name,
                fontfile=font.file,
                base_size=base_size,
                cfg=cfg,
                align=align,
            )

            _try_insert_textbox(
                page,
                rect,
                target_text,
                fontname=font.name,
                fontfile=font.file,
                fontsize=fitted_size,
                align=align,
                line_height=cfg.line_height,
            )

            if cfg.debug_draw_boxes:
                page.draw_rect(rect, color=(1, 0, 0), width=0.5)

    pdf.save(output_pdf)
    pdf.close()
