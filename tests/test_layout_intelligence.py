"""Test PHASE 1 layout intelligence features."""

from pathlib import Path

import fitz

from scitrans.core.models import BBox, Block
from scitrans.parsing.layout import (
    detect_columns,
    detect_headers_footers,
    merge_paragraph_blocks,
    should_merge_blocks,
    sort_blocks_multicolumn,
)
from scitrans.parsing.pymupdf_parser import parse_pdf


def test_column_detection():
    """Test column detection."""
    # Create blocks in two columns
    left_blocks = [
        Block(id="b1", type="text", bbox=BBox(x0=50, y0=100, x1=250, y1=120), lines=[]),
        Block(id="b2", type="text", bbox=BBox(x0=50, y0=130, x1=250, y1=150), lines=[]),
    ]

    right_blocks = [
        Block(id="b3", type="text", bbox=BBox(x0=300, y0=100, x1=500, y1=120), lines=[]),
        Block(id="b4", type="text", bbox=BBox(x0=300, y0=130, x1=500, y1=150), lines=[]),
    ]

    all_blocks = left_blocks + right_blocks

    columns = detect_columns(all_blocks, page_width=550)

    # Should detect 2 columns
    assert len(columns) == 2
    assert len(columns[0].blocks) == 2
    assert len(columns[1].blocks) == 2


def test_multicolumn_sort():
    """Test multi-column reading order sorting."""
    # Create blocks in wrong order (mixed columns)
    blocks = [
        Block(id="b1", type="text", bbox=BBox(x0=50, y0=100, x1=200, y1=120), lines=[]),  # Left top
        Block(
            id="b2", type="text", bbox=BBox(x0=300, y0=100, x1=450, y1=120), lines=[]
        ),  # Right top
        Block(
            id="b3", type="text", bbox=BBox(x0=50, y0=130, x1=200, y1=150), lines=[]
        ),  # Left bottom
        Block(
            id="b4", type="text", bbox=BBox(x0=300, y0=130, x1=450, y1=150), lines=[]
        ),  # Right bottom
    ]

    sorted_blocks = sort_blocks_multicolumn(blocks, page_width=500)

    # Reading order should be: left column top-to-bottom, then right column
    sorted_ids = [b.id for b in sorted_blocks]
    expected_ids = ["b1", "b3", "b2", "b4"]  # Left column (b1, b3), then right (b2, b4)

    assert sorted_ids == expected_ids


def test_header_footer_detection():
    """Test header and footer detection."""
    blocks = [
        Block(id="h1", type="text", bbox=BBox(x0=50, y0=20, x1=200, y1=40), lines=[]),  # Header
        Block(id="b1", type="text", bbox=BBox(x0=50, y0=100, x1=200, y1=120), lines=[]),  # Body
        Block(id="b2", type="text", bbox=BBox(x0=50, y0=130, x1=200, y1=150), lines=[]),  # Body
        Block(id="f1", type="text", bbox=BBox(x0=50, y0=800, x1=200, y1=820), lines=[]),  # Footer
    ]

    headers, body, footers = detect_headers_footers(blocks, page_height=842)  # A4 height

    assert len(headers) == 1
    assert len(body) == 2
    assert len(footers) == 1
    assert headers[0].id == "h1"
    assert footers[0].id == "f1"


def test_paragraph_merging():
    """Test paragraph block merging."""
    # Create two blocks that should merge (close vertical proximity, aligned)
    from scitrans.core.models import Line, Span, SpanStyle

    span1 = Span(
        text="First line", bbox=BBox(x0=50, y0=100, x1=150, y1=115), style=SpanStyle(size=11.0)
    )
    line1 = Line(spans=[span1], bbox=BBox(x0=50, y0=100, x1=150, y1=115))
    block1 = Block(id="b1", type="text", bbox=BBox(x0=50, y0=100, x1=150, y1=115), lines=[line1])

    span2 = Span(
        text="Second line", bbox=BBox(x0=50, y0=120, x1=150, y1=135), style=SpanStyle(size=11.0)
    )
    line2 = Line(spans=[span2], bbox=BBox(x0=50, y0=120, x1=150, y1=135))
    block2 = Block(id="b2", type="text", bbox=BBox(x0=50, y0=120, x1=150, y1=135), lines=[line2])

    # Should merge (small gap, aligned, same font)
    assert should_merge_blocks(block1, block2)

    # Merge
    merged = merge_paragraph_blocks([block1, block2])
    assert len(merged) == 1  # Two blocks merged into one
    assert len(merged[0].lines) == 2  # Both lines present


def test_no_merge_different_columns():
    """Blocks in different columns should not merge."""
    from scitrans.core.models import Line, Span, SpanStyle

    # Left column block
    span1 = Span(text="Left", bbox=BBox(x0=50, y0=100, x1=150, y1=115), style=SpanStyle(size=11.0))
    line1 = Line(spans=[span1], bbox=BBox(x0=50, y0=100, x1=150, y1=115))
    block1 = Block(id="b1", type="text", bbox=BBox(x0=50, y0=100, x1=150, y1=115), lines=[line1])

    # Right column block (different x-range)
    span2 = Span(
        text="Right", bbox=BBox(x0=300, y0=100, x1=400, y1=115), style=SpanStyle(size=11.0)
    )
    line2 = Line(spans=[span2], bbox=BBox(x0=300, y0=100, x1=400, y1=115))
    block2 = Block(id="b2", type="text", bbox=BBox(x0=300, y0=100, x1=400, y1=115), lines=[line2])

    # Should NOT merge (different columns)
    assert not should_merge_blocks(block1, block2)


def test_parse_pdf_with_layout_intelligence(tmp_path: Path):
    """Test parsing with PHASE 1 layout features enabled."""
    # Create two-column PDF
    pdf_path = tmp_path / "multicolumn.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # Left column
    page.insert_text((50, 100), "Left column line 1", fontsize=11)
    page.insert_text((50, 120), "Left column line 2", fontsize=11)

    # Right column
    page.insert_text((350, 100), "Right column line 1", fontsize=11)
    page.insert_text((350, 120), "Right column line 2", fontsize=11)

    doc.save(str(pdf_path))
    doc.close()

    # Parse with layout intelligence
    parsed = parse_pdf(str(pdf_path), use_layout_intelligence=True)

    assert len(parsed.pages) == 1
    assert len(parsed.pages[0].blocks) > 0

    # Reading order should be: left column, then right column
    # (Exact verification depends on block merging)
