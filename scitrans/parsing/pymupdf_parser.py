from __future__ import annotations

import hashlib
import statistics
from collections import Counter

import fitz  # PyMuPDF

from scitrans.core.models import BBox, Block, Document, Line, Page, Span, SpanStyle
from scitrans.parsing.layout import (
    classify_block_type,
    detect_headers_footers,
    detect_tables_and_captions,
    merge_paragraph_blocks,
    sort_blocks_multicolumn,
)
from scitrans.parsing.enhanced_font_extractor import extract_enhanced_font_from_span


def _bbox_from_tuple(t: tuple[float, float, float, float]) -> BBox:
    x0, y0, x1, y1 = t
    return BBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))


def _deterministic_block_id(page_index: int, bbox: BBox, text_content: str) -> str:
    """Generate a deterministic block ID based on page, bbox, and text content.

    This ensures stable IDs across runs for caching and repair workflows.
    """
    # Round bbox to avoid floating-point instability
    bbox_str = f"{page_index}_{round(bbox.x0, 2)}_{round(bbox.y0, 2)}_{round(bbox.x1, 2)}_{round(bbox.y1, 2)}"
    # Include first 50 chars of text for uniqueness
    text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()[:8]
    combined = f"{bbox_str}_{text_hash}"
    block_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
    return f"b_{page_index}_{block_hash}"


def _text_from_span(span: dict) -> str:
    chars = span.get("chars") or []
    if chars:
        return "".join(ch.get("c", "") for ch in chars)
    return span.get("text", "") or ""


def _detect_script_category(text: str) -> str:
    if not text:
        return "latin"
    has_cjk = any(
        0x4E00 <= ord(c) <= 0x9FFF
        or 0x3040 <= ord(c) <= 0x30FF
        or 0xAC00 <= ord(c) <= 0xD7AF
        for c in text
    )
    if has_cjk:
        return "cjk"
    has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in text)
    if has_cyrillic:
        return "cyrillic"
    return "latin"


def _detect_and_tag_headers_titles(blocks: list[Block], page_index_map: dict[str, int] | None = None) -> None:
    """Detect headers and titles based on font size, styling, and text patterns.
    
    Tags blocks with:
    - "block_type": "title" (very large font, typically at top)
    - "block_type": "header" (large font, bold, section headers)
    - "block_type": "subheader" (medium font, bold)
    
    Args:
        blocks: List of blocks to tag
        page_index_map: Optional dict mapping block.id to page index (0-based)
    """
    import re
    
    for block in blocks:
        if block.type != "text" or not block.lines:
            continue
        
        # Get dominant font size and style from all spans
        font_sizes = []
        bold_count = 0
        total_spans = 0
        
        for line in block.lines:
            for span in line.spans:
                if span.style.size:
                    font_sizes.append(float(span.style.size))
                if span.style.flags and (span.style.flags & (2**4)):  # FLAG_BOLD
                    bold_count += 1
                total_spans += 1
        
        if not font_sizes:
            continue
        
        avg_font_size = sum(font_sizes) / len(font_sizes)
        max_font_size = max(font_sizes)
        is_bold = bold_count > total_spans * 0.5  # More than 50% bold
        
        # Get block text
        block_text = ""
        for line in block.lines:
            for span in line.spans:
                block_text += span.text
        
        block_text = block_text.strip()
        
        # Pattern matching for headers - improved patterns
        # Match: "1. ", "2)", "1)", "Section 1:", "Section 1", "Chapter 2", etc.
        is_numbered_section = bool(re.match(r'^\d+[\.\)]\s+', block_text))  # "1. ", "2) "
        is_section_header = bool(re.match(r'^(Section|Chapter|Part)\s+\d+[:]?\s*', block_text, re.IGNORECASE))
        # Match numbered lists: "1.", "2.", "3." at start
        is_numbered_list = bool(re.match(r'^\d+\.\s+[A-Z]', block_text))  # "1. Item", "2. Item"
        # Match roman numerals: "I.", "II.", "III."
        is_roman_numeral = bool(re.match(r'^[IVX]+\.\s+', block_text, re.IGNORECASE))
        is_short_uppercase = len(block_text) < 50 and block_text.isupper() and len(block_text.split()) <= 5
        
        # Classify block type - IMPROVED: More lenient title detection
        # Title: Very large font OR first page + large font OR short text + large font
        is_first_page = False
        if page_index_map and block.id in page_index_map:
            is_first_page = (page_index_map[block.id] == 0)
        
        # IMPROVED: More lenient detection for headers/titles, especially for mixed-language documents
        # Check script category
        script_category = block.meta.get("script_category") or _detect_script_category(block_text)
        has_cjk = script_category == "cjk"
        
        is_title_candidate = (
            (max_font_size >= 16 and len(block_text) < 120)
            or (max_font_size >= 14 and is_bold and len(block_text) < 120)
            or (is_first_page and max_font_size >= 14 and len(block_text) < 100)
            or (has_cjk and max_font_size >= 12 and len(block_text) < 40)
        )
        
        if is_title_candidate:
            # Very large font = title
            block.meta["block_type"] = "title"
            block.meta["is_header"] = True
        elif max_font_size >= 14 or (max_font_size >= 12 and is_bold and (is_numbered_section or is_section_header)):
            # Large font or bold numbered section = header
            block.meta["block_type"] = "header"
            block.meta["is_header"] = True
        elif max_font_size >= 12 and is_bold:
            # Medium bold = subheader
            block.meta["block_type"] = "subheader"
            block.meta["is_header"] = True
        elif is_numbered_section or is_section_header or is_numbered_list or is_roman_numeral or is_short_uppercase:
            # Pattern-based detection
            block.meta["block_type"] = "header"
            block.meta["is_header"] = True
            # Tag numbering type for preservation
            if is_numbered_section or is_section_header:
                block.meta["has_section_number"] = True
            if is_numbered_list:
                block.meta["has_list_number"] = True
            if is_roman_numeral:
                block.meta["has_roman_numeral"] = True
        elif has_cjk and max_font_size >= 10:
            # CJK text with reasonable font size - likely a header
            block.meta["block_type"] = "header"
            block.meta["is_header"] = True
        
        # Store font info for rendering
        if font_sizes:
            block.meta["avg_font_size"] = avg_font_size
            block.meta["max_font_size"] = max_font_size
            block.meta["is_bold"] = is_bold
        
        # PHASE 4.2: Add context-aware metadata tagging
        # Use enhanced classification if not already classified
        if "block_type" not in block.meta:
            block.meta["block_type"] = classify_block_type(block)
        
        # Add additional metadata for translation pipeline (use block_text not text)
        block.meta["has_section_number"] = bool(re.match(r'^(Section|Chapter|Part)\s+\d+', block_text, re.IGNORECASE))
        block.meta["is_short"] = len(block_text) < 100
        
        # Font size category for consistent rendering
        if avg_font_size >= 14:
            block.meta["font_size_category"] = "large"
        elif avg_font_size >= 11:
            block.meta["font_size_category"] = "medium"
        else:
            block.meta["font_size_category"] = "small"


