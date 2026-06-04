"""Compatibility alias for relocated application owner.

Real owner: ``application/controller/guards.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .controller import guards as _owner

sys.modules[__name__] = _owner
