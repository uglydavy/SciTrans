"""Test configuration.

These tests support running directly from a source checkout without requiring
an editable install. We ensure the repository root is on `sys.path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
