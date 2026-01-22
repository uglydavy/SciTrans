r"""Stub implementation of an advanced math detector.

This module provides a minimal implementation of ``AdvancedMathDetector`` so that
imports of this class do not fail even when the full math detection logic is
absent. The purpose of the class is to identify and mask mathematical spans
within a block of text that may not be enclosed by explicit delimiters such
as `$...$` or `\( ... \)`. In this stub, no additional masking is
performed.
"""

from __future__ import annotations

from typing import Dict, Tuple


class AdvancedMathDetector:
    """Fallback advanced math detector that performs no additional masking."""

    def mask_math_in_text(
        self,
        text: str,
        block: object,
        *,
        placeholder_fmt: str = "@@SCITRANS_MATH_INLINE_{num:04d}_{crc:08X}@@",
    ) -> Tuple[str, Dict[str, str]]:
        """Return the text unchanged and an empty registry.

        Args:
            text: The input text to analyse.
            block: A Block-like object containing spans and font information.
            placeholder_fmt: Placeholder format string (unused in stub).

        Returns:
            A tuple of (masked_text, registry).  In this stub, the masked_text
            is identical to ``text`` and the registry is empty.
        """
        return text, {}