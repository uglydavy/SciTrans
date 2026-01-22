from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TranslateRequest:
    text: str
    source_lang: str
    target_lang: str
    system_prompt: str
    temperature: float = 0.0
    n_candidates: int = 1
    context: dict[str, Any] = field(default_factory=dict)  # Metadata dict (e.g., is_header, block_id)
    identity_threshold: float = 0.90  # Identity detection threshold (0.90 for general, 0.95 for academic)
    is_header: bool = False  # Whether this is a header block (uses stricter threshold)
    timeout: float = 60.0  # Per-request timeout in seconds (adaptive based on text length)


@dataclass(frozen=True)
class TranslateResult:
    candidates: list[str]
    model: str
    backend: str
    meta: dict


class TranslationBackend(Protocol):
    name: str

    def translate(self, req: TranslateRequest) -> TranslateResult: ...
