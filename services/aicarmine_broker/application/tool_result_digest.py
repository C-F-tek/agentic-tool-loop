"""Compatibility alias for relocated application owner.

Real owner: ``application/tool_surface/result_digest.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .tool_surface import result_digest as _owner

sys.modules[__name__] = _owner
