"""Layout intelligence for better reading order and block grouping.

PHASE 1: Multi-column detection, paragraph merging, header/footer detection
PHASE 3: Table heuristics, caption grouping, improved overlap handling
PHASE 4: Enhanced block classification and tagging
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scitrans.core.models import BBox, Block


@dataclass
class Column:
    """Detected column region."""

    x_min: float
    x_max: float
    blocks: list[Block]

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2


def detect_columns(blocks: list[Block], page_width: float, min_gap: float = 30.0) -> list[Column]:
    """Detect columns in a page using x-coordinate clustering.

    Args:
        blocks: List of blocks to analyze
        page_width: Page width
        min_gap: Minimum gap between columns (pts)

    Returns:
        List of detected columns (sorted left to right)
    """
    if not blocks:
        return []

    # Get x-centers of all blocks
    centers = [(b, (b.bbox.x0 + b.bbox.x1) / 2) for b in blocks]
    centers.sort(key=lambda x: x[1])

    # Detect gaps
    columns = []
    current_column_blocks = [centers[0][0]]
    current_x_min = centers[0][0].bbox.x0
    current_x_max = centers[0][0].bbox.x1

    for i in range(1, len(centers)):
        block, x_center = centers[i]
        prev_block, prev_center = centers[i - 1]

        gap = x_center - prev_center

        if gap > min_gap:
            # Start new column
            columns.append(
                Column(
                    x_min=current_x_min,
                    x_max=current_x_max,
                    blocks=current_column_blocks,
                )
            )
            current_column_blocks = [block]
            current_x_min = block.bbox.x0
            current_x_max = block.bbox.x1
        else:
            # Same column
            current_column_blocks.append(block)
            current_x_min = min(current_x_min, block.bbox.x0)
            current_x_max = max(current_x_max, block.bbox.x1)

    # Add last column
    columns.append(
        Column(
            x_min=current_x_min,
            x_max=current_x_max,
            blocks=current_column_blocks,
        )
    )

    return columns


# PHASE 3: Table and caption heuristics


def _is_heading_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if not re.search(r"[A-Za-z]", stripped):
        return False
    lowered = stripped.lower()
    if re.match(r"^\d+(?:\.\d+)*\s*[.:]?\s+\w+", stripped):
        return True
    keywords = {
        "section",
        "chapter",
        "introduction",
        "methodology",
        "methods",
        "results",
        "conclusion",
        "abstract",
        "summary",
        "discussion",
        "background",
        "related work",
        "future work",
    }
    return any(keyword in lowered for keyword in keywords)


def _split_columns(line: str) -> list[str]:
    if "|" in line:
        return [p.strip() for p in line.split("|") if p.strip()]
    if "\t" in line:
        return [p.strip() for p in line.split("\t") if p.strip()]
    return [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]


def _consistent_column_counts(lines: list[str]) -> bool:
    counts = []
    for line in lines:
        cols = _split_columns(line)
        if len(cols) >= 2:
            counts.append(len(cols))
    if len(counts) < 2:
        return False
    return max(counts) - min(counts) <= 1


def is_table_candidate(block: Block) -> bool:
    """Enhanced table detection with better heuristics.
    
    Checks:
    1. Grid-like structure (multiple columns)
    2. Repeated separators (|, tabs, multiple spaces)
    3. Numeric patterns in cells
    4. Alignment patterns
    5. Consistent column structure
    
    CRITICAL: Exclude headers/titles from table detection to avoid false positives
    """
    if block.type != "text":
        return False

    # CRITICAL: Never mark headers/titles as tables
    if block.meta.get("is_header") or block.meta.get("block_type") in ("title", "header", "subheader"):
        return False

    text = "\n".join("".join(sp.text for sp in ln.spans) for ln in block.lines)
    if not text.strip():
        return False

    lines = text.split('\n')
    
    # Exclude short single-line text that looks like section titles/headers
    if len(lines) == 1 and len(text) < 100:
        if _is_heading_like(text):
            return False
        
        # Check if it looks like a title (ends with colon, short, capitalized)
        if text.strip().endswith(':') and len(text.strip()) < 50:
            return False
    
    signals = 0
    has_separators = "|" in text or "\t" in text
    if has_separators:
        signals += 1

    if len(lines) >= 2 and _consistent_column_counts(lines):
        signals += 1

    # For single-line blocks: allow strong separators or aligned columns
    if len(lines) < 2:
        if has_separators:
            cols = _split_columns(text)
            if len(cols) >= 2:
                return True

        if "  " in text:
            cols = _split_columns(text)
            parts = text.split()
            numeric_parts = [p for p in parts if any(c.isdigit() for c in p)]

            # Column structure with 3+ columns, or numeric-heavy single-line
            if len(cols) >= 3 or len(numeric_parts) >= 4:
                double_spaces = re.findall(r'  +', text)
                if len(double_spaces) >= 2:
                    space_lengths = [len(s) for s in double_spaces]
                    if max(space_lengths) <= min(space_lengths) * 3:
                        return True

        return False

    # For multi-line blocks: check for table-like structure
    # Signal 1: High numeric density
    digits = sum(1 for c in text if c.isdigit())
    if digits > 0:
        numeric_density = digits / max(len(text), 1)
        # Slightly relaxed threshold for multi-line numeric tables
        if numeric_density > 0.22:
            signals += 1

    # Signal 2: Stacked table rows (many short lines, mixed numeric)
    short_lines = [line for line in lines if line.strip() and len(line.strip()) <= 20]
    numeric_lines = [line for line in lines if any(c.isdigit() for c in line)]
    if len(lines) >= 6 and len(short_lines) / len(lines) >= 0.7 and len(numeric_lines) / len(lines) >= 0.3:
        return True

    # Signal 3: Repeated double-spaces in multiple lines (column structure)
    if "  " in text:
        lines_with_double_spaces = [line for line in lines if "  " in line]
        # At least 50% of lines should have double spaces for a table
        if len(lines_with_double_spaces) >= len(lines) * 0.5:
            signals += 1

    return signals >= 2


def is_caption_candidate(block: Block) -> bool:
    """Heuristic to flag caption blocks (Figure/Table captions)."""
    if block.type != "text":
        return False

    text = "".join(sp.text for ln in block.lines for sp in ln.spans).strip().lower()
    if text.startswith("figure") or text.startswith("fig.") or text.startswith("table"):
        return True
    return False


def detect_tables_and_captions(blocks: list[Block]) -> tuple[list[Block], list[Block], list[Block]]:
    """Separate table blocks, caption blocks, and body blocks."""
    tables = []
    captions = []
    body = []

    for block in blocks:
        if is_table_candidate(block):
            tables.append(block)
        elif is_caption_candidate(block):
            captions.append(block)
        else:
            body.append(block)

    return tables, captions, body


def sort_blocks_multicolumn(blocks: list[Block], page_width: float) -> list[Block]:
    """Sort blocks considering multi-column layout.

    Strategy:
    1. Detect columns (if any)
    2. Sort blocks within each column (top-to-bottom)
    3. Combine columns left-to-right

    Args:
        blocks: Unsorted blocks
        page_width: Page width for column detection

    Returns:
        Blocks sorted in reading order
    """
    if not blocks:
        return []

    # Detect columns
    columns = detect_columns(blocks, page_width)

    # Sort blocks within each column (top-to-bottom)
    sorted_blocks = []
    for column in columns:
        # Sort by y0 (top-to-bottom), then x0 (left-to-right) for ties
        column_sorted = sorted(
            column.blocks, key=lambda b: (round(b.bbox.y0, 1), round(b.bbox.x0, 1))
        )
        sorted_blocks.extend(column_sorted)

    return sorted_blocks


def should_merge_blocks(block1: Block, block2: Block, max_gap: float = 15.0) -> bool:
    """Determine if two blocks should be merged into a paragraph.

    Args:
        block1: First block (earlier in reading order)
        block2: Second block (later in reading order)
        max_gap: Maximum vertical gap for merging (pts)

    Returns:
        True if blocks should be merged
    """
    if block1.type != "text" or block2.type != "text":
        return False

    # Check vertical proximity
    vertical_gap = block2.bbox.y0 - block1.bbox.y1
    if vertical_gap < 0 or vertical_gap > max_gap:
        return False

    # Check horizontal alignment (should have similar x-range)
    x_overlap = min(block1.bbox.x1, block2.bbox.x1) - max(block1.bbox.x0, block2.bbox.x0)
    avg_width = (block1.bbox.width() + block2.bbox.width()) / 2

    if x_overlap / avg_width < 0.7:  # Less than 70% overlap
        return False

    # Check if block1 ends with hyphen (common in academic PDFs)
    if block1.lines and block1.lines[-1].spans:
        last_text = block1.lines[-1].spans[-1].text
        if last_text.rstrip().endswith("-"):
            return True  # Hyphenated word continuation

    # Check if fonts match (roughly)
    if block1.lines and block2.lines:
        if block1.lines[0].spans and block2.lines[0].spans:
            size1 = block1.lines[0].spans[0].style.size
            size2 = block2.lines[0].spans[0].style.size
            if abs(size1 - size2) > 1.0:  # Font sizes differ significantly
                return False

    return True


def merge_paragraph_blocks(blocks: list[Block]) -> list[Block]:
    """Merge blocks that belong to the same paragraph.

    Args:
        blocks: Blocks in reading order

    Returns:
        Blocks with paragraphs merged
    """
    if len(blocks) <= 1:
        return blocks

    merged = []
    current = blocks[0]

    for next_block in blocks[1:]:
        if should_merge_blocks(current, next_block):
            # Merge: combine lines and extend bbox
            from scitrans.core.models import Block

            merged_lines = current.lines + next_block.lines
            merged_bbox = BBox(
                x0=min(current.bbox.x0, next_block.bbox.x0),
                y0=current.bbox.y0,
                x1=max(current.bbox.x1, next_block.bbox.x1),
                y1=next_block.bbox.y1,
            )

            # Create merged block (keep ID of first block)
            current = Block(
                id=current.id,
                type=current.type,
                bbox=merged_bbox,
                lines=merged_lines,
                meta={**current.meta, "merged": True},
            )
        else:
            # Don't merge: save current and start new
            merged.append(current)
            current = next_block

    # Add last block
    merged.append(current)

    return merged


def detect_headers_footers(
    blocks: list[Block], page_height: float, margin: float = 72.0
) -> tuple[list[Block], list[Block], list[Block]]:
    """Detect headers, footers, and body blocks.

    Args:
        blocks: All blocks on page
        page_height: Page height
        margin: Header/footer margin threshold (pts, default 72 = 1 inch)

    Returns:
        Tuple of (headers, body_blocks, footers)
    """
    headers = []
    footers = []
    body = []

    for block in blocks:
        if block.bbox.y0 < margin:
            # Top margin → likely header
            headers.append(block)
        elif block.bbox.y1 > page_height - margin:
            # Bottom margin → likely footer
            footers.append(block)
        else:
            # Middle → body content
            body.append(block)

    return headers, body, footers


def _get_avg_font_size(block: Block) -> float:
    """Calculate average font size for a block."""
    if not block.lines:
        return 12.0  # Default
    
    sizes = []
    for line in block.lines:
        for span in line.spans:
            if span.style and span.style.size and span.style.size > 0:
                sizes.append(float(span.style.size))
    
    return sum(sizes) / len(sizes) if sizes else 12.0


def _get_block_text(block: Block) -> str:
    """Extract text from block."""
    lines = []
    for line in block.lines:
        line_text = "".join(span.text for span in line.spans)
        lines.append(line_text)
    return "\n".join(lines).strip()


def classify_block_type(block: Block) -> str:
    """Classify block as title, header, subheader, paragraph, list_item, etc.
    
    PHASE 4.1: Enhanced block classification using:
    - Font size analysis
    - Content pattern matching
    - Position heuristics
    - Text length analysis
    
    Args:
        block: Block to classify
        
    Returns:
        Block type: "title", "header", "subheader", "paragraph", "list_item"
    """
    # Check font size
    avg_font_size = block.meta.get("median_font_size") or _get_avg_font_size(block)
    
    # Check content patterns
    text = _get_block_text(block)
    text_lower = text.lower().strip()
    text_len = len(text)
    
    script_category = block.meta.get("script_category", "latin")

    # Title: Large font (>= 16pt), short text
    if avg_font_size >= 16.0 and text_len < 120:
        return "title"
    
    # Header: Medium-large font (>= 14pt) OR starts with section pattern
    section_pattern = r'^(section|chapter|part|chapitre|partie|\d+\.)\s+'
    if avg_font_size >= 14.0 or re.match(section_pattern, text_lower):
        return "header"
    
    # Subheader: Medium font (>= 12pt), short text
    if avg_font_size >= 12.0 and text_len < (120 if script_category == "cjk" else 150):
        return "subheader"
    
    # List item: Starts with bullet or number
    list_pattern = r'^[•\-\*·]|^\d+[.)]\s+'
    if re.match(list_pattern, text):
        return "list_item"
    
    # Default: paragraph
    return "paragraph"
