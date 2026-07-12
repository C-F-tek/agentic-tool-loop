"""Controller capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'agent_flow_diagnostics': 'diagnostics',
    'controller_guard_count': 'guards',
    'controller_guard_rejection_signature': 'guards',
    'controller_initial_doc_preseed_plan': 'preseed',
    'controller_memory_lesson_text': 'memory',
    'query_plan_continue_without_model': 'rag_preseed',

}

__all__: list[str] = sorted(_PUBLIC_EXPORTS)

def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
