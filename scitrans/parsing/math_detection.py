"""Math equation detection for span-level preservation.

PHASE 2: Detect equation spans to avoid redacting them during rendering.

Strategy:
1. Font-based detection (common math fonts)
2. Unicode math symbol detection
3. LaTeX delimiter detection
4. Glyph density heuristics
"""

from __future__ import annotations

import re

from scitrans.core.models import Block, Span

# Common math fonts in PDFs
MATH_FONTS = {
    "cmr",
    "cmsy",
    "cmmi",
    "cmex",  # Computer Modern (TeX)
    "symbol",
    "zapfdingbats",  # Symbol fonts
    "math",
    "stix",
    "cambria",  # Modern math fonts
    "euclid",
    "latinmodern",
}

# Unicode math symbols (common ranges)
MATH_UNICODE_RANGES = [
    (0x2200, 0x22FF),  # Mathematical Operators
    (0x2190, 0x21FF),  # Arrows
    (0x0391, 0x03C9),  # Greek letters
    (0x2070, 0x209F),  # Superscripts/Subscripts
    (0x2100, 0x214F),  # Letter-like Symbols
]

# Single codepoints for superscripts commonly used in PDFs
MATH_UNICODE_SINGLE = {
    0x00B2,  # ²
    0x00B3,  # ³
    0x00B9,  # ¹
}


def is_math_font(font_name: str) -> bool:
    """Check if font is commonly used for math."""
    font_lower = font_name.lower()
    return any(math_font in font_lower for math_font in MATH_FONTS)


def has_math_unicode(text: str) -> bool:
    """Check if text contains Unicode math symbols."""
    for char in text:
        code = ord(char)
        if code in MATH_UNICODE_SINGLE:
            return True
        for start, end in MATH_UNICODE_RANGES:
            if start <= code <= end:
                return True
    return False


def has_latex_delimiters(text: str) -> bool:
    """Check if text contains LaTeX math delimiters."""
    patterns = [
        r"\$.*?\$",  # $...$
        r"\\\(.*?\\\)",  # \(...\)
        r"\\\[.*?\\\]",  # \[...\]
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.DOTALL):
            return True
    return False


def is_equation_span(span: Span) -> bool:
    """Determine if a span is likely a math equation.

    Checks:
    1. Math font
    2. Unicode math symbols
    3. LaTeX delimiters
    4. Symbol density (high ratio of non-alphanumeric)
    """
    # Check font
    if is_math_font(span.style.font):
        return True

    # Check Unicode math
    if has_math_unicode(span.text):
        return True

    # Check LaTeX
    if has_latex_delimiters(span.text):
        return True

    # Check symbol density
    if len(span.text) > 3:
        alphanumeric = sum(1 for c in span.text if c.isalnum())
        total = len(span.text)
        if alphanumeric / total < 0.5:  # More than 50% non-alphanumeric
            return True

    return False


def detect_equation_blocks(blocks: list[Block]) -> set[str]:
    """Detect blocks that are primarily equations.

    Returns set of block IDs that are equations (should not be translated).
    """
    equation_block_ids = set()

    for block in blocks:
        if block.type != "text":
            continue

        # Count equation vs text spans
        total_spans = 0
        equation_spans = 0

        for line in block.lines:
            for span in line.spans:
                total_spans += 1
                if is_equation_span(span):
                    equation_spans += 1

        if total_spans > 0:
            equation_ratio = equation_spans / total_spans
            if equation_ratio > 0.7:  # More than 70% equation spans
                equation_block_ids.add(block.id)

    return equation_block_ids


def split_mixed_blocks(block: Block) -> tuple[list[Span], list[Span]]:
    """Split a block into text spans and equation spans.

    Args:
        block: Block potentially containing mixed text and math

    Returns:
        Tuple of (text_spans, equation_spans)
    """
    text_spans = []
    equation_spans = []

    for line in block.lines:
        for span in line.spans:
            if is_equation_span(span):
                equation_spans.append(span)
            else:
                text_spans.append(span)

    return text_spans, equation_spans


def get_translatable_text(block: Block) -> str:
    """Extract only translatable text from block (excluding equation spans).

    For PHASE 2: Render only natural language spans, preserve equation spans.
    """
    text_parts = []

    for line in block.lines:
        line_parts = []
        for span in line.spans:
            if not is_equation_span(span):
                line_parts.append(span.text)
            else:
                # Placeholder for equation span (preserved in rendering)
                line_parts.append(f"[EQUATION:{span.text}]")
        text_parts.append("".join(line_parts))

    return "\n".join(text_parts)
