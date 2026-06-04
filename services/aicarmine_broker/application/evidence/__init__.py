"""Evidence capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'execution_evidence_digest_text': 'execution_digest',
    'goal_requests_apply': 'goal_classifier',
    'goal_requests_code_product': 'goal_classifier',
    'planner_evidence_contract': 'builder',
    'repo_path_kind': 'repo_path_policy',
    'required_working_set_for_prompt': 'required_working_set',
    'semantic_goal_classification': 'goal_classifier',

}

__all__ = sorted(_PUBLIC_EXPORTS)


def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
