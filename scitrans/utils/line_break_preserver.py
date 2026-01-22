"""Line break and paragraph spacing preservation stubs.

The real SciTrans implementation includes functions to preserve the original
line breaks and paragraph spacing of the source document when constructing
the input to the language model. These stubs simply return the input text
unchanged. They exist so that unit tests depending on these functions can
import them without failure.
"""

from __future__ import annotations



def preserve_line_breaks(text: str) -> str:
    """Return the input text unchanged.

    Args:
        text: The input string.

    Returns:
        The same string, unchanged.
    """
    return text


def preserve_paragraph_spacing(text: str) -> str:
    """Return the input text unchanged.

    Args:
        text: The input string.

    Returns:
        The same string, unchanged.
    """
    return text