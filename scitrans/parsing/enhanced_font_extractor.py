"""Enhanced font extractor stub.

This module exists to satisfy imports in parsers that attempt to use an
enhanced font extraction mechanism. The full implementation would analyse
text spans to infer font metadata and other typography features. In this
stub, we simply return an empty mapping.
"""

from __future__ import annotations

from typing import Dict, Any


def extract_fonts(block: Any) -> Dict[str, Any]:
    """Return an empty font description for the given block.

    Args:
        block: A Block-like object from which fonts should be extracted.

    Returns:
        An empty dictionary.  In a complete implementation this would map
        span identifiers to font descriptors.
    """
    return {}