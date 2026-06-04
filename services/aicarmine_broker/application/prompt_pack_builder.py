"""Compatibility alias for relocated application owner.

Real owner: ``application/prompt/pack_builder.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .prompt import pack_builder as _owner

sys.modules[__name__] = _owner
