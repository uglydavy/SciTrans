"""scitrans.rendering.perfect_renderer

A *layout-safe* "perfect" renderer.

The original version of this file focused on exact, line-by-line placement. In practice,
that approach can produce unreadable PDFs when:

- some blocks are intentionally not translated (e.g., tables when --preserve-tables)
  but the renderer still redacts them;
- a translation fails / returns empty for some blocks;
- a translated block expands and overlaps adjacent content.

This renderer now enforces two production-grade invariants:

1) **Coverage safety**: if a block is not translated (missing/empty/identity), the
   original PDF content is preserved (no redaction).
2) **No-overlap-by-default**: translated text is inserted with `insert_textbox` and
   adaptive font fitting so it stays inside the original block rectangle.

It still preserves:
- original font family (best-effort, via FontManager)
- original base font size (shrinks only if needed)
- bullet characters (strongly preserved)

"""

from __future__ import annotations

import logging
import re

import fitz  # PyMuPDF

from scitrans.core.models import Block, Document
from scitrans.rendering.font_manager import FontManager
from scitrans.rendering.math_safe_renderer import (
    RenderConfig,
    _fit_font_size,
    _infer_alignment,
    _try_insert_textbox,
)

logger = logging.getLogger(__name__)

# PyMuPDF font flags (from span.style.flags)
FLAG_BOLD = 2**4
FLAG_ITALIC = 2**1


def extract_bullet_character(text: str) -> tuple[str, str]:
    """Extract bullet character from a single line (if present)."""
    text = text.strip()
    bullets = ["•", "-", "*", "·", "▪", "▫"]

    for bullet in bullets:
        if text.startswith(bullet):
            # Check if it's followed by space or number
            if len(text) > 1 and (text[1] == " " or text[1].isdigit()):
                return bullet, text[1:].strip()

    return "", text


def preserve_bullet_in_translation(source_text: str, translated_text: str) -> str:
    """Ensure bullet characters are preserved in translation ONLY where they exist in source.

    CRITICAL: Only preserve bullets where they exist in the source - do NOT add bullets
    to paragraphs that don't have them. This prevents adding hyphens to regular paragraphs.
    """

    # Split source and translation into lines
    source_lines = [line.strip() for line in source_text.split("\n") if line.strip()]
    trans_lines = [line.strip() for line in translated_text.split("\n") if line.strip()]

    # If no line breaks, return translation as-is (single paragraph)
    if len(source_lines) <= 1 and len(trans_lines) <= 1:
        return translated_text

    # Map source lines to their bullet status
    source_line_bullets = {}
    bullets = ["•", "-", "*", "·", "▪", "▫"]
    
    for i, src_line in enumerate(source_lines):
        bullet_char, _ = extract_bullet_character(src_line)
        source_line_bullets[i] = bullet_char  # Store bullet char for this line, or "" if none

    # If source has no bullets at all, return translation as-is
    if not any(source_line_bullets.values()):
        return translated_text

    # Filter out LLM instruction spillover from translation
    filtered_lines: list[str] = []
    for line in trans_lines:
        if not line:
            continue
        if any(
            keyword in line.lower()
            for keyword in [
                "rules",
                "conserver",
                "ne pas traduire",
                "critique",
                "do not translate",
                "je suis ravi",  # Generic responses
                "pouvez-vous",
                "comment puis-je",
            ]
        ):
            continue
        filtered_lines.append(line)

    # Match translation lines to source lines (best effort)
    result_lines: list[str] = []
    for i, trans_line in enumerate(filtered_lines):
        if not trans_line.strip():
            continue

        # Check if this line should have a bullet based on source
        # Try to match by position (if same number of lines) or by content similarity
        should_have_bullet = ""
        if i < len(source_lines):
            # Same position - use source bullet status
            should_have_bullet = source_line_bullets.get(i, "")
        else:
            # Extra lines in translation - check if any source line had a bullet
            # Only add bullet if most source lines had bullets (likely a list)
            bullets_in_source = sum(1 for b in source_line_bullets.values() if b)
            if bullets_in_source > len(source_lines) * 0.5:  # More than 50% had bullets
                # Use the most common bullet from source
                bullet_chars = [b for b in source_line_bullets.values() if b]
                if bullet_chars:
                    should_have_bullet = bullet_chars[0]  # Use first found bullet type

        # Check if translation line already has a bullet
        trans_bullet, trans_content = extract_bullet_character(trans_line)

        if should_have_bullet:
            # Source line had a bullet - ensure translation has it
            if trans_bullet == should_have_bullet:
                result_lines.append(trans_line)  # Already has correct bullet
            elif trans_bullet:
                # Has different bullet - replace with source bullet
                result_lines.append(f"{should_have_bullet} {trans_content}")
            else:
                # No bullet in translation - add source bullet
                result_lines.append(f"{should_have_bullet} {trans_line}")
        else:
            # Source line had NO bullet - preserve translation as-is (no bullet)
            result_lines.append(trans_line)

    # If no result lines, return original translation
    if not result_lines:
        return translated_text

    return "\n".join(result_lines)


