from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class BBox(BaseModel):
    """PDF bbox in PyMuPDF coordinate space (x0, y0, x1, y1)."""

    model_config = ConfigDict(frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float

    def width(self) -> float:
        return self.x1 - self.x0

    def height(self) -> float:
        return self.y1 - self.y0


class SpanStyle(BaseModel):
    """Rendering-relevant style extracted from PDF spans."""

    model_config = ConfigDict(frozen=True)

    font: str = "Times-Roman"
    size: float = 11.0
    flags: int = 0
    color: Optional[int] = None  # PDF integer color if available


class Span(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    bbox: BBox
    style: SpanStyle


class Line(BaseModel):
    model_config = ConfigDict(frozen=True)

    spans: list[Span]
    bbox: BBox


BlockType = Literal["text", "image", "vector", "table", "unknown"]


class Block(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: BlockType
    bbox: BBox
    lines: list[Line] = Field(default_factory=list)

    # Optional metadata (layout classifier, reading order, etc.)
    meta: dict[str, Any] = Field(default_factory=dict)


class Page(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: int
    width: float
    height: float
    blocks: list[Block]


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_path: str
    pages: list[Page]
    meta: dict[str, Any] = Field(default_factory=dict)


class MaskedBlock(BaseModel):
    """Block text after masking, plus registry needed for restoration."""

    model_config = ConfigDict(frozen=True)

    block_id: str
    masked_text: str
    registry: dict[str, str]
    # For debugging
    mask_counts: dict[str, int] = Field(default_factory=dict)
    # PHASE 4: Metadata for context-aware processing (e.g., section_prefix)
    meta: dict[str, Any] = Field(default_factory=dict)


class TranslatedBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    block_id: str
    source_text: str
    translated_text: str
    # Quality + validation
    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
