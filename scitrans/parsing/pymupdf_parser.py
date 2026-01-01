from __future__ import annotations

import hashlib

import fitz  # PyMuPDF

from scitrans.core.models import BBox, Block, Document, Line, Page, Span, SpanStyle
from scitrans.parsing.layout import (
    detect_headers_footers,
    detect_tables_and_captions,
    merge_paragraph_blocks,
    sort_blocks_multicolumn,
)


def _bbox_from_tuple(t: tuple[float, float, float, float]) -> BBox:
    x0, y0, x1, y1 = t
    return BBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))


def _deterministic_block_id(page_index: int, bbox: BBox, text_content: str) -> str:
    """Generate a deterministic block ID based on page, bbox, and text content.

    This ensures stable IDs across runs for caching and repair workflows.
    """
    # Round bbox to avoid floating-point instability
    bbox_str = f"{page_index}_{round(bbox.x0, 2)}_{round(bbox.y0, 2)}_{round(bbox.x1, 2)}_{round(bbox.y1, 2)}"
    # Include first 50 chars of text for uniqueness
    text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()[:8]
    combined = f"{bbox_str}_{text_hash}"
    block_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
    return f"b_{page_index}_{block_hash}"


def _sort_blocks_by_reading_order(blocks: list[Block]) -> list[Block]:
    """Sort blocks by reading order: top-to-bottom, then left-to-right.

    This ensures consistent block ordering across runs.
    """

    def sort_key(block: Block) -> tuple[float, float]:
        # Primary: y0 (top-to-bottom)
        # Secondary: x0 (left-to-right)
        return (round(block.bbox.y0, 2), round(block.bbox.x0, 2))

    return sorted(blocks, key=sort_key)


def parse_pdf(path: str, use_layout_intelligence: bool = True) -> Document:
    """Parse a PDF into a stable page/block/line/span representation.

    Args:
        path: PDF file path
        use_layout_intelligence: Enable PHASE 1 improvements (column detection, paragraph merging)

    Notes:
      - Uses PyMuPDF `page.get_text("rawdict")` for maximum detail.
      - PHASE 1/3: Multi-column reading order, paragraph merging, table/caption tagging
      - Keeps image blocks as `type="image"` without text.
    """
    doc = fitz.open(path)
    pages: list[Page] = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        raw = page.get_text("rawdict")
        blocks: list[Block] = []

        for b in raw.get("blocks", []):
            btype = b.get("type", 0)
            bbox = _bbox_from_tuple(tuple(b.get("bbox", (0, 0, 0, 0))))

            if btype == 1:
                # Image block: use bbox + page index for ID
                block_id = _deterministic_block_id(page_index, bbox, f"image_{bbox.x0}_{bbox.y0}")
                blocks.append(
                    Block(
                        id=block_id,
                        type="image",
                        bbox=bbox,
                        lines=[],
                        meta={"raw_type": 1},
                    )
                )
                continue

            # text block
            lines: list[Line] = []
            text_parts: list[str] = []
            for ln in b.get("lines", []):
                line_bbox = _bbox_from_tuple(
                    tuple(ln.get("bbox", (bbox.x0, bbox.y0, bbox.x1, bbox.y1)))
                )
                spans: list[Span] = []
                for sp in ln.get("spans", []):
                    sp_text = sp.get("text", "")
                    if not sp_text and sp.get("chars"):
                        sp_text = "".join(ch.get("c", "") for ch in sp.get("chars", []))
                    text_parts.append(sp_text)
                    sp_bbox = _bbox_from_tuple(
                        tuple(
                            sp.get("bbox", (line_bbox.x0, line_bbox.y0, line_bbox.x1, line_bbox.y1))
                        )
                    )
                    style = SpanStyle(
                        font=str(sp.get("font", "Times-Roman")),
                        size=float(sp.get("size", 11.0)),
                        flags=int(sp.get("flags", 0)),
                        color=sp.get("color"),
                    )
                    spans.append(Span(text=sp_text, bbox=sp_bbox, style=style))
                lines.append(Line(spans=spans, bbox=line_bbox))

            # Generate deterministic ID from page, bbox, and text content
            text_content = "".join(text_parts)
            block_id = _deterministic_block_id(page_index, bbox, text_content)
            blocks.append(
                Block(
                    id=block_id,
                    type="text",
                    bbox=bbox,
                    lines=lines,
                    meta={"raw_type": 0},
                )
            )

        # PHASE 1/3: Layout intelligence
        if use_layout_intelligence:
            # Multi-column reading order
            blocks = sort_blocks_multicolumn(blocks, page.rect.width)

            # Detect headers/footers (optional: exclude from translation)
            headers, body_blocks, footers = detect_headers_footers(blocks, page.rect.height)

            # Detect tables and captions in body
            tables, captions, body_blocks = detect_tables_and_captions(body_blocks)

            # Merge paragraphs
            body_blocks = merge_paragraph_blocks(body_blocks)

            # Recombine (headers + body + captions + tables + footers)
            blocks = headers + body_blocks + captions + tables + footers

            # Tag metadata for downstream handling
            for b in headers:
                b.meta["region"] = "header"
            for b in footers:
                b.meta["region"] = "footer"
            for b in tables:
                b.meta["region"] = "table"
            for b in captions:
                b.meta["region"] = "caption"
        else:
            # Simple sorting (PHASE 0)
            blocks = _sort_blocks_by_reading_order(blocks)

        pages.append(
            Page(
                number=page_index + 1,
                width=float(page.rect.width),
                height=float(page.rect.height),
                blocks=blocks,
            )
        )

    return Document(source_path=path, pages=pages, meta={"parser": "pymupdf_rawdict"})
