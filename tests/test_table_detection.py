"""PHASE 3/4: Table detection and handling heuristics."""

from scitrans.core.models import BBox, Block, Line, Span, SpanStyle
from scitrans.parsing.layout import detect_tables_and_captions, is_table_candidate


def make_text_block(text: str, x0=50, y0=100, x1=200, y1=120) -> Block:
    lines = []
    for idx, line_text in enumerate(text.split("\n")):
        line_bbox = BBox(x0=x0, y0=y0 + idx * 10, x1=x1, y1=y0 + (idx + 1) * 10)
        span = Span(text=line_text, bbox=line_bbox, style=SpanStyle(size=11.0))
        lines.append(Line(spans=[span], bbox=line_bbox))
    return Block(
        id="b",
        type="text",
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y0 + len(lines) * 10),
        lines=lines,
    )


def test_table_candidate_heuristics():
    # Pipes
    table_block = make_text_block("| Col1 | Col2 |")
    assert is_table_candidate(table_block) is True

    # Numeric density (single line with separators and enough numbers)
    numeric_block = make_text_block("12.3  45.6  78.9  10.1")
    assert is_table_candidate(numeric_block) is True

    # Double spaces (columns)
    spaced_block = make_text_block("Name    Value    Notes")
    assert is_table_candidate(spaced_block) is True

    # Normal text
    normal_block = make_text_block("This is a paragraph.")
    assert is_table_candidate(normal_block) is False


def test_table_and_caption_detection():
    blocks = [
        make_text_block("| A | B |", y0=100, y1=120),  # table-like
        make_text_block("Figure 1: Sample", y0=130, y1=150),  # caption
        make_text_block("Normal paragraph", y0=160, y1=180),
    ]

    tables, captions, body = detect_tables_and_captions(blocks)

    assert len(tables) == 1
    assert len(captions) == 1
    assert len(body) == 1
