from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

from scitrans.core.models import Document
from scitrans.rendering.font_manager import FontManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderConfig:
    min_font_size: float = 5.0
    max_shrink_ratio: float = 0.55  # don't shrink below 55% of original unless necessary
    line_height: float = 1.2
    redact_padding: float = 0.5  # pts
    align_threshold: float = 12.0  # pts difference between left/right margins for centering
    preserve_color: bool = False  # future
    debug_draw_boxes: bool = False


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
    """Binary-search the largest font size that fits inside rect."""

    if not text.strip():
        return base_size

    lo = max(cfg.min_font_size, base_size * cfg.max_shrink_ratio)
    hi = base_size

    best = lo
    # Ensure we start from hi down, so we keep best-looking size
    for _ in range(16):
        mid = (lo + hi) / 2.0
        # We need a dry-run. PyMuPDF actually writes. So we instead approximate by:
        # - insert into a temporary page is heavy; instead we can use return value:
        #   insert_textbox returns negative if it doesn't fit.
        # We'll do: insert, then immediately clean by redacting? That is messy.
        # Simpler: use a hidden scratch page.
        scratch = fitz.open()
        sp = scratch.new_page(width=page.rect.width, height=page.rect.height)
        ret = _try_insert_textbox(
            sp,
            rect,
            text,
            fontname=fontname,
            fontfile=fontfile,
            fontsize=mid,
            align=align,
            line_height=cfg.line_height,
        )
        scratch.close()

        if ret >= 0:
            best = mid
            lo = mid
        else:
            hi = mid

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
