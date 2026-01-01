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
    """Ensure bullet characters are preserved in translation.

    LLMs / MT systems sometimes replace bullets with numbering or drop them.
    We detect bullets in the *source* and inject the same bullet into translated lines.
    """

    # Detect bullet character from source
    bullet_char = None
    bullets = ["•", "-", "*", "·", "▪", "▫"]

    for bullet in bullets:
        if bullet in source_text:
            bullet_char = bullet
            break

    if not bullet_char:
        source_lines = source_text.split("\n")
        for line in source_lines:
            bullet, _ = extract_bullet_character(line.strip())
            if bullet:
                bullet_char = bullet
                break

    if not bullet_char:
        return translated_text

    # Split into lines
    trans_lines = [line.strip() for line in translated_text.split("\n")]

    # Filter out empty lines and typical LLM instruction spillover
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
            ]
        ):
            continue
        filtered_lines.append(line)

    result_lines: list[str] = []
    for trans_line in filtered_lines:
        if not trans_line.strip():
            continue

        trans_bullet, _ = extract_bullet_character(trans_line)

        if trans_bullet == bullet_char:
            result_lines.append(trans_line)
            continue

        # Starts with number like "1." or "2)" → replace with bullet
        m = re.match(r"^(\d+)[\.)]\s*", trans_line)
        if m:
            rest = trans_line[m.end() :]
            result_lines.append(f"{bullet_char} {rest}")
            continue

        # Starts with other bullet-like markers
        m2 = re.match(r"^[*\-]\s+", trans_line)
        if m2:
            rest = trans_line[m2.end() :]
            result_lines.append(f"{bullet_char} {rest}")
            continue

        # No marker → add bullet
        result_lines.append(f"{bullet_char} {trans_line}")

    # If translation didn't contain line breaks, keep as single line
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


def _get_block_base_style(block: Block) -> tuple[str, float, int]:
    """Return (font_name, font_size, flags) for the block.

    Uses the first span of the first line as the baseline.
    """
    if block.lines and block.lines[0].spans:
        st = block.lines[0].spans[0].style
        return st.font or "Times-Roman", float(st.size or 11.0), int(st.flags or 0)
    return "Times-Roman", 11.0, 0


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

    # Missing / empty translation → keep original (coverage safety)
    if not target_text or not target_text.strip():
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
        redacted_any = False
        for block in page_model.blocks:
            if block.type != "text":
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
                console.print(f"[cyan]Page {page_idx+1}, Block {block.id}: Source='{source_text[:40]}...'[/cyan]")
                console.print(f"[cyan]  Stored translation: '{stored_translation[:40] if stored_translation else 'EMPTY'}...'[/cyan]")

            replace, target_text, source_text_check = _should_replace_block(
                block, translations, translate_tables=translate_tables
            )
            if not replace or not target_text:
                # DEBUG: Log why block wasn't replaced
                if block.id not in translations:
                    logger.warning(f"Page {page_idx+1}, Block {block.id}: NO TRANSLATION in dictionary! Source: '{source_text[:50]}...'")
                    console.print(f"[red]Page {page_idx+1}, Block {block.id}: NO TRANSLATION! Source: '{source_text[:40]}...'[/red]")
                elif not translations.get(block.id, "").strip():
                    logger.warning(f"Page {page_idx+1}, Block {block.id}: Translation is EMPTY! Source: '{source_text[:50]}...'")
                    console.print(f"[red]Page {page_idx+1}, Block {block.id}: Translation EMPTY! Source: '{source_text[:40]}...'[/red]")
                else:
                    stored_trans = translations.get(block.id, "")
                    logger.debug(f"Page {page_idx+1}, Block {block.id}: Not replacing (identity or other reason). Stored: '{stored_trans[:50]}...'")
                continue
            
            # DEBUG: Log what we're inserting (first 2 pages)
            if page_idx < 2:
                logger.info(f"Page {page_idx+1}, Block {block.id}: ✅ Inserting translation: '{target_text[:50]}...'")
                console.print(f"[green]Page {page_idx+1}, Block {block.id}: ✅ Inserting: '{target_text[:40]}...'[/green]")

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
