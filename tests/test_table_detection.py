"""PHASE 3/4: Table detection and handling heuristics."""

from scitrans.core.models import BBox, Block, Line, Span, SpanStyle
from scitrans.parsing.layout import detect_tables_and_captions, is_table_candidate


def make_text_block(text: str, x0=50, y0=100, x1=200, y1=120) -> Block:
    span = Span(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), style=SpanStyle(size=11.0))
    line = Line(spans=[span], bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))
    return Block(id="b", type="text", bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), lines=[line])


def test_table_candidate_heuristics():
    # Pipes
    table_block = make_text_block("| Col1 | Col2 |")
    assert is_table_candidate(table_block) is True

    # Numeric density
    numeric_block = make_text_block("12.3 45.6 78.9")
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
