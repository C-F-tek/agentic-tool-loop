"""Compatibility alias for relocated application owner.

Real owner: ``application/public_payload/terminal_sanitizer.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .public_payload import terminal_sanitizer as _owner

sys.modules[__name__] = _owner
