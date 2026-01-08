"""Translation cleaner stub.

In the full SciTrans pipeline the translation cleaner is responsible for
removing spill-over instructions or assistant messages that some models
emit, such as "Here is the translation:" or code fences.  The stub
implementation provided here simply returns the input candidate unchanged,
effectively disabling any cleaning logic.  This makes the behaviour more
predictable for tests that rely on specific candidate strings.
"""

from __future__ import annotations

from typing import Tuple


def clean_instruction_spillover(candidate: str) -> Tuple[str, bool]:
    """Return the candidate unchanged with ``False`` for removal flag.

    Args:
        candidate: The translated candidate string.

    Returns:
        A tuple of (candidate, removed) where removed is always False.
    """
    return candidate, False