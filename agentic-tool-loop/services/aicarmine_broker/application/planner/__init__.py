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
    'RequiredNextProgress': 'required_progress',
    'planner_system_for_current_mode': 'system_prompt',
    'progress_code_product_block_required': 'required_progress',
    'progress_code_product_route_shift': 'required_progress',
    'progress_forbidden_repeat_repo_read': 'required_progress',
    'progress_native_tool_required': 'required_progress',
    'progress_prompt_context_continuation': 'required_progress',
    'progress_quality_gate_final_allowed': 'required_progress',
    'required_next_progress_from_text': 'required_progress',
    'run_agentic_planner_job': 'loop',
    'validate_planner_decision_against_evidence': 'validator',

}

__all__: list[str] = sorted(_PUBLIC_EXPORTS)

def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
