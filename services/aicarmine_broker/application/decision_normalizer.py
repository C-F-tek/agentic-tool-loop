"""Compatibility alias for relocated application owner.

Real owner: ``application/planner/decision_normalizer.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .planner import decision_normalizer as _owner

sys.modules[__name__] = _owner
