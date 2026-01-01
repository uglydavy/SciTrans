from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF

from scitrans.core.models import Document


@dataclass(frozen=True)
class LayoutMetrics:
    overlap_pairs: int
    mean_iou: float


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.get_area()
    union_area = a.get_area() + b.get_area() - inter_area
    return 0.0 if union_area <= 0 else inter_area / union_area


def compute_block_overlap_metrics(doc: Document, *, page_index: int = 0) -> LayoutMetrics:
    """Compute simple overlap metrics on a page based on parsed bboxes."""
    page = doc.pages[page_index]
    rects = [
        fitz.Rect(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
        for b in page.blocks
        if b.type == "text"
    ]

    overlaps = 0
    ious = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            iou = _iou(rects[i], rects[j])
            if iou > 0:
                overlaps += 1
                ious.append(iou)

    mean_iou = sum(ious) / len(ious) if ious else 0.0
    return LayoutMetrics(overlap_pairs=overlaps, mean_iou=mean_iou)


def compute_rendered_pdf_overlap_metrics(pdf_path: str, *, page_index: int = 0) -> LayoutMetrics:
    """Compute overlap metrics by parsing the rendered PDF directly.
    
    This validates that the actual rendered PDF has no overlapping text blocks.
    Parses the output PDF using PyMuPDF and checks for overlapping text blocks.
    
    Args:
        pdf_path: Path to the rendered PDF file
        page_index: Page index to check (0-based)
        
    Returns:
        LayoutMetrics with overlap information
    """
    pdf = fitz.open(pdf_path)
    
    if page_index >= len(pdf):
        pdf.close()
        return LayoutMetrics(overlap_pairs=0, mean_iou=0.0)
    
    page = pdf[page_index]
    
    # Get all text blocks from the rendered PDF
    text_dict = page.get_text("rawdict")
    blocks = text_dict.get("blocks", [])
    
    # Extract text block rectangles
    rects = []
    for block in blocks:
        if block.get("type") == 0:  # Text block
            bbox = block.get("bbox", [0, 0, 0, 0])
            if len(bbox) == 4:
                rects.append(fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3]))
    
    # Compute overlaps
    overlaps = 0
    ious = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            iou = _iou(rects[i], rects[j])
            # Only count significant overlaps (IoU > 0.01 to ignore minor edge cases)
            if iou > 0.01:
                overlaps += 1
                ious.append(iou)
    
    mean_iou = sum(ious) / len(ious) if ious else 0.0
    pdf.close()
    
    return LayoutMetrics(overlap_pairs=overlaps, mean_iou=mean_iou)