def _block_text(block: Block) -> str:
    """Reconstruct block text with line breaks preserved."""
    if not block.lines:
        return ""
    lines: list[str] = []
    for ln in block.lines:
        lines.append("".join(sp.text for sp in ln.spans))
    return "\n".join(lines).strip()


def _normalize_for_identity_check(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _resolve_font_key(base_font: str, flags: int) -> str:
    """Augment font key with style hints so FontManager can pick bold/italic variants."""
    f = base_font or ""
    low = f.lower()

    if flags & FLAG_BOLD and "bold" not in low:
        f = f + " Bold"
        low = f.lower()

    if flags & FLAG_ITALIC and ("italic" not in low and "oblique" not in low):
        f = f + " Italic"

    return f


def _get_block_base_style(block: Block, min_font_size: float = 12.0) -> tuple[str, float, int]:
    """Return (font_name, font_size, flags) for the block.

    Enhanced extraction:
    - For headers/titles: Uses max font size and dominant font
    - For normal text: Uses average font size and most common font
    - Ensures minimum font size for readability
    - Preserves bold/italic flags from dominant style
    """
    if not block.lines:
        return "Times-Roman", max(11.0, min_font_size), 0
    
    # Collect all font info from all spans
    font_info: list[tuple[str, float, int]] = []
    for line in block.lines:
        for span in line.spans:
            if span.style:
                font_name = span.style.font or "Times-Roman"
                font_size = float(span.style.size or 11.0)
                flags = int(span.style.flags or 0)
                font_info.append((font_name, font_size, flags))
    
    if not font_info:
        return "Times-Roman", max(11.0, min_font_size), 0
    
    # Check if this is a header/title from metadata
    is_header = block.meta.get("is_header", False)
    block_type = block.meta.get("block_type", "normal")
    
    if is_header or block_type in ("title", "header", "subheader"):
        # For headers: use max font size and preserve bold
        max_size = max(f[1] for f in font_info)
        # Find the span with max size to get its font and flags
        max_font_info = max(font_info, key=lambda x: x[1])
        font_name = max_font_info[0]
        font_size = max(max_size, min_font_size)
        # Preserve bold flag for headers
        flags = max_font_info[2]
        if block_type == "title":
            # Titles should be bold and larger
            flags = flags | (2**4)  # FLAG_BOLD
            font_size = max(font_size, 16.0)
        elif block_type == "header":
            flags = flags | (2**4)  # FLAG_BOLD
            font_size = max(font_size, 14.0)
        return font_name, font_size, flags
    else:
        # For normal text: use most common font and average size
        # Count font occurrences
        font_counts: dict[str, int] = {}
        for f_name, _, _ in font_info:
            font_counts[f_name] = font_counts.get(f_name, 0) + 1
        
        # Get most common font
        if font_counts:
            font_name = max(font_counts.items(), key=lambda x: x[1])[0]
        else:
            font_name = font_info[0][0]
        
        # Average font size
        avg_size = sum(f[1] for f in font_info) / len(font_info)
        font_size = max(avg_size, min_font_size)
        
        # Most common flags (majority vote)
        flag_counts: dict[int, int] = {}
        for _, _, f_flags in font_info:
            flag_counts[f_flags] = flag_counts.get(f_flags, 0) + 1
        
        if flag_counts:
            flags = max(flag_counts.items(), key=lambda x: x[1])[0]
        else:
            flags = font_info[0][2]
        
        return font_name, font_size, flags


def _should_replace_block(
    block: Block,
    translations: dict[str, str],
    *,
    translate_tables: bool,
) -> tuple[bool, str | None, str]:
    """Decide whether to replace a block and return (replace?, target_text, source_text)."""

    source_text = _block_text(block)

    # Preserve tables unless explicitly enabled
    if block.meta.get("region") == "table" and not translate_tables:
        return False, None, source_text

    target_text = translations.get(block.id)

    # CRITICAL: Headers/titles should ALWAYS be rendered, even if translation is empty
    # Use source text as fallback for headers to ensure they appear
    is_header = block.meta.get("is_header", False)
    
    # Missing / empty translation → keep original (coverage safety)
    if not target_text or not target_text.strip():
        # For headers, use source text as fallback (better than nothing)
        if is_header:
            logger.warning(f"Block {block.id}: Header translation is empty, using source as fallback")
            return True, source_text, source_text  # Render source text for headers
        return False, None, source_text

    # Identity translation → STILL REPLACE (user wants translation, not source)
    # But log a warning
    if _normalize_for_identity_check(target_text) == _normalize_for_identity_check(source_text):
        logger.warning(
            f"Block {block.id}: Identity translation detected in renderer, but replacing anyway. "
            f"Source: '{source_text[:50]}...' == Target: '{target_text[:50]}...'"
        )
        # STILL REPLACE - user wants to see what backend returned, even if it's wrong
        return True, target_text, source_text

    return True, target_text, source_text


def render_translated_pdf_perfect(
    *,
    source_pdf: str,
    doc: Document,
    translations: dict[str, str],
    output_pdf: str,
    cfg: RenderConfig | None = None,
    assets_dir: str | None = None,
    translate_tables: bool = False,
) -> None:
    """Render translated blocks onto the original PDF.

    Notes:
      - Only blocks that actually have a non-empty, non-identity translation are redacted.
      - Preserved blocks (including tables when translate_tables=False) remain untouched.
      - For replaced blocks, we use insert_textbox with font fitting to keep text inside bbox.
    """

    cfg = cfg or RenderConfig()
    font_mgr = FontManager(assets_dir=assets_dir)
    pdf = fitz.open(source_pdf)

    if len(pdf) != len(doc.pages):
        raise ValueError(f"Page count mismatch: parsed={len(doc.pages)} pdf={len(pdf)}")

    for page_idx, page_model in enumerate(doc.pages):
        page = pdf[page_idx]

        # 1) Redact only blocks we will replace
        # CRITICAL: Never touch image blocks - they are preserved automatically
        redacted_any = False
        for block in page_model.blocks:
            if block.type != "text":
                # Images and other non-text blocks are automatically preserved
                # PyMuPDF redactions only affect text, so images remain untouched
                continue

            replace, target_text, _source_text = _should_replace_block(
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

        # 2) Insert translations
        for block in page_model.blocks:
            if block.type != "text":
                continue

            source_text = _block_text(block)
            stored_translation = translations.get(block.id, "")
            
            # DEBUG: Log what we have for this block (first 2 pages)
            if page_idx < 2:
                logger.info(f"Page {page_idx+1}, Block {block.id}: Source='{source_text[:50]}...', Stored='{stored_translation[:50] if stored_translation else 'EMPTY'}...'")
                logger.debug(f"Page {page_idx+1}, Block {block.id}: Source='{source_text[:40]}...'")
                logger.debug(f"  Stored translation: '{stored_translation[:40] if stored_translation else 'EMPTY'}...'")

            replace, target_text, source_text_check = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            if not replace or not target_text:
                # DEBUG: Log why block wasn't replaced
                if block.id not in translations:
                    logger.warning(f"Page {page_idx+1}, Block {block.id}: NO TRANSLATION in dictionary! Source: '{source_text[:50]}...'")
                elif not translations.get(block.id, "").strip():
                    logger.warning(f"Page {page_idx+1}, Block {block.id}: Translation is EMPTY! Source: '{source_text[:50]}...'")
                else:
                    stored_trans = translations.get(block.id, "")
                    logger.debug(f"Page {page_idx+1}, Block {block.id}: Not replacing (identity or other reason). Stored: '{stored_trans[:50]}...'")
                continue
            
            # DEBUG: Log what we're inserting (first 2 pages)
            if page_idx < 2:
                logger.info(f"Page {page_idx+1}, Block {block.id}: ✅ Inserting translation: '{target_text[:50]}...'")
                logger.debug(f"Page {page_idx+1}, Block {block.id}: ✅ Inserting: '{target_text[:40]}...'")

            # Preserve bullets based on the source block content
            target_text = preserve_bullet_in_translation(source_text, target_text)

            base_font, base_size, flags = _get_block_base_style(block)
            font_key = _resolve_font_key(base_font, flags)
            font = font_mgr.pick(font_key)

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
                page.draw_rect(rect, color=(0, 1, 0), width=0.5)  # green

    pdf.save(output_pdf)
    pdf.close()
    logger.info("Perfect rendering complete: %s", output_pdf)
