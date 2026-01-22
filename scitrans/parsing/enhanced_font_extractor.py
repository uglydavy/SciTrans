"""
Enhanced font extraction utilities.

The parser expects:
- extract_enhanced_font_from_span(span_dict) -> EnhancedFont
- get_font_fallback(family, weight, style) -> str

This implementation is intentionally conservative: it infers family/weight/style
from the PDF span "font" name and span flags, and returns a stable fallback
font name that downstream FontManager can map to bundled DejaVu fonts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple, Union


ColorType = Union[int, Tuple[float, float, float]]  # fitz spans usually give int


@dataclass(frozen=True)
class EnhancedFont:
    family: str
    weight: str = "normal"   # "normal" | "bold"
    style: str = "normal"    # "normal" | "italic"
    size: float = 11.0
    flags: int = 0
    color: Optional[ColorType] = None

    def _color_to_int(self) -> Optional[int]:
        """Convert stored color to an int 0xRRGGBB when possible."""
        if self.color is None:
            return None
        if isinstance(self.color, int):
            return self.color
        # Tuple floats 0..1
        try:
            r, g, b = self.color
            r_i = max(0, min(255, int(round(r * 255))))
            g_i = max(0, min(255, int(round(g * 255))))
            b_i = max(0, min(255, int(round(b * 255))))
            return (r_i << 16) + (g_i << 8) + b_i
        except Exception:
            return None


def _normalize_font_name(font: str) -> str:
    """Remove subset prefixes like 'ABCDEE+FontName'."""
    f = (font or "").strip()
    if "+" in f:
        # e.g. 'EABCDF+TimesNewRomanPSMT'
        f = f.split("+", 1)[1]
    return f or "Times-Roman"


def _infer_bold_italic(font: str, flags: int) -> tuple[bool, bool]:
    f = (font or "").lower()
    is_bold = ("bold" in f) or bool(flags & (2**4))  # PyMuPDF bold flag often bit 4
    is_italic = ("italic" in f) or ("oblique" in f)
    # Some PDFs encode italic in flags bit 1, but it's not consistent; name is safer.
    return is_bold, is_italic


def _infer_family(font: str) -> str:
    f = _normalize_font_name(font)
    # Heuristic split on '-' (e.g., 'Times-BoldItalic')
    if "-" in f:
        return f.split("-", 1)[0] or "Times"
    return f


def extract_enhanced_font_from_span(span: dict[str, Any]) -> EnhancedFont:
    """
    Extract EnhancedFont from a PyMuPDF span dict (from page.get_text('dict')).
    """
    font = _normalize_font_name(str(span.get("font", "Times-Roman")))
    flags = int(span.get("flags", 0) or 0)
    size = float(span.get("size", 11.0) or 11.0)
    color = span.get("color", None)

    family = _infer_family(font)
    is_bold, is_italic = _infer_bold_italic(font, flags)

    weight = "bold" if is_bold else "normal"
    style = "italic" if is_italic else "normal"

    return EnhancedFont(
        family=family,
        weight=weight,
        style=style,
        size=size,
        flags=flags,
        color=color,
    )


def get_font_fallback(family: str, weight: str = "normal", style: str = "normal") -> str:
    """
    Return a stable 'font name' string. FontManager later maps it to bundled DejaVu.
    The only requirement is: include 'bold'/'italic' tokens when appropriate.
    """
    fam = (family or "").strip() or "Times-Roman"

    suffix = ""
    if (weight or "").lower() in {"bold", "black", "semibold", "demibold"}:
        suffix += "Bold"
    if (style or "").lower() in {"italic", "oblique"}:
        suffix += "Italic"

    if suffix:
        return f"{fam}-{suffix}"
    return fam
