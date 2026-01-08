"""Layout intelligence for better reading order and block grouping.

PHASE 1: Multi-column detection, paragraph merging, header/footer detection
PHASE 3: Table heuristics, caption grouping, improved overlap handling
"""

from __future__ import annotations

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


def is_table_candidate(block: Block) -> bool:
    """Enhanced table detection with better heuristics.
    
    Checks:
    1. Grid-like structure (multiple columns)
    2. Repeated separators (|, tabs, multiple spaces)
    3. Numeric patterns in cells
    4. Alignment patterns
    5. Consistent column structure
    
    CRITICAL: Exclude headers/titles from table detection
    """
    if block.type != "text":
        return False

    # CRITICAL: Never mark headers/titles as tables
    if block.meta.get("is_header") or block.meta.get("block_type") in ("title", "header", "subheader"):
        return False

    text = "".join(sp.text for ln in block.lines for sp in ln.spans)
    if not text.strip():
        return False

    # Signal 1: Pipes or tabs
    if "|" in text or "\t" in text:
        return True

    # Signal 2: Numeric density (but need multiple lines for table)
    lines = text.split('\n')
    # Allow single-line tables if they appear columnar: contain double spaces and at least three columns
    if len(lines) < 2:
        # Treat as a table when there are double spaces separating 3 or more chunks
        if "  " in text:
            parts = [p for p in text.split() if p]
            if len(parts) >= 3:
                return True
        return False

    digits = sum(1 for c in text if c.isdigit())
    if digits > 0 and digits / max(len(text), 1) > 0.25:
        return True

    # Signal 3: Repeated double-spaces (column-like)
    if "  " in text:
        return True

    return False


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
