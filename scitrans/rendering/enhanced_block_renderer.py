"""scitrans.rendering.enhanced_block_renderer

Enhanced block-level renderer that preserves major styling elements.

This is a pragmatic middle ground between:
- Simple block rendering (fast, but can lose styling)
- Character-level rendering (very complex, e.g., PDFMathTranslate)

Key features:
- Detects and preserves titles (large font)
- Detects and preserves headers (medium font + bold)
- Preserves bullet points
- Handles bold / italic text (best-effort)
- Uses adaptive font fitting to avoid overflow

Production fixes:
- **Coverage safety**: blocks without a usable translation are left untouched
  (no redaction), so headers/tables/etc never disappear.
- **No-overlap-by-default**: translated text is inserted via `insert_textbox`
  inside the original block rectangle.

"""

from __future__ import annotations

import logging
import re

import fitz

from scitrans.core.models import Block, Document
from scitrans.rendering.font_manager import FontManager
from scitrans.rendering.math_safe_renderer import (
    RenderConfig,
    _fit_font_size,
    _infer_alignment,
    _try_insert_textbox,
)

logger = logging.getLogger(__name__)

# PyMuPDF font flags
FLAG_BOLD = 2**4
FLAG_ITALIC = 2**1


def classify_block_type(block: Block) -> tuple[str, float, str]:
    """Classify block by its dominant styling.

    Returns:
        (block_type, font_size, font_variant)

    block_type:
        - "title"  : very large font
        - "header" : large font
        - "bold"   : bold font
        - "italic" : italic font
        - "bullet" : bullet list item
        - "normal" : default

    font_variant:
        - "Bold", "Italic", "Regular"

    NOTE: This is intentionally simple and deterministic.
    """
    if not block.lines or not block.lines[0].spans:
        return "normal", 11.0, "Regular"

    first_span = block.lines[0].spans[0]
    size = float(first_span.style.size or 11.0)
    flags = int(first_span.style.flags or 0)

    block_text = _block_text(block)

    # Defaults
    block_type = "normal"
    font_variant = "Regular"

    if size >= 18:
        block_type = "title"
        font_variant = "Bold"
        size = max(size, 20.0)
    elif size >= 14:
        block_type = "header"
        font_variant = "Bold"
        size = max(size, 15.0)
    elif flags & FLAG_BOLD:
        block_type = "bold"
        font_variant = "Bold"
    elif flags & FLAG_ITALIC:
        block_type = "italic"
        font_variant = "Italic"
    elif block_text.strip().startswith(("•", "-", "*", "·", "▪", "▫")):
        block_type = "bullet"

    return block_type, size, font_variant


def _block_text(block: Block) -> str:
    if not block.lines:
        return ""
    lines: list[str] = []
    for ln in block.lines:
        lines.append("".join(sp.text for sp in ln.spans))
    return "\n".join(lines).strip()


def _normalize_for_identity_check(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _should_replace_block(
    block: Block,
    translations: dict[str, str],
    *,
    translate_tables: bool,
) -> tuple[bool, str | None, str]:
    """Return (replace?, target_text, source_text)."""

    source_text = _block_text(block)

    # Preserve tables unless explicitly enabled
    if block.meta.get("region") == "table" and not translate_tables:
        return False, None, source_text

    target_text = translations.get(block.id)
    if not target_text or not target_text.strip():
        return False, None, source_text

    # Identity translation: keep original for best fidelity
    if _normalize_for_identity_check(target_text) == _normalize_for_identity_check(source_text):
        return False, None, source_text

    return True, target_text, source_text


def render_translated_pdf_enhanced(
    *,
    source_pdf: str,
    doc: Document,
    translations: dict[str, str],
    output_pdf: str,
    cfg: RenderConfig | None = None,
    assets_dir: str | None = None,
    translate_tables: bool = False,
) -> None:
    """Render translated blocks with block-level styling.

    Only blocks with non-empty, non-identity translations are redacted and replaced.
    Others remain untouched.
    """

    cfg = cfg or RenderConfig()
    font_mgr = FontManager(assets_dir=assets_dir)
    pdf = fitz.open(source_pdf)

    if len(pdf) != len(doc.pages):
        raise ValueError(f"Page count mismatch: parsed={len(doc.pages)} pdf={len(pdf)}")

    for page_idx, page_model in enumerate(doc.pages):
        page = pdf[page_idx]

        # 1) Redact only blocks we will replace
        redacted_any = False
        for block in page_model.blocks:
            if block.type != "text":
                continue

            replace, target_text, _src = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            if not replace or not target_text:
                continue

            rect = fitz.Rect(
                block.bbox.x0 - cfg.redact_padding,
                block.bbox.y0 - cfg.redact_padding,
                block.bbox.x1 + cfg.redact_padding,
                block.bbox.y1 + cfg.redact_padding,
            )
            page.add_redact_annot(rect, fill=(1, 1, 1))
            redacted_any = True

        if redacted_any:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # 2) Insert translations with enhanced styling
        for block in page_model.blocks:
            if block.type != "text":
                continue

            replace, target_text, source_text = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            if not replace or not target_text:
                continue

            block_type, suggested_size, font_variant = classify_block_type(block)

            # Base font from the original block
            base_font = "DejaVuSans"
            if block.lines and block.lines[0].spans:
                base_font = block.lines[0].spans[0].style.font or base_font

            # Provide style hints to FontManager
            bf_low = base_font.lower()
            if font_variant == "Bold" and "bold" not in bf_low:
                base_font = base_font + " Bold"
                bf_low = base_font.lower()
            if font_variant == "Italic" and ("italic" not in bf_low and "oblique" not in bf_low):
                base_font = base_font + " Italic"

            # Preserve bullet character (prepend if translation dropped it)
            if block_type == "bullet":
                src_first = source_text.strip()[:1]
                if src_first in {"•", "-", "*", "·", "▪", "▫"}:
                    if not target_text.strip().startswith(src_first):
                        target_text = f"{src_first} {target_text.strip()}"

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
                base_size=suggested_size,
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
                colors = {
                    "title": (1, 0, 0),
                    "header": (0, 0, 1),
                    "bold": (0, 1, 0),
                    "italic": (1, 0, 1),
                    "bullet": (1, 1, 0),
                    "normal": (0.5, 0.5, 0.5),
                }
                page.draw_rect(rect, color=colors.get(block_type, (0, 0, 0)), width=0.5)

    pdf.save(output_pdf)
    pdf.close()
    logger.info("Enhanced rendering complete: %s", output_pdf)
