"""Compatibility alias for relocated application owner.

Real owner: ``application/tool_surface/turn_surface_policy.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .tool_surface import turn_surface_policy as _owner

sys.modules[__name__] = _owner
