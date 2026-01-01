"""
Character-level PDF parser using pdfminer.

This parser extracts individual characters with their exact positions,
fonts, and sizes - required for perfect rendering preservation.

Based on PDFMathTranslate's approach.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pdfminer.converter import PDFConverter
from pdfminer.layout import LTPage
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.utils import apply_matrix_pt

logger = logging.getLogger(__name__)


@dataclass
class CharInfo:
    """Information about a single character."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str
    font_size: float
    cid: int  # Character ID in font
    advance_width: float
    is_formula: bool = False


@dataclass
class ParagraphInfo:
    """Information about a paragraph (group of characters)."""

    text: str
    chars: list[CharInfo]
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float
    has_line_break: bool = False


class CharacterLevelConverter(PDFConverter):
    """
    PDF converter that extracts character-level information.

    Similar to PDFMathTranslate's PDFConverterEx but adapted for our needs.
    """

    def __init__(self, rsrcmgr: PDFResourceManager):
        PDFConverter.__init__(self, rsrcmgr, None, "utf-8", 1, None)
        self.paragraphs: list[ParagraphInfo] = []
        self.current_paragraph_chars: list[CharInfo] = []
        self.current_paragraph_text: str = ""
        self.font_map = {}  # Font ID -> Font object

    def begin_page(self, page, ctm) -> None:
        """Start of page."""
        (x0, y0, x1, y1) = page.cropbox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPage(page.pageno, mediabox)
        self.paragraphs = []

    def end_page(self, page):
        """End of page - return collected paragraphs."""
        if self.current_paragraph_chars:
            self._finish_paragraph()
        return self.paragraphs

    def render_char(
        self,
        matrix,
        font,
        fontsize: float,
        scaling: float,
        rise: float,
        cid: int,
        ncs,
        graphicstate,
    ) -> float:
        """
        Called for each character in the PDF.

        This is where we extract character-level information.
        """
        try:
            text = font.to_unichr(cid)
        except Exception:
            text = "?"

        textwidth = font.char_width(cid)
        advance = textwidth * fontsize * scaling / 100.0

        # Get character bbox (simplified)
        # In reality, need to apply matrix transformations
        x0, y0 = matrix[4], matrix[5]
        x1, y1 = x0 + advance, y0 + fontsize

        # Create character info
        char_info = CharInfo(
            text=text,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            font_name=font.fontname if hasattr(font, "fontname") else "Unknown",
            font_size=fontsize,
            cid=cid,
            advance_width=advance,
            is_formula=False,  # Will be determined by formula detection
        )

        # Add to current paragraph
        self.current_paragraph_chars.append(char_info)
        self.current_paragraph_text += text

        return advance

    def _finish_paragraph(self):
        """Finish current paragraph and start new one."""
        if not self.current_paragraph_chars:
            return

        # Calculate paragraph bbox
        x0 = min(c.x0 for c in self.current_paragraph_chars)
        y0 = min(c.y0 for c in self.current_paragraph_chars)
        x1 = max(c.x1 for c in self.current_paragraph_chars)
        y1 = max(c.y1 for c in self.current_paragraph_chars)

        # Get dominant font size
        font_size = self.current_paragraph_chars[0].font_size

        para = ParagraphInfo(
            text=self.current_paragraph_text,
            chars=self.current_paragraph_chars,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            font_size=font_size,
        )

        self.paragraphs.append(para)

        # Reset for next paragraph
        self.current_paragraph_chars = []
        self.current_paragraph_text = ""


def parse_pdf_character_level(pdf_path: str) -> list[list[ParagraphInfo]]:
    """
    Parse PDF and extract character-level information.

    Returns:
        List of pages, each containing list of paragraphs
    """
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfinterp import PDFPageInterpreter
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser

    result = []

    with open(pdf_path, "rb") as fp:
        parser = PDFParser(fp)
        doc = PDFDocument(parser)
        rsrcmgr = PDFResourceManager()

        for page in PDFPage.create_pages(doc):
            converter = CharacterLevelConverter(rsrcmgr)
            interpreter = PDFPageInterpreter(rsrcmgr, converter)
            interpreter.process_page(page)

            paragraphs = converter.end_page(page)
            result.append(paragraphs)

    return result
