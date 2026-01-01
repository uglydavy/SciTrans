from __future__ import annotations

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


class DummyBackend:
    """A backend for testing: returns the input as the output."""

    name = "dummy"

    def __init__(self, model: str = "dummy"):
        self.model = model

    def translate(self, req: TranslateRequest) -> TranslateResult:
        return TranslateResult(
            candidates=[req.text],
            model=self.model,
            backend=self.name,
            meta={"note": "identity translation"},
        )
