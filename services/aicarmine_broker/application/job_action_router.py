"""Compatibility alias for relocated application owner.

Real owner: ``application/job/action_router.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .job import action_router as _owner

sys.modules[__name__] = _owner
