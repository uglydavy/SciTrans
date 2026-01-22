"""Utilities for generating and validating placeholder tokens used during masking.

SciTrans needs to protect segments of text (math, code, citations, etc.) from being
corrupted by downstream language models. To do this we replace the sensitive
spans with synthetic tokens that are unlikely to be translated and that carry
enough information to detect tampering. Each placeholder includes a kind
identifier, an incrementing index and an eight‑digit CRC32 checksum of the
protected text. The checksum allows us to detect if a placeholder has been
modified or omitted by the model.

Example token::

    @@SCITRANS_MATH_INLINE_0001_3F0A1C2B@@

The functions in this module centralise creation and basic validation of these
tokens. Validation here is intentionally minimal – full validation and
recovery of placeholders happens in the masking engine and downstream scoring.
"""

from __future__ import annotations

import binascii
import re
from typing import Dict, List

__all__ = ["generate_placeholder", "validate_placeholders"]


def generate_placeholder(kind: str, num: int, text: str) -> str:
    """Create a deterministic placeholder token for the given span.

    Args:
        kind: The logical category of the span (e.g. ``MATH_INLINE``).
        num:  A 1-based index used to ensure uniqueness per kind.
        text: The exact text being replaced. The CRC of this text is
            incorporated into the token for integrity checking.

    Returns:
        A token of the form ``@@SCITRANS_<KIND>_<num:04d>_<crc:08X>@@``.
    """
    # Compute an unsigned CRC32 for reproducible eight character code
    crc_val = binascii.crc32(text.encode("utf-8")) & 0xFFFFFFFF
    return f"@@SCITRANS_{kind}_{num:04d}_{crc_val:08X}@@"


def validate_placeholders(translated: str, registry: Dict[str, str]) -> List[str]:
    """Validate that all placeholders present in the registry appear in the translated text.

    This function performs a simple containment check for each placeholder and
    tolerates minor whitespace variations around underscores. It returns a
    list of placeholder tokens that were not found in the translated string.

    Args:
        translated: The translated text potentially containing placeholders.
        registry: A mapping of placeholder tokens to their original text.

    Returns:
        A list of placeholder tokens that were missing from the translation.
    """
    missing: List[str] = []
    for ph in registry.keys():
        if ph in translated:
            continue
        # Tolerate minor whitespace differences inside the token
        # e.g. @@SCITRANS_MATH_INLINE_0001_3F0A1C2B@@ vs @@SCITRANS_MATH_INLINE_0001_3F0A1C2B@@
        pattern = re.escape(ph)
        # Replace underscores with a pattern that allows optional spaces
        pattern = pattern.replace("_", r"\s*_\s*")
        if re.search(pattern, translated):
            continue
        missing.append(ph)
    return missing