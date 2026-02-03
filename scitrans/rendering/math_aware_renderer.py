"""PHASE 2: Math-aware rendering that preserves equation geometry.

Unlike math_safe_renderer.py (which redacts ALL text), this renderer:
1. Detects equation spans
2. Preserves equation geometry (doesn't redact)
3. Redacts only natural language spans
4. Renders translated text around equations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

from scitrans.core.models import Document
from scitrans.parsing.math_detection import is_equation_span, split_mixed_blocks
from scitrans.rendering.font_manager import FontManager
from scitrans.rendering.math_safe_renderer import (
    RenderConfig,
    _fit_font_size,
    _infer_alignment,
    _try_insert_textbox,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MathAwareRenderConfig(RenderConfig):
    """Extended config for math-aware rendering."""

    preserve_equation_spans: bool = True  # PHASE 2 feature
    translate_tables: bool = False  # PHASE 4: default preserve tables


def _union_rect(rects: list[fitz.Rect]) -> fitz.Rect | None:
    if not rects:
        return None
    r = fitz.Rect(rects[0])
    for rc in rects[1:]:
        r |= rc
    return r


def _split_table_line(text: str) -> list[str]:
    """Heuristic split of a table line into cells."""
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if parts:
            return parts
    if "\t" in text:
        parts = [p.strip() for p in text.split("\t") if p.strip()]
        if parts:
            return parts
    # Fallback: split on 2+ spaces
    import re

    parts = [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]
    if parts:
        return parts
    return [text.strip()]


def _render_table_block(
    page: fitz.Page,
    block,
    target_text: str,
    cfg: MathAwareRenderConfig,
    font_mgr: FontManager,
) -> None:
    """Render a table-like block with rudimentary per-cell layout."""
    # Redact the full table block first (simple, since we'll reinsert per line)
    rect_block = fitz.Rect(
        block.bbox.x0 - cfg.redact_padding,
        block.bbox.y0 - cfg.redact_padding,
        block.bbox.x1 + cfg.redact_padding,
        block.bbox.y1 + cfg.redact_padding,
    )
    page.add_redact_annot(rect_block, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Use lines from block to align rows; fall back to single line from target_text
    lines = block.lines if block.lines else []
    if not lines:
        lines = [type("Line", (), {"bbox": block.bbox, "spans": [], "text": target_text})]

    rows: list[tuple[fitz.Rect, list[str]]] = []
    target_lines = target_text.split("\n") if "\n" in target_text else [target_text]
    # align number of rows: zip lines with target_lines
    for idx, line in enumerate(lines):
        line_text = (
            "".join(sp.text for sp in line.spans)
            if getattr(line, "spans", None)
            else target_lines[min(idx, len(target_lines) - 1)]
        )
        cells = _split_table_line(line_text if idx >= len(target_lines) else target_lines[idx])
        rows.append((fitz.Rect(line.bbox.x0, line.bbox.y0, line.bbox.x1, line.bbox.y1), cells))

    for row_rect, cells in rows:
        n_cols = max(1, len(cells))
        col_width = row_rect.width / n_cols
        x_start = row_rect.x0
        for col_idx, cell_text in enumerate(cells):
            cell_rect = fitz.Rect(
                x_start + col_idx * col_width,
                row_rect.y0,
                x_start + (col_idx + 1) * col_width,
                row_rect.y1,
            )
            base_font = (
                block.lines[0].spans[0].style.font
                if block.lines and block.lines[0].spans
                else "DejaVuSans"
            )
            base_size = (
                block.lines[0].spans[0].style.size if block.lines and block.lines[0].spans else 11.0
            )
            fontname, fontfile = font_mgr.get_font_for_text(cell_text, base_font)
            align = _infer_alignment(
                page.rect.width, cell_rect.x0, cell_rect.x1, cfg.align_threshold
            )
            fontsize = _fit_font_size(
                page,
                cell_rect,
                cell_text,
                fontname=fontname,
                fontfile=fontfile,
                base_size=base_size,
                cfg=cfg,
                align=align,
            )
            _try_insert_textbox(
                page,
                cell_rect,
                cell_text,
                fontname=fontname,
                fontfile=fontfile,
                fontsize=fontsize,
                align=align,
                line_height=cfg.line_height,
            )


def render_translated_pdf_math_aware(
    *,
    source_pdf: str,
    doc: Document,
    translations: dict[str, str],
    output_pdf: str,
    cfg: MathAwareRenderConfig | None = None,
    assets_dir: str | None = None,
) -> None:
    """Render translated PDF with math-aware span-level preservation.

    PHASE 2: This renderer preserves equation spans geometrically while
    translating natural language spans.

    Process:
    1. Detect equation vs text spans
    2. Redact ONLY text spans
    3. Insert translations ONLY in text span regions
    4. Leave equation spans untouched (original rendering preserved)
    """
    cfg = cfg or MathAwareRenderConfig()
    font_mgr = FontManager(assets_dir=assets_dir)
    pdf = fitz.open(source_pdf)

    if len(pdf) != len(doc.pages):
        raise ValueError("Parsed document pages != PDF pages")

    for page_idx, page_model in enumerate(doc.pages):
        page = pdf[page_idx]

        # Process each block
        for block in page_model.blocks:
            if block.type != "text":
                continue

            # PHASE 4: Preserve tables unless translation explicitly enabled
            if block.meta.get("region") == "table":
                if not cfg.translate_tables:
                    continue
                # Table rendering path (per-cell heuristic)
                target_text = translations.get(block.id, "")
                if not target_text:
                    continue
                _render_table_block(page, block, target_text, cfg, font_mgr)
                continue

            # Get translation
            target_text = translations.get(block.id, "")
            if not target_text:
                continue

            if cfg.preserve_equation_spans:
                # PHASE 2: Split into text vs equation spans
                text_spans, equation_spans = split_mixed_blocks(block)

                if equation_spans:
                    logger.info(
                        f"Block {block.id}: preserving {len(equation_spans)} equation spans"
                    )

                # Redact only text spans
                for line in block.lines:
                    for span in line.spans:
                        if not is_equation_span(span):
                            # Redact this span (it's text)
                            rect = fitz.Rect(
                                span.bbox.x0 - cfg.redact_padding,
                                span.bbox.y0 - cfg.redact_padding,
                                span.bbox.x1 + cfg.redact_padding,
                                span.bbox.y1 + cfg.redact_padding,
                            )
                            page.add_redact_annot(rect, fill=(1, 1, 1))
                        # Equation spans: NOT redacted (preserved)

                # Apply redactions
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                # Span-level: insert translation within union of text spans to avoid equations
                text_rects = []
                for line in block.lines:
                    for span in line.spans:
                        if not is_equation_span(span):
                            text_rects.append(
                                fitz.Rect(
                                    span.bbox.x0 - cfg.redact_padding,
                                    span.bbox.y0 - cfg.redact_padding,
                                    span.bbox.x1 + cfg.redact_padding,
                                    span.bbox.y1 + cfg.redact_padding,
                                )
                            )
                text_union = _union_rect(text_rects)
                if equation_spans and text_union:
                    base_font = (
                        block.lines[0].spans[0].style.font
                        if block.lines and block.lines[0].spans
                        else "DejaVuSans"
                    )
                    base_size = (
                        block.lines[0].spans[0].style.size
                        if block.lines and block.lines[0].spans
                        else 11.0
                    )
                    fontname, fontfile = font_mgr.get_font_for_text(target_text, base_font)
                    align = _infer_alignment(
                        page.rect.width, block.bbox.x0, block.bbox.x1, cfg.align_threshold
                    )
                    fontsize = _fit_font_size(
                        page,
                        text_union,
                        target_text,
                        fontname=fontname,
                        fontfile=fontfile,
                        base_size=base_size,
                        cfg=cfg,
                        align=align,
                    )
                    _try_insert_textbox(
                        page,
                        text_union,
                        target_text,
                        fontname=fontname,
                        fontfile=fontfile,
                        fontsize=fontsize,
                        align=align,
                        line_height=cfg.line_height,
                    )
                    continue

            else:
                # PHASE 0/1: Redact entire block (old behavior)
                rect = fitz.Rect(
                    block.bbox.x0 - cfg.redact_padding,
                    block.bbox.y0 - cfg.redact_padding,
                    block.bbox.x1 + cfg.redact_padding,
                    block.bbox.y1 + cfg.redact_padding,
                )
                page.add_redact_annot(rect, fill=(1, 1, 1))

        # Apply all redactions for this page
        if not cfg.preserve_equation_spans:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # Insert translations (block-level for now)
        for block in page_model.blocks:
            if block.type != "text":
                continue

            if block.meta.get("region") == "table" and not cfg.translate_tables:
                continue

            target_text = translations.get(block.id, "")
            if not target_text:
                continue

            # Get baseline style
            base_font = "Times-Roman"
            base_size = 11.0
            if block.lines and block.lines[0].spans:
                # Use first TEXT span (skip equation spans)
                for span in block.lines[0].spans:
                    if not is_equation_span(span):
                        base_font = span.style.font
                        base_size = span.style.size
                        break

            font = font_mgr.pick_for_text(target_text, base_font)
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
                page.draw_rect(rect, color=(0, 0, 1), width=0.5)  # Blue for math-aware

    pdf.save(output_pdf)
    pdf.close()
