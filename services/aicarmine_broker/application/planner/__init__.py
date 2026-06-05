"""Planner capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'normalize_planner_decision': 'decision_normalizer',
    'planner_decision': 'turn',
    'PlannerLoopState': 'state',
    'planner_system_for_current_mode': 'system_prompt',
    'run_agentic_planner_job': 'loop',
    'validate_planner_decision_against_evidence': 'validator',

}

__all__ = sorted(_PUBLIC_EXPORTS)


def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
