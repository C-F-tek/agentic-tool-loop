"""Compatibility alias for relocated application owner.

Real owner: ``application/evidence/scope_conflict_resolution.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .evidence import scope_conflict_resolution as _owner

sys.modules[__name__] = _owner
