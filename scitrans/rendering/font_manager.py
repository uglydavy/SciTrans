from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True)
class FontSpec:
    name: str
    file: str | None = None  # path to a TTF/OTF file


class FontManager:
    """Resolve fonts for PDF insertion.

    Goal: ensure we always have a Unicode-safe font to prevent glyph loss (e.g. apostrophes -> '?').

    Strategy:
      - Prefer embedded fontfile if provided.
      - Otherwise map to DejaVu variants bundled in `assets/fonts/`.
      - Final fallback: Base-14 fonts (Helvetica).
    """

    def __init__(self, assets_dir: str | None = None):
        # assets_dir expected: <repo>/assets/fonts
        if assets_dir:
            self.assets_dir = Path(assets_dir)
        else:
            # package-relative assets directory
            self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"

    def _normalize_pdf_font(self, font_name: str) -> str:
        f = (font_name or "").strip()
        if "+" in f:
            f = f.split("+", 1)[1]
        return f or "Times-Roman"

    def _fallback_spec(self, original_font: str) -> FontSpec:
        f = original_font or ""
        f_low = f.lower()

        # Detect weight/style
        is_bold = "bold" in f_low
        is_italic = ("italic" in f_low) or ("oblique" in f_low)

        # Prefer DejaVu (bundled)
        if self.assets_dir.exists():
            if is_bold and is_italic:
                path = self.assets_dir / "DejaVuSans-BoldOblique.ttf"
                if path.exists():
                    return FontSpec(name="DejaVuSans-BoldOblique", file=str(path))
            if is_bold:
                path = self.assets_dir / "DejaVuSans-Bold.ttf"
                if path.exists():
                    return FontSpec(name="DejaVuSans-Bold", file=str(path))
            if is_italic:
                path = self.assets_dir / "DejaVuSans-Oblique.ttf"
                if path.exists():
                    return FontSpec(name="DejaVuSans-Oblique", file=str(path))

            path = self.assets_dir / "DejaVuSans.ttf"
            if path.exists():
                return FontSpec(name="DejaVuSans", file=str(path))

        # Fallback
        return FontSpec(name="Helvetica", file=None)

    def _supports_text(self, spec: FontSpec, text: str) -> bool:
        if not text:
            return True
        try:
            if spec.file:
                font = fitz.Font(fontfile=spec.file)
            else:
                font = fitz.Font(fontname=spec.name)
            if hasattr(font, "has_glyph"):
                for char in text:
                    if char.isspace():
                        continue
                    if not font.has_glyph(ord(char)):
                        return False
                return True
        except Exception:
            return False

        # Fallback heuristic: if any non-Latin1 char, require fallback font
        return all(ord(char) <= 255 or char.isspace() for char in text)

    def pick(self, original_font: str) -> FontSpec:
        original = self._normalize_pdf_font(original_font)
        return self._fallback_spec(original)

    def pick_for_text(self, text: str, original_font: str) -> FontSpec:
        """Prefer the original font, fallback only when glyphs are missing."""
        original = self._normalize_pdf_font(original_font)
        original_spec = FontSpec(name=original, file=None)
        if self._supports_text(original_spec, text):
            return original_spec
        return self._fallback_spec(original)

    # Backward-compatible helper used by renderers
    def get_font(self, font_name: str) -> tuple[str, str | None]:
        spec = self.pick(font_name)
        return spec.name, spec.file

    def get_font_for_text(self, text: str, font_name: str) -> tuple[str, str | None]:
        spec = self.pick_for_text(text, font_name)
        return spec.name, spec.file
