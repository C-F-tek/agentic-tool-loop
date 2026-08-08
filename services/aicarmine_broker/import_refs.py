"""Centralised lazy-import registry.

Provides cached, thread-safe access to cross-module symbols so that callers
do not need scattered ``import ...`` statements inside function bodies.

Usage::

    from .import_refs import _resolve_lazy

    dispatch_tool = _resolve_lazy(".tool_dispatch", ["dispatch_tool"])["dispatch_tool"]
    normalize     = _resolve_lazy(".tool_contract", ["normalize_tool_name"]).get("normalize_tool_name")
"""
from __future__ import annotations

import importlib
import threading
from typing import Any

_lock = threading.Lock()
_registry: dict[str, dict[str, Any]] = {}


def _resolve_lazy(module_path: str, symbol_names: list[str]) -> dict[str, Any]:
    """Resolve *symbol_names* from *module_path*, cache and return the dict."""
    key = f"{module_path}::{','.join(symbol_names)}"
    with _lock:
        if key in _registry:
            return _registry[key]

    # Lazy load once
    mod = importlib.import_module(module_path, package="services.aicarmine_broker")
    result: dict[str, Any] = {name: getattr(mod, name) for name in symbol_names}
    with _lock:
        _registry[key] = result
    return result