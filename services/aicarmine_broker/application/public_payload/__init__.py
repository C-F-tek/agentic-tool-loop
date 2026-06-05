"""Public Payload capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'answer_for_openwebui': 'openwebui_terminal_answer',
    'build_public_result_digest': 'history_ledger',
    'build_tool_context_for_30b': 'openwebui_tool_context',
    'materialize_public_evidence': 'evidence_materializer',
    'OpenWebUIPayloadBuilder': 'openwebui_tool_context',
    'PublicEvidenceMaterializer': 'evidence_materializer',
    'public_terminal_result_for_30b': 'terminal_result',
    'public_tool_artifact_rows': 'tool_context',

}

__all__ = sorted(_PUBLIC_EXPORTS)


def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
