from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranslateRequest:
    text: str
    source_lang: str
    target_lang: str
    system_prompt: str
    temperature: float = 0.0
    n_candidates: int = 1
    context: str = ""  # Reference-only context (DO NOT translate this)


@dataclass(frozen=True)
class TranslateResult:
    candidates: list[str]
    model: str
    backend: str
    meta: dict


class TranslationBackend(Protocol):
    name: str

    def translate(self, req: TranslateRequest) -> TranslateResult: ...
