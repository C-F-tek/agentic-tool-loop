"""Shared capability owner package.

This package exposes a controlled public API through ``__all__`` and lazy
``__getattr__``. Implementation modules use leading-underscore helpers for
private behavior; consumers should import the public owner API or a specific
owner module, not depend on flat compatibility shims.
"""

from __future__ import annotations

_PUBLIC_EXPORTS = {
    'drop_empty_dict_values': 'clean_values',
    'compact_evidence_contract_summary': 'evidence_contract_summary',
    'coverage_status_from_contract': 'evidence_contract_summary',
    'diagnostic_row': 'diagnostics',
    'evidence_contract_summary_triplet': 'evidence_contract_summary',
    'history_tool_result': 'history_queries',
    'planner_ollama_turn_from_decision': 'history_ledger',
    'repo_rel_token': 'path_tokens',
    'safe_json_text': 'diagnostics',
    'safe_text': 'diagnostics',
    'sha256_text': 'payload_metadata',
    'stable_json_fingerprint': 'payload_metadata',

}

__all__: list[str] = sorted(_PUBLIC_EXPORTS)

def __getattr__(name: str):
    module_name = _PUBLIC_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, name)
