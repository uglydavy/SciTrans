"""Identity translation detection stubs.

This module provides a minimal implementation of identity translation detection
for use during testing and in environments where the full heuristic-based
identity detection is unavailable. It exposes an ``IdentityCheckResult`` data
class and a simple ``check_identity_translation`` function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IdentityCheckResult:
    """Represents the result of an identity translation check.

    Attributes:
        is_identity: True if the translated text is considered effectively
            identical to the source.
        should_retry: True if a retry should be triggered due to identity.
    """

    is_identity: bool
    should_retry: bool


def check_identity_translation(
    source: str,
    translated: str,
    *,
    is_header: bool = False,
    is_bullet: bool = False,
) -> IdentityCheckResult:
    """Simple identity translation check.

    This stub checks if the translated string is identical to the source
    (ignoring whitespace) and returns an ``IdentityCheckResult``. It does not
    perform any advanced heuristics.

    Args:
        source: The original text.
        translated: The translated text.
        is_header: Whether the text originates from a header block (unused).
        is_bullet: Whether the text originates from a bullet block (unused).

    Returns:
        An ``IdentityCheckResult`` with ``is_identity`` set to True when
        the source and translation normalised strings are equal, and
        ``should_retry`` equal to the same value.
    """
    # Normalise whitespace for a simple comparison
    norm_src = " ".join(source.split())
    norm_tr = " ".join(translated.split())
    is_identical = norm_src == norm_tr and bool(norm_src)
    return IdentityCheckResult(is_identity=is_identical, should_retry=is_identical)