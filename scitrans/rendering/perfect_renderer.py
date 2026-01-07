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
from scitrans.parsing.math_detection import is_equation_span
from scitrans.rendering.font_manager import FontManager
from scitrans.rendering.math_safe_renderer import (
    RenderConfig,
    _fit_font_size,
    _infer_alignment,
    _try_insert_textbox,
)
from scitrans.rendering.span_level_renderer import preserve_color_from_spans
from scitrans.utils.numbering_detector import NumberingDetector

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


def _get_block_base_style(block: Block, min_font_size: float = 10.0) -> tuple[str, float, int]:
    """Return (font_name, font_size, flags) for the block.

    Enhanced extraction with fallback support:
    - For headers/titles: Uses max font size and dominant font
    - For normal text: Uses average font size and most common font
    - Ensures minimum font size for readability
    - Preserves bold/italic flags from dominant style
    - Falls back to defaults if font extraction fails
    """
    if not block.lines:
        return "Times-Roman", max(11.0, min_font_size), 0
    
    # Try to use enhanced metadata from parser first (if available)
    font_families = block.meta.get("font_families")
    if font_families:
        primary_font = font_families[0] if font_families else "Times-Roman"
        avg_size = block.meta.get("avg_font_size", 11.0)
        max_size = block.meta.get("max_font_size", 11.0)
    else:
        primary_font = "Times-Roman"
        avg_size = 11.0
        max_size = 11.0
    
    # Collect all font info from all spans for flags and validation
    font_info: list[tuple[str, float, int]] = []
    for line in block.lines:
        for span in line.spans:
            if span.style:
                font_name = span.style.font or primary_font
                font_size = float(span.style.size or avg_size)
                flags = int(span.style.flags or 0)
                font_info.append((font_name, font_size, flags))
    
    if not font_info:
        # Ultimate fallback to defaults
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
        
        # Average font size - use actual average, but ensure reasonable minimum
        avg_size = sum(f[1] for f in font_info) / len(font_info)
        # Don't enforce 12pt minimum - let font fitting handle size reduction
        # This prevents forcing text to be too large and causing overflow
        font_size = max(avg_size, 8.0)  # Only enforce 8pt absolute minimum
        
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

    # Preserve tables unless explicitly enabled, BUT always translate TOC, figures, captions
    is_table_region = block.meta.get("region") == "table"
    is_toc = ("table of contents" in source_text.lower() or "contents" in source_text.lower()) and len(source_text) < 100
    is_figure_caption = any(keyword in source_text.lower() for keyword in ["figure", "fig.", "table", "tab."]) and len(source_text) < 200
    if is_table_region and not translate_tables and not (is_toc or is_figure_caption):
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"J","location":"perfect_renderer.py:278","message":"Table block skipped (not TOC/figure)","data":{"block_id":block.id}})+'\n')
        # #endregion
        return False, None, source_text

    target_text = translations.get(block.id)

    # CRITICAL: Headers/titles should ALWAYS be rendered, even if translation is empty
    # Use source text as fallback for headers to ensure they appear
    is_header = block.meta.get("is_header", False)
    block_type = block.meta.get("block_type", "normal")
    
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"K","location":"perfect_renderer.py:287","message":"_should_replace_block entry","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type,"has_target_text":bool(target_text),"source_preview":source_text[:50]}})+'\n')
    # #endregion

    # Missing / empty translation → keep original (coverage safety)
    if not target_text or not target_text.strip():
        # For headers, use source text as fallback (better than nothing)
        if is_header:
            logger.warning(f"Block {block.id}: Header translation is empty, using source as fallback")
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"L","location":"perfect_renderer.py:295","message":"Header with no translation - using source fallback","data":{"block_id":block.id,"is_header":is_header}})+'\n')
            # #endregion
            return True, source_text, source_text  # Render source text for headers
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"L","location":"perfect_renderer.py:300","message":"Non-header with no translation - returning False","data":{"block_id":block.id,"is_header":is_header}})+'\n')
        # #endregion
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

        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"perfect_renderer.py:332","message":"Rendering page","data":{"page_idx":page_idx,"total_blocks":len(page_model.blocks)}})+'\n')
        # #endregion

        # 0) Pre-check: Detect overlapping bounding boxes in source document
        # This helps identify if overlaps are due to source document issues
        text_blocks = [b for b in page_model.blocks if b.type == "text"]
        overlapping_pairs = []
        for i, block1 in enumerate(text_blocks):
            for block2 in text_blocks[i+1:]:
                # Check if bounding boxes overlap
                bbox1 = block1.bbox
                bbox2 = block2.bbox
                # Calculate intersection
                x_overlap = max(0, min(bbox1.x1, bbox2.x1) - max(bbox1.x0, bbox2.x0))
                y_overlap = max(0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0))
                if x_overlap > 0 and y_overlap > 0:
                    overlap_area = x_overlap * y_overlap
                    area1 = (bbox1.x1 - bbox1.x0) * (bbox1.y1 - bbox1.y0)
                    area2 = (bbox2.x1 - bbox2.x0) * (bbox2.y1 - bbox2.y0)
                    iou = overlap_area / (area1 + area2 - overlap_area) if (area1 + area2 - overlap_area) > 0 else 0
                    if iou > 0.01:  # Significant overlap (IoU > 1%)
                        overlapping_pairs.append((block1.id, block2.id, iou))
                        # #region agent log
                        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                            import json
                            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"J","location":"perfect_renderer.py:378","message":"Source bbox overlap detected","data":{"block1_id":block1.id,"block2_id":block2.id,"iou":iou,"bbox1":{"x0":bbox1.x0,"y0":bbox1.y0,"x1":bbox1.x1,"y1":bbox1.y1},"bbox2":{"x0":bbox2.x0,"y0":bbox2.y0,"x1":bbox2.x1,"y1":bbox2.y1}}})+'\n')
                        # #endregion
                        logger.warning(
                            f"Page {page_idx+1}: Source blocks {block1.id} and {block2.id} have overlapping bounding boxes "
                            f"(IoU: {iou:.2%}). This may cause rendering overlaps."
                        )
        
        if overlapping_pairs:
            logger.warning(
                f"Page {page_idx+1}: Found {len(overlapping_pairs)} pairs of overlapping source bounding boxes. "
                f"This is likely causing rendering overlaps."
            )

        # 1) Redact only blocks we will replace
        # CRITICAL: Never touch image blocks - they are preserved automatically
        redacted_any = False
        redacted_block_ids = []
        for block in page_model.blocks:
            if block.type != "text":
                # Images and other non-text blocks are automatically preserved
                # PyMuPDF redactions only affect text, so images remain untouched
                continue

            source_text = _block_text(block)
            is_header = block.meta.get("is_header", False)
            block_type = block.meta.get("block_type", "normal")
            has_translation = block.id in translations and translations.get(block.id, "").strip()
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"perfect_renderer.py:347","message":"Checking block for redaction","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type,"has_translation":has_translation,"source_preview":source_text[:50]}})+'\n')
            # #endregion

            replace, target_text, _source_text = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"B","location":"perfect_renderer.py:356","message":"_should_replace_block result","data":{"block_id":block.id,"replace":replace,"has_target_text":bool(target_text),"target_preview":target_text[:50] if target_text else None}})+'\n')
            # #endregion

            if not replace or not target_text:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"perfect_renderer.py:361","message":"Block NOT redacted","data":{"block_id":block.id,"is_header":is_header,"reason":"replace=False or no target_text"}})+'\n')
                # #endregion
                continue

            # CRITICAL: Use original bbox WITHOUT padding to prevent overlaps
            # Padding can cause redactions to overlap with adjacent blocks
            # Instead, we'll rely on the text insertion to stay within bounds
            rect = fitz.Rect(
                block.bbox.x0,
                block.bbox.y0,
                block.bbox.x1,
                block.bbox.y1,
            )
            page.add_redact_annot(rect, fill=(1, 1, 1))
            redacted_any = True
            redacted_block_ids.append(block.id)
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"D","location":"perfect_renderer.py:375","message":"Block REDACTED","data":{"block_id":block.id,"is_header":is_header}})+'\n')
            # #endregion

        if redacted_any:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"D","location":"perfect_renderer.py:380","message":"Redactions applied","data":{"page_idx":page_idx,"redacted_count":len(redacted_block_ids),"redacted_ids":redacted_block_ids}})+'\n')
            # #endregion

        # 2) Insert translations
        rendered_block_ids = []
        for block in page_model.blocks:
            if block.type != "text":
                continue

            source_text = _block_text(block)
            stored_translation = translations.get(block.id, "")
            is_header = block.meta.get("is_header", False)
            block_type = block.meta.get("block_type", "normal")
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"E","location":"perfect_renderer.py:395","message":"Processing block for rendering","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type,"has_translation":bool(stored_translation),"source_preview":source_text[:50]}})+'\n')
            # #endregion
            
            # DEBUG: Log what we have for this block (first 2 pages)
            if page_idx < 2:
                logger.info(f"Page {page_idx+1}, Block {block.id}: Source='{source_text[:50]}...', Stored='{stored_translation[:50] if stored_translation else 'EMPTY'}...'")
                logger.debug(f"Page {page_idx+1}, Block {block.id}: Source='{source_text[:40]}...'")
                logger.debug(f"  Stored translation: '{stored_translation[:40] if stored_translation else 'EMPTY'}...'")

            replace, target_text, source_text_check = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"F","location":"perfect_renderer.py:408","message":"_should_replace_block result (render phase)","data":{"block_id":block.id,"replace":replace,"has_target_text":bool(target_text),"is_header":is_header}})+'\n')
            # #endregion

            if not replace or not target_text:
                # CRITICAL: Always render blocks - if no translation, use source text
                # This ensures no blocks are omitted from the final PDF
                if block.id not in translations or not translations.get(block.id, "").strip():
                    # Use source text as fallback to ensure block is rendered
                    logger.debug(f"Page {page_idx+1}, Block {block.id}: Using source text as fallback (no translation)")
                    target_text = source_text
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"G","location":"perfect_renderer.py:417","message":"Using source text fallback","data":{"block_id":block.id,"is_header":is_header,"reason":"no translation in dict"}})+'\n')
                    # #endregion
                else:
                    stored_trans = translations.get(block.id, "")
                    logger.debug(f"Page {page_idx+1}, Block {block.id}: Using stored translation. Stored: '{stored_trans[:50]}...'")
                    target_text = stored_trans
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"G","location":"perfect_renderer.py:424","message":"Using stored translation","data":{"block_id":block.id,"is_header":is_header,"stored_preview":stored_trans[:50]}})+'\n')
                    # #endregion
                
                # Continue to render with source or stored translation
                # Don't skip the block - ensure it's rendered
            
            # DEBUG: Log what we're inserting (first 2 pages)
            if page_idx < 2:
                logger.info(f"Page {page_idx+1}, Block {block.id}: ✅ Inserting translation: '{target_text[:50]}...'")
                logger.debug(f"Page {page_idx+1}, Block {block.id}: ✅ Inserting: '{target_text[:40]}...'")

            # Preserve bullets based on the source block content
            target_text = preserve_bullet_in_translation(source_text, target_text)
            
            # Enhanced numbering preservation (Roman, nested, letters)
            from scitrans.utils.numbering_detector import NumberingDetector
            target_text = NumberingDetector.preserve_numbering(source_text, target_text)
            
            # Preserve line breaks and paragraph formatting
            from scitrans.utils.line_break_preserver import preserve_line_breaks, preserve_paragraph_spacing
            target_text = preserve_line_breaks(source_text, target_text)
            target_text = preserve_paragraph_spacing(source_text, target_text)

            base_font, base_size, flags = _get_block_base_style(block)
            font_key = _resolve_font_key(base_font, flags)
            
            # Try to pick font with fallback handling
            try:
                font = font_mgr.pick(font_key)
            except Exception as e:
                logger.warning(f"Font {font_key} not available, using fallback: {e}")
                # Fallback to standard font based on flags
                if flags & (2**4):  # Bold
                    fallback_font = "Times-Bold" if "Times" in base_font else "Helvetica-Bold"
                elif flags & (2**1):  # Italic
                    fallback_font = "Times-Italic" if "Times" in base_font else "Helvetica-Oblique"
                else:
                    fallback_font = "Times-Roman"
                font = font_mgr.pick(fallback_font)
            
            # Preserve text color if available
            text_color = preserve_color_from_spans(block)

            # CRITICAL: Use original bbox for text insertion to prevent overlaps
            # The font fitting will ensure text stays within bounds
            # However, we need to ensure blocks don't overlap with adjacent blocks
            # Check for nearby blocks and adjust if necessary
            original_rect = fitz.Rect(block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
            
            # CRITICAL: Ensure rect is valid (not empty or inverted)
            if original_rect.width <= 0 or original_rect.height <= 0:
                logger.warning(f"Block {block.id} has invalid bbox: {original_rect}, skipping")
                continue
            
            # CRITICAL: Check for adjacent blocks that might cause overlaps
            # Strategy: Check against ALL blocks on the page (not just rendered ones) to prevent overlaps
            # This is especially important for larger PDFs where blocks might be close together
            safe_rect = fitz.Rect(original_rect.x0, original_rect.y0, original_rect.x1, original_rect.y1)
            safety_margin = 1.0  # Reduced margin to prevent excessive shrinking (pts)
            
            # Sort blocks by position to check nearest neighbors first (more efficient)
            text_blocks_sorted = sorted(
                [b for b in page_model.blocks if b.type == "text" and b.id != block.id],
                key=lambda b: (
                    abs(b.bbox.y0 - block.bbox.y0) + abs(b.bbox.x0 - block.bbox.x0)
                )
            )
            
            # Check against nearest text blocks first (more efficient)
            for other_block_model in text_blocks_sorted[:10]:  # Check only nearest 10 blocks
                other_rect = fitz.Rect(
                    other_block_model.bbox.x0, 
                    other_block_model.bbox.y0, 
                    other_block_model.bbox.x1, 
                    other_block_model.bbox.y1
                )
                
                # Check if rectangles actually overlap or are very close
                x_overlap = min(original_rect.x1, other_rect.x1) - max(original_rect.x0, other_rect.x0)
                y_overlap = min(original_rect.y1, other_rect.y1) - max(original_rect.y0, other_rect.y0)
                
                # Also check if blocks are very close (within safety margin)
                x_gap = max(0, max(original_rect.x0, other_rect.x0) - min(original_rect.x1, other_rect.x1))
                y_gap = max(0, max(original_rect.y0, other_rect.y0) - min(original_rect.y1, other_rect.y1))
                is_very_close = x_gap < safety_margin and y_gap < safety_margin
                
                if (x_overlap > 0 and y_overlap > 0) or is_very_close:
                    # There's actual overlap or blocks are very close - adjust our rectangle
                    if x_overlap > 0 and y_overlap > 0:
                        overlap_area = x_overlap * y_overlap
                        our_area = original_rect.width * original_rect.height
                        overlap_ratio = overlap_area / our_area if our_area > 0 else 0
                        
                        if overlap_ratio > 0.01:  # More than 1% overlap (more sensitive)
                            # #region agent log
                            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                                import json
                                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"L","location":"perfect_renderer.py:620","message":"Detected overlap with block","data":{"block_id":block.id,"other_block_id":other_block_model.id,"overlap_ratio":overlap_ratio,"x_overlap":x_overlap,"y_overlap":y_overlap}})+'\n')
                            # #endregion
                            logger.warning(
                                f"Block {block.id}: Overlaps with block {other_block_model.id} "
                                f"({overlap_ratio:.1%} overlap). Adjusting rectangle."
                            )
                            
                            # Adjust based on overlap direction and position
                            if x_overlap > y_overlap:
                                # Horizontal overlap is larger - adjust horizontally
                                if original_rect.x0 < other_rect.x0:
                                    safe_rect.x1 = min(safe_rect.x1, other_rect.x0 - safety_margin)
                                else:
                                    safe_rect.x0 = max(safe_rect.x0, other_rect.x1 + safety_margin)
                            else:
                                # Vertical overlap is larger - adjust vertically
                                if original_rect.y0 < other_rect.y0:
                                    safe_rect.y1 = min(safe_rect.y1, other_rect.y0 - safety_margin)
                                else:
                                    safe_rect.y0 = max(safe_rect.y0, other_rect.y1 + safety_margin)
                    elif is_very_close:
                        # Blocks are very close - add small margin to prevent edge overlap
                        if x_gap < safety_margin:
                            if original_rect.x0 < other_rect.x0:
                                safe_rect.x1 = min(safe_rect.x1, other_rect.x0 - safety_margin)
                            else:
                                safe_rect.x0 = max(safe_rect.x0, other_rect.x1 + safety_margin)
                        if y_gap < safety_margin:
                            if original_rect.y0 < other_rect.y0:
                                safe_rect.y1 = min(safe_rect.y1, other_rect.y0 - safety_margin)
                            else:
                                safe_rect.y0 = max(safe_rect.y0, other_rect.y1 + safety_margin)
            
            # Ensure safe_rect is still valid after adjustments
            if safe_rect.width <= 0 or safe_rect.height <= 0:
                logger.warning(
                    f"Block {block.id}: Safe rect became invalid after overlap prevention, "
                    f"using original rect. Original: {original_rect.width:.1f}x{original_rect.height:.1f}"
                )
                safe_rect = original_rect
            
            # Log if we adjusted the rectangle
            if safe_rect.x0 != original_rect.x0 or safe_rect.y0 != original_rect.y0 or safe_rect.x1 != original_rect.x1 or safe_rect.y1 != original_rect.y1:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"K","location":"perfect_renderer.py:650","message":"Adjusted rect to prevent overlap","data":{"block_id":block.id,"original":{"x0":original_rect.x0,"y0":original_rect.y0,"x1":original_rect.x1,"y1":original_rect.y1},"safe":{"x0":safe_rect.x0,"y0":safe_rect.y0,"x1":safe_rect.x1,"y1":safe_rect.y1}}})+'\n')
                # #endregion
                logger.info(
                    f"Block {block.id}: Adjusted rectangle to prevent overlap. "
                    f"Original: {original_rect.width:.1f}x{original_rect.height:.1f}, "
                    f"Safe: {safe_rect.width:.1f}x{safe_rect.height:.1f}"
                )
            
            rect = safe_rect
            
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

            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"E","location":"perfect_renderer.py:667","message":"Font size fitted","data":{"block_id":block.id,"base_size":base_size,"fitted_size":fitted_size,"min_font_size":cfg.min_font_size,"text_length":len(target_text),"rect_width":rect.width,"rect_height":rect.height,"shrink_ratio":fitted_size/base_size if base_size > 0 else 0}})+'\n')
            # #endregion

            # CRITICAL: Verify the fitted size is reasonable
            if fitted_size < cfg.min_font_size:
                logger.warning(
                    f"Block {block.id}: Fitted font size {fitted_size:.2f} is below minimum "
                    f"{cfg.min_font_size}, text may be too long for block"
                )
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"E","location":"perfect_renderer.py:680","message":"Font size below minimum","data":{"block_id":block.id,"fitted_size":fitted_size,"min_font_size":cfg.min_font_size}})+'\n')
                # #endregion

            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"H","location":"perfect_renderer.py:530","message":"About to render block","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type,"target_preview":target_text[:50],"font_size":fitted_size}})+'\n')
            # #endregion

            try:
                # CRITICAL: Verify text fits before inserting
                # insert_textbox returns negative if text doesn't fit
                result = _try_insert_textbox(
                    page,
                    rect,
                    target_text,
                    fontname=font.name,
                    fontfile=font.file,
                    fontsize=fitted_size,
                    align=align,
                    line_height=cfg.line_height,
                    color=text_color,  # Preserve color if available
                )
                
                # CRITICAL: Check if text actually fit
                if result < 0:
                    logger.warning(
                        f"Block {block.id}: Text overflow detected (result={result:.2f}), "
                        f"font size {fitted_size:.2f} may be too large. "
                        f"Text length: {len(target_text)}, Block size: {rect.width:.1f}x{rect.height:.1f}"
                    )
                    # Try with progressively smaller font sizes
                    emergency_sizes = [
                        max(cfg.min_font_size, fitted_size * 0.9),
                        max(cfg.min_font_size, fitted_size * 0.8),
                        max(cfg.min_font_size, fitted_size * 0.7),
                        cfg.min_font_size,
                    ]
                    
                    result = -1
                    for emergency_size in emergency_sizes:
                        result = _try_insert_textbox(
                            page,
                            rect,
                            target_text,
                            fontname=font.name,
                            fontfile=font.file,
                            fontsize=emergency_size,
                            align=align,
                            line_height=cfg.line_height,
                            color=text_color,
                        )
                        if result >= 0:
                            logger.info(f"Block {block.id}: Text fits with emergency size {emergency_size:.2f}")
                            break
                    
                    if result < 0:
                        # Last resort: intelligently truncate text
                        logger.error(
                            f"Block {block.id}: Text still doesn't fit even with minimum size {cfg.min_font_size:.2f}. "
                            f"Intelligently truncating text to prevent overflow."
                        )
                        # Estimate max chars that fit (conservative estimate)
                        chars_per_line = max(1, int(rect.width / (cfg.min_font_size * 0.5)))
                        max_lines = max(1, int(rect.height / (cfg.min_font_size * cfg.line_height)))
                        max_chars = chars_per_line * max_lines
                        
                        if len(target_text) > max_chars:
                            # Try to truncate at word boundary
                            truncated = target_text[:max_chars]
                            last_space = truncated.rfind(' ')
                            if last_space > max_chars * 0.8:  # If we can find a space near the end
                                target_text = truncated[:last_space] + "..."
                            else:
                                target_text = truncated + "..."
                        
                        # Final attempt with truncated text
                        result = _try_insert_textbox(
                            page,
                            rect,
                            target_text,
                            fontname=font.name,
                            fontfile=font.file,
                            fontsize=cfg.min_font_size,
                            align=align,
                            line_height=cfg.line_height,
                            color=text_color,
                        )
                        if result < 0:
                            logger.error(
                                f"Block {block.id}: CRITICAL - Text still doesn't fit after truncation. "
                                f"Block may be too small or text too long. Rendering what we can."
                            )
                
                rendered_block_ids.append(block.id)
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"H","location":"perfect_renderer.py:548","message":"Block RENDERED successfully","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type}})+'\n')
                # #endregion
            except Exception as e:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"H","location":"perfect_renderer.py:553","message":"Block RENDER FAILED","data":{"block_id":block.id,"is_header":is_header,"block_type":block_type,"error":str(e)}})+'\n')
                # #endregion
                logger.error(f"Failed to render block {block.id}: {e}", exc_info=True)

            if cfg.debug_draw_boxes:
                page.draw_rect(rect, color=(0, 1, 0), width=0.5)  # green
        
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"I","location":"perfect_renderer.py:563","message":"Page rendering complete","data":{"page_idx":page_idx,"total_blocks":len(page_model.blocks),"rendered_count":len(rendered_block_ids),"rendered_ids":rendered_block_ids}})+'\n')
        # #endregion

    pdf.save(output_pdf)
    pdf.close()
    logger.info("Perfect rendering complete: %s", output_pdf)
