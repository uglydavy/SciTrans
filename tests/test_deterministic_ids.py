"""Test that block IDs are deterministic across runs."""

from pathlib import Path

import fitz

from scitrans.parsing.pymupdf_parser import parse_pdf


def test_deterministic_block_ids(tmp_path: Path):
    """Block IDs should be stable across multiple parsing runs."""
    # Create a simple PDF
    src_pdf = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 80), "Hello world", fontsize=12)
    page.insert_text((50, 100), "Second block", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    # Parse twice
    doc1 = parse_pdf(str(src_pdf))
    doc2 = parse_pdf(str(src_pdf))

    # Block IDs should be identical
    assert len(doc1.pages) == len(doc2.pages)
    assert len(doc1.pages) == 1

    page1 = doc1.pages[0]
    page2 = doc2.pages[0]

    assert len(page1.blocks) == len(page2.blocks)
    assert len(page1.blocks) > 0

    # All block IDs should match
    ids1 = [b.id for b in page1.blocks]
    ids2 = [b.id for b in page2.blocks]
    assert ids1 == ids2, "Block IDs must be deterministic"


def test_reading_order_stability(tmp_path: Path):
    """Blocks should be sorted in reading order consistently."""
    # Create a PDF with multiple blocks
    src_pdf = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    # Add blocks in non-reading order
    page.insert_text((50, 100), "Bottom", fontsize=12)
    page.insert_text((50, 50), "Top", fontsize=12)
    page.insert_text((50, 75), "Middle", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    # Parse multiple times
    docs = [parse_pdf(str(src_pdf)) for _ in range(3)]

    # All should have same block order (top-to-bottom)
    block_orders = []
    for doc in docs:
        page = doc.pages[0]
        y_coords = [b.bbox.y0 for b in page.blocks if b.type == "text"]
        block_orders.append(y_coords)

    # All should be sorted (top-to-bottom)
    for y_coords in block_orders:
        assert y_coords == sorted(y_coords), "Blocks should be sorted top-to-bottom"

    # All runs should produce same order
    assert len(set(tuple(y) for y in block_orders)) == 1, "Block order should be stable"
