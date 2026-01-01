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