def _sort_blocks_by_reading_order(blocks: list[Block]) -> list[Block]:
    """Sort blocks by reading order: top-to-bottom, then left-to-right.

    This ensures consistent block ordering across runs.
    """

    def sort_key(block: Block) -> tuple[float, float]:
        # Primary: y0 (top-to-bottom)
        # Secondary: x0 (left-to-right)
        return (round(block.bbox.y0, 2), round(block.bbox.x0, 2))

    return sorted(blocks, key=sort_key)


def parse_pdf(path: str, use_layout_intelligence: bool = True) -> Document:
    """Parse a PDF into a stable page/block/line/span representation.

    Args:
        path: PDF file path
        use_layout_intelligence: Enable PHASE 1 improvements (column detection, paragraph merging)

    Notes:
      - Uses PyMuPDF `page.get_text("rawdict")` for maximum detail.
      - PHASE 1/3: Multi-column reading order, paragraph merging, table/caption tagging
      - Keeps image blocks as `type="image"` without text.
    """
    doc = fitz.open(path)
    pages: list[Page] = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        raw = page.get_text("rawdict")
        blocks: list[Block] = []

        for b in raw.get("blocks", []):
            btype = b.get("type", 0)
            bbox = _bbox_from_tuple(tuple(b.get("bbox", (0, 0, 0, 0))))

            if btype == 1:
                # Image block: use bbox + page index for ID
                block_id = _deterministic_block_id(page_index, bbox, f"image_{bbox.x0}_{bbox.y0}")
                blocks.append(
                    Block(
                        id=block_id,
                        type="image",
                        bbox=bbox,
                        lines=[],
                        meta={"raw_type": 1},
                    )
                )
                continue

            # text block
            lines: list[Line] = []
            text_parts: list[str] = []
            raw_font_names: list[str] = []
            normalized_fonts: list[str] = []
            font_weights: list[str] = []
            font_styles: list[str] = []
            font_flags: list[int] = []
            font_colors: list[int] = []
            for ln in b.get("lines", []):
                line_bbox = _bbox_from_tuple(
                    tuple(ln.get("bbox", (bbox.x0, bbox.y0, bbox.x1, bbox.y1)))
                )
                spans: list[Span] = []
                for sp in ln.get("spans", []):
                    sp_text = _text_from_span(sp)
                    text_parts.append(sp_text)
                    sp_bbox = _bbox_from_tuple(
                        tuple(
                            sp.get("bbox", (line_bbox.x0, line_bbox.y0, line_bbox.x1, line_bbox.y1))
                        )
                    )
                    # Use enhanced font extraction for better accuracy
                    try:
                        enhanced_font = extract_enhanced_font_from_span(sp)
                        style = SpanStyle(
                            font=enhanced_font.normalized_name,
                            size=enhanced_font.size,
                            flags=enhanced_font.flags,
                            color=enhanced_font._color_to_int() if enhanced_font.color else None,
                        )
                        raw_font_names.append(enhanced_font.raw_name)
                        normalized_fonts.append(enhanced_font.normalized_name)
                        font_weights.append(enhanced_font.weight)
                        font_styles.append(enhanced_font.style)
                    except Exception as e:
                        logger.debug(f"Enhanced font extraction failed for span, using basic extraction: {e}")
                        # Fallback to basic extraction
                        style = SpanStyle(
                            font=str(sp.get("font", "Times-Roman")),
                            size=float(sp.get("size", 11.0)),
                            flags=int(sp.get("flags", 0)),
                            color=sp.get("color"),
                        )
                    if style.flags:
                        font_flags.append(int(style.flags))
                    if style.color is not None:
                        font_colors.append(int(style.color))

                    spans.append(Span(text=sp_text, bbox=sp_bbox, style=style))
                lines.append(Line(spans=spans, bbox=line_bbox))

            # Generate deterministic ID from page, bbox, and text content
            text_content = "".join(text_parts)
            block_id = _deterministic_block_id(page_index, bbox, text_content)
            
            # Store enhanced font metadata in block.meta for rendering
            # Collect all unique font families, sizes, and styles from spans
            font_families = set()
            font_sizes = []
            for line in lines:
                for span in line.spans:
                    if span.style:
                        font_families.add(span.style.font)
                        if span.style.size:
                            font_sizes.append(float(span.style.size))
            
            median_font_size = (
                statistics.median(font_sizes) if font_sizes else 11.0
            )
            dominant_font = (
                Counter(normalized_fonts).most_common(1)[0][0]
                if normalized_fonts
                else (list(font_families)[0] if font_families else "Times-Roman")
            )
            dominant_color = (
                Counter(font_colors).most_common(1)[0][0] if font_colors else None
            )
            script_category = _detect_script_category(text_content)

            block_meta = {
                "raw_type": 0,
                "font_families": list(font_families) if font_families else ["Times-Roman"],
                "avg_font_size": sum(font_sizes) / len(font_sizes) if font_sizes else 11.0,
                "min_font_size": min(font_sizes) if font_sizes else 11.0,
                "max_font_size": max(font_sizes) if font_sizes else 11.0,
                "median_font_size": median_font_size,
                "dominant_font": dominant_font,
                "dominant_color": dominant_color,
                "script_category": script_category,
                "font_weights": list(set(font_weights)) if font_weights else [],
                "font_styles": list(set(font_styles)) if font_styles else [],
                "font_flags": font_flags,
                "raw_font_names": list(set(raw_font_names)) if raw_font_names else [],
                "normalized_fonts": list(set(normalized_fonts)) if normalized_fonts else [],
            }
            
            blocks.append(
                Block(
                    id=block_id,
                    type="text",
                    bbox=bbox,
                    lines=lines,
                    meta=block_meta,
                )
            )

        # PHASE 1/3: Layout intelligence
        if use_layout_intelligence:
            # Multi-column reading order
            blocks = sort_blocks_multicolumn(blocks, page.rect.width)

            # Detect headers/footers (optional: exclude from translation)
            headers, body_blocks, footers = detect_headers_footers(blocks, page.rect.height)

            # Detect tables and captions in body
            tables, captions, body_blocks = detect_tables_and_captions(body_blocks)

            # Merge paragraphs
            body_blocks = merge_paragraph_blocks(body_blocks)

            # Recombine (headers + body + captions + tables + footers)
            blocks = headers + body_blocks + captions + tables + footers

            # Tag metadata for downstream handling
            for b in headers:
                b.meta["region"] = "header"
            for b in footers:
                b.meta["region"] = "footer"
            for b in tables:
                b.meta["region"] = "table"
            for b in captions:
                b.meta["region"] = "caption"
            
            # Detect and tag headers/titles based on styling and patterns
            # Build page index map for title detection (titles often on first page)
            page_index_map = {}
            for idx, b in enumerate(blocks):
                page_index_map[b.id] = page_index
            _detect_and_tag_headers_titles(blocks, page_index_map=page_index_map)
        else:
            # Simple sorting (PHASE 0)
            blocks = _sort_blocks_by_reading_order(blocks)

        pages.append(
            Page(
                number=page_index + 1,
                width=float(page.rect.width),
                height=float(page.rect.height),
                blocks=blocks,
            )
        )

    return Document(source_path=path, pages=pages, meta={"parser": "pymupdf_rawdict"})
