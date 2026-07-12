"""HTTP client helpers for the Vulkan bridge.

The first refactor step keeps runtime behavior in ``vulkan_bridge.app``.
This module is intentionally small so later extraction can move the existing
client helpers here without changing the root entrypoint.
"""

from .app import _post_json

__all__ = ["_post_json"]

