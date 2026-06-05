"""Compatibility surface for broker configuration.

Existing imports use `aicarmine_broker.config`. The implementation now lives in
small env/model/compatibility modules while preserving the legacy constants.
"""

from .compatibility import *  # noqa: F401,F403
