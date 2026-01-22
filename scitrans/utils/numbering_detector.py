"""Numbering detector stub.

The numbering detector is intended to recognise numbering patterns in lists and
tables (e.g., Roman numerals, alphabetical labels) so that they can be
preserved during translation. In this stub we provide a minimal class
interface that always returns ``False`` for numbering detection.
"""

from __future__ import annotations

from dataclasses import dataclass


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
# --- detect_numbering compatibility shim ---
# Pipeline expects NumberingDetector.detect_numbering(text). Some versions only expose other helpers.
# This shim provides detect_numbering without breaking existing implementations.

import re as _re

class _DetectedNumbering(dict):
    def __getattr__(self, k):
        return self.get(k)
    def __bool__(self):
        return bool(self.get("prefix"))

_NUM_PATTERNS = [
    ("decimal", _re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)\s*(?P<sep>[.)])\s+")),
    ("roman",   _re.compile(r"^\s*(?P<num>[IVXLCDM]+)\s*(?P<sep>[.)])\s+", _re.I)),
    ("alpha",   _re.compile(r"^\s*(?P<num>[A-Z])\s*(?P<sep>[.)])\s+")),
    ("section", _re.compile(r"^\s*(?P<label>(?:section|chapter|fig(?:ure)?|table))\s+(?P<num>\d+(?:\.\d+)*)\s*(?P<sep>[:.\-])\s*", _re.I)),
    ("bullet",  _re.compile(r"^\s*(?P<sep>[•\-\*\·])\s+")),
]

def _detect_numbering(text: str):
    s = text or ""
    for kind, pat in _NUM_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        prefix = m.group(0)
        num = m.groupdict().get("num") or ""
        sep = m.groupdict().get("sep") or ""
        return _DetectedNumbering(prefix=prefix, number=num, sep=sep, kind=kind, rest=s[len(prefix):])
    return _DetectedNumbering(prefix="", number="", sep="", kind="", rest=s)

def _preserve_numbering(source_text: str, target_text: str) -> str:
    """Preserve numbering from source in target if lost during translation."""
    source_numbering = _detect_numbering(source_text)
    if not source_numbering or not source_numbering.get("prefix"):
        return target_text
    
    # Check if target already has the numbering
    target_numbering = _detect_numbering(target_text)
    if target_numbering and target_numbering.get("prefix"):
        # Target already has numbering, don't modify
        return target_text
    
    # Special case: "Section X:" pattern - preserve "Section X:"
    section_match = _re.match(r'^(Section\s+\d+\s*[:.\-]\s*)', source_text, _re.I)
    if section_match:
        section_prefix = section_match.group(1)
        # If target doesn't start with this, prepend it
        if not target_text.lower().startswith(section_prefix.lower()):
            return section_prefix + target_text
    
    # Prepend source numbering to target
    return source_numbering["prefix"] + target_text

try:
    NumberingDetector  # type: ignore[name-defined]
except Exception:
    pass
else:
    if not hasattr(NumberingDetector, "detect_numbering"):
        setattr(NumberingDetector, "detect_numbering", staticmethod(_detect_numbering))
    if not hasattr(NumberingDetector, "preserve_numbering"):
        setattr(NumberingDetector, "preserve_numbering", staticmethod(_preserve_numbering))
