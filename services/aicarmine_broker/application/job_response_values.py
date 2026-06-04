"""Compatibility alias for relocated application owner.

Real owner: ``application/job/response_values.py``.
This module intentionally aliases ``sys.modules[__name__]`` to the owner so
legacy imports and monkeypatches mutate the real owner module.
"""

from __future__ import annotations

import sys

from .job import response_values as _owner

sys.modules[__name__] = _owner
