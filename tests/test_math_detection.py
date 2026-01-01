"""Test PHASE 2 math detection features."""

from scitrans.core.models import BBox, Block, Line, Span, SpanStyle
from scitrans.parsing.math_detection import (
    detect_equation_blocks,
    has_latex_delimiters,
    has_math_unicode,
    is_equation_span,
    is_math_font,
    split_mixed_blocks,
)


def test_math_font_detection():
    """Test math font detection."""
    assert is_math_font("CMSY10")  # Computer Modern Symbol
    assert is_math_font("CMR10")  # Computer Modern Roman
    assert is_math_font("STIXGeneral")
    assert is_math_font("Symbol")

    assert not is_math_font("Times-Roman")
    assert not is_math_font("Helvetica")


def test_math_unicode_detection():
    """Test Unicode math symbol detection."""
    assert has_math_unicode("α + β = γ")  # Greek letters
    assert has_math_unicode("∫ ∑ ∏")  # Math operators
    assert has_math_unicode("→ ⇒ ←")  # Arrows
    assert has_math_unicode("x²")  # Superscript

    assert not has_math_unicode("Normal text")
    assert not has_math_unicode("Hello world 123")


def test_latex_delimiter_detection():
    """Test LaTeX delimiter detection."""
    assert has_latex_delimiters("Inline $E=mc^2$ math")
    assert has_latex_delimiters("Display $$x^2$$ equation")
    assert has_latex_delimiters("Bracket \\(x\\) notation")
    assert has_latex_delimiters("Display \\[x^2\\] bracket")

    assert not has_latex_delimiters("No math here")


def test_equation_span_detection():
    """Test span-level equation detection."""
    # Math font span
    span1 = Span(
        text="∑",
        bbox=BBox(x0=0, y0=0, x1=10, y1=10),
        style=SpanStyle(font="CMSY10", size=12.0),
    )
    assert is_equation_span(span1)

    # Unicode math span
    span2 = Span(
        text="α + β",
        bbox=BBox(x0=0, y0=0, x1=20, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    assert is_equation_span(span2)

    # LaTeX span
    span3 = Span(
        text="$x^2$",
        bbox=BBox(x0=0, y0=0, x1=20, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    assert is_equation_span(span3)

    # Normal text span
    span4 = Span(
        text="Normal text",
        bbox=BBox(x0=0, y0=0, x1=50, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    assert not is_equation_span(span4)


def test_equation_block_detection():
    """Test block-level equation detection."""
    # Create block with all equation spans
    eq_span1 = Span(
        text="∑", bbox=BBox(x0=0, y0=0, x1=10, y1=10), style=SpanStyle(font="CMSY10", size=12.0)
    )
    eq_span2 = Span(
        text="α", bbox=BBox(x0=10, y0=0, x1=20, y1=10), style=SpanStyle(font="Symbol", size=12.0)
    )
    line = Line(spans=[eq_span1, eq_span2], bbox=BBox(x0=0, y0=0, x1=20, y1=10))
    block = Block(id="b1", type="text", bbox=BBox(x0=0, y0=0, x1=20, y1=10), lines=[line])

    equation_ids = detect_equation_blocks([block])
    assert "b1" in equation_ids


def test_mixed_block_splitting():
    """Test splitting mixed text/equation blocks."""
    # Create mixed block
    text_span = Span(
        text="The equation",
        bbox=BBox(x0=0, y0=0, x1=50, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    eq_span = Span(
        text="α+β", bbox=BBox(x0=50, y0=0, x1=70, y1=10), style=SpanStyle(font="Symbol", size=11.0)
    )
    text_span2 = Span(
        text="is important",
        bbox=BBox(x0=70, y0=0, x1=120, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )

    line = Line(spans=[text_span, eq_span, text_span2], bbox=BBox(x0=0, y0=0, x1=120, y1=10))
    block = Block(id="b1", type="text", bbox=BBox(x0=0, y0=0, x1=120, y1=10), lines=[line])

    text_spans, equation_spans = split_mixed_blocks(block)

    assert len(text_spans) == 2  # "The equation", "is important"
    assert len(equation_spans) == 1  # "α+β"
    assert equation_spans[0].text == "α+β"


def test_no_false_positives():
    """Ensure normal text isn't detected as math."""
    # Normal paragraph
    span = Span(
        text="This is a normal paragraph with no mathematical content whatsoever.",
        bbox=BBox(x0=0, y0=0, x1=200, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    assert not is_equation_span(span)

    # Numbers aren't automatically math
    span2 = Span(
        text="The year 2025 and value 42.",
        bbox=BBox(x0=0, y0=0, x1=100, y1=10),
        style=SpanStyle(font="Times-Roman", size=11.0),
    )
    assert not is_equation_span(span2)
