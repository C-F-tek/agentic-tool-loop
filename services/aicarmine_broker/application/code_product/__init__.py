"""Code Product capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'code_product_answer_text': 'public_outputs',
    'code_product_build_state_parse': 'state',
    'code_product_build_state_ready_payload': 'state',
    'code_product_payload_violations': 'state',

}

__all__ = sorted(_PUBLIC_EXPORTS)

def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
