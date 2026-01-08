"""Numbering detector stub.

The numbering detector is intended to recognise numbering patterns in lists and
tables (e.g., Roman numerals, alphabetical labels) so that they can be
preserved during translation. In this stub we provide a minimal class
interface that always returns ``False`` for numbering detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NumberingDetector:
    """A stubbed numbering detector that performs no detection."""

    def detect(self, text: str) -> bool:
        """Return False for all inputs.

        Args:
            text: The input string.

        Returns:
            Always ``False`` indicating no numbering pattern was detected.
        """
        return False