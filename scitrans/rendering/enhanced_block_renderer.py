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

import re

from scitrans.core.models import Block, Document
from scitrans.rendering.math_safe_renderer import RenderConfig
from scitrans.rendering.perfect_renderer import render_translated_pdf_perfect


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
    """Legacy entrypoint retained for compatibility.

    Delegates to the primary renderer for best font/style fidelity.
    """
    render_translated_pdf_perfect(
        source_pdf=source_pdf,
        doc=doc,
        translations=translations,
        output_pdf=output_pdf,
        cfg=cfg,
        assets_dir=assets_dir,
        translate_tables=translate_tables,
    )
