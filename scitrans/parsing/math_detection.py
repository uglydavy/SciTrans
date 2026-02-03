"""Math equation detection for span-level preservation.

PHASE 2: Detect equation spans to avoid redacting them during rendering.

Strategy:
1. Font-based detection (common math fonts)
2. Unicode math symbol detection
3. LaTeX delimiter detection
4. Glyph density heuristics
"""

from __future__ import annotations

import binascii
import re

from typing import Dict, Tuple

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
    (0x1D400, 0x1D7FF),  # Mathematical Alphanumeric Symbols
    (0x25A0, 0x25FF),  # Geometric Shapes
    (0x2600, 0x26FF),  # Miscellaneous Symbols
]

# Single codepoints for superscripts commonly used in PDFs
MATH_UNICODE_SINGLE = {
    0x00B2,  # ²
    0x00B3,  # ³
    0x00B9,  # ¹
}

# Common LaTeX math environments
LATEX_MATH_ENV = {
    "equation",
    "equation*",
    "align",
    "align*",
    "eqnarray",
    "eqnarray*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "split",
}

# Mathematical operator symbols
MATH_OPERATORS = set("=+-*/^<>")
MATH_OPERATOR_UNICODE = {
    "×",
    "÷",
    "±",
    "∓",
    "≠",
    "≤",
    "≥",
    "≈",
    "≡",
    "∈",
    "∉",
    "∝",
    "∞",
    "∑",
    "∏",
    "∫",
    "∂",
    "∇",
}

SUPERSCRIPT_RANGE = (0x2070, 0x209F)
SUBSCRIPT_RANGE = (0x2080, 0x209F)


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
        r"\\begin\{(" + "|".join(sorted(LATEX_MATH_ENV)) + r")\}.*?\\end\{\1\}",
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.DOTALL):
            return True
    return False


def _has_super_subscript(text: str) -> bool:
    for char in text:
        code = ord(char)
        if SUPERSCRIPT_RANGE[0] <= code <= SUPERSCRIPT_RANGE[1]:
            return True
        if SUBSCRIPT_RANGE[0] <= code <= SUBSCRIPT_RANGE[1]:
            return True
    return False


def _operator_count(text: str) -> int:
    count = 0
    for char in text:
        if char in MATH_OPERATORS or char in MATH_OPERATOR_UNICODE:
            count += 1
    return count


def _has_operator_pattern(text: str) -> bool:
    if _operator_count(text) == 0:
        return False
    # Require operator with numbers or variables to avoid plain punctuation
    if re.search(r"[0-9]", text) and _operator_count(text) >= 1:
        return True
    if re.search(r"\b[a-zA-Z]\b", text) and _operator_count(text) >= 1:
        return True
    if re.search(r"[α-ωΑ-Ω]", text) and _operator_count(text) >= 1:
        return True
    return False


def _has_variable_pattern(text: str) -> bool:
    latin_vars = re.findall(r"\b[a-zA-Z]\b", text)
    greek_vars = re.findall(r"\b[α-ωΑ-Ω]\b", text)
    if len(latin_vars) + len(greek_vars) >= 2:
        return True
    # Single variable combined with digits or operators
    if (latin_vars or greek_vars) and re.search(r"[0-9]", text) and _operator_count(text) >= 1:
        return True
    return False


def _has_math_context(text: str) -> bool:
    # Operators inside brackets/parentheses
    if re.search(r"[\(\[][^\)\]]*[+\-*/=<>≠≤≥∈∉][^\)\]]*[\)\]]", text):
        return True
    # Fractions like a/b or 1/2
    if re.search(r"\b[\w\)\]]+\s*/\s*[\w\(\[]+\b", text):
        return True
    # Inequality ranges
    if re.search(r"\b\d+\s*(≤|>=|<=|≥|<|>)\s*[a-zA-Zα-ωΑ-Ω0-9]+\b", text):
        return True
    # Set membership
    if re.search(r"\b[a-zA-Zα-ωΑ-Ω]\s*∈\s*\[[^\]]+\]", text):
        return True
    return False


def is_equation_span(
    span: Span,
    context_spans: list[Span] | None = None,
    sensitivity: float = 0.7,
) -> bool:
    """Determine if a span is likely a math equation.

    Multi-heuristic checks:
    1. Math font
    2. Unicode math symbols
    3. LaTeX delimiters and environments
    4. Symbol density (math operators vs text)
    5. Operator patterns
    6. Subscript/superscript usage
    7. Variable naming patterns
    8. Mathematical context (fractions, ranges, brackets)
    """
    text = span.text or ""
    if not text.strip():
        return False

    # Strong signals: immediate return
    if is_math_font(span.style.font):
        return True
    if has_latex_delimiters(text):
        return True

    # Avoid marking plain numbers or years as math
    if re.fullmatch(r"\d{1,4}", text.strip()):
        return False

    score = 0.0
    operator_count = _operator_count(text)
    word_count = len(re.findall(r"\b\w+\b", text))

    # Unicode math symbols are a strong signal but not definitive
    if has_math_unicode(text):
        score += 0.6

    # Operator patterns
    if _has_operator_pattern(text):
        score += 0.5

    # Subscript/superscript usage
    if _has_super_subscript(text):
        score += 0.5

    # Variable naming patterns
    if _has_variable_pattern(text):
        score += 0.6
        if word_count <= 4:
            score += 0.2

    # Mathematical context
    if _has_math_context(text):
        score += 0.5

    # Symbol density (math operators and symbols)
    if len(text) > 3:
        math_symbols = sum(1 for c in text if c in MATH_OPERATOR_UNICODE or c in MATH_OPERATORS)
        alphanumeric = sum(1 for c in text if c.isalnum())
        total = len(text)
        if total > 0 and (math_symbols / total) > 0.2 and (alphanumeric / total) < 0.7:
            score += 0.4

    # Penalize long natural language spans without operators
    if word_count >= 6 and operator_count == 0:
        score -= 0.3

    # Light penalty for sentence-like text ending with punctuation
    if text.strip().endswith((".", ";", ":")) and operator_count == 0:
        score -= 0.2

    if context_spans:
        # If surrounding spans are math-heavy, boost slightly
        math_neighbors = sum(1 for sp in context_spans if sp is not span and has_math_unicode(sp.text))
        if math_neighbors >= 2:
            score += 0.1

    return score >= sensitivity


def mask_math_in_text(
    text: str,
    block: Block,
    *,
    placeholder_fmt: str = "@@SCITRANS_MATH_INLINE_{num:04d}_{crc:08X}@@",
) -> Tuple[str, Dict[str, str]]:
    """Mask math spans within a text block using span-level math detection."""
    if not text or not block.lines:
        return text, {}

    masked = text
    registry: Dict[str, str] = {}
    counter = 0

    for line in block.lines:
        spans = line.spans or []
        for idx, span in enumerate(spans):
            if not span.text or not span.text.strip():
                continue
            context = spans[max(0, idx - 2) : min(len(spans), idx + 3)]
            if not is_equation_span(span, context_spans=context):
                continue
            counter += 1
            crc_val = binascii.crc32(span.text.encode("utf-8")) & 0xFFFFFFFF
            try:
                placeholder = placeholder_fmt.format(
                    kind="MATH_INLINE", num=counter, crc=crc_val
                )
            except KeyError:
                placeholder = f"@@SCITRANS_MATH_INLINE_{counter:04d}_{crc_val:08X}@@"
            if span.text in masked:
                masked = masked.replace(span.text, placeholder, 1)
                registry[placeholder] = span.text

    return masked, registry


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
