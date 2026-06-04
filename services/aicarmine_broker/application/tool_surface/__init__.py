"""Tool Surface capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'DispatchRequest': 'dispatcher',
    'RegistryToolDispatcher': 'dispatcher',
    'build_default_dispatcher': 'dispatcher',
    'candidate_actions_from_evidence': 'candidate_actions',
    'compact_tool_result_for_planner': 'result_compaction',
    'native_tools_schema_for_planner': 'manifest_builder',
    'tool_surface_names_for_turn': 'turn_surface_policy',

}

__all__ = sorted(_PUBLIC_EXPORTS)


def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
