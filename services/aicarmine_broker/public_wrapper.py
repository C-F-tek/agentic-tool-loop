"""Deterministic public wrapper helpers for broker tool results."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MAX_TOOL_RESULT_CHARS, V6_MARKER
from .repo_tools import compact


def summary_from_result(result: dict[str, Any]) -> str:
    for key in ('answer_for_30b', 'context_for_30b', 'summary', 'content', 'text', 'message', 'stdout_tail'):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_TOOL_RESULT_CHARS]
    return compact(result, MAX_TOOL_RESULT_CHARS)

def deterministic_public_wrapper(*, public_tool_name: str, original_args: dict[str, Any], internal_tool: str, internal_args: dict[str, Any], dispatcher_result: dict[str, Any], selector_response: dict[str, Any], root: Path) -> dict[str, Any]:
    dispatcher_result = dict(dispatcher_result or {})
    dispatcher_result.setdefault('called_by_vulkan', internal_tool)
    ok = bool(dispatcher_result.get('ok', False))
    summary = summary_from_result(dispatcher_result)
    artifacts = [str(dispatcher_result.get('artifact'))] if dispatcher_result.get('artifact') else []
    answer = dispatcher_result.get('answer_for_30b')
    if not isinstance(answer, str) or not answer.strip():
        answer = summary
    return {'ok': ok, 'service': 'vulkan_agent', 'mode': V6_MARKER, 'verdict': 'PUBLIC_TOOL_X_RESULT_READY' if ok else 'PUBLIC_TOOL_X_RESULT_FAILED', 'tool_name': public_tool_name, 'tool_result_for': public_tool_name, 'operation_id': public_tool_name, 'called_by_30b': public_tool_name, 'arguments_from_30b': original_args, 'result': dispatcher_result, 'answer_for_30b': answer, 'summary_for_30b': summary, 'message_for_30b': answer, 'content': answer, 'text': answer, 'final': answer, 'tool_context_for_30b': dispatcher_result.get('context_for_30b') or answer, 'verified_problems': dispatcher_result.get('verified_problems') if isinstance(dispatcher_result.get('verified_problems'), list) else [], 'useful_next_calls': dispatcher_result.get('useful_next_calls') if isinstance(dispatcher_result.get('useful_next_calls'), list) else [], 'wrapper_call_contract': dispatcher_result.get('wrapper_call_contract') or {'public_tool': public_tool_name, 'rule': 'Call the public wrapper tool again with specific parameters when more local context is needed.'}, 'session_id': root.name, 'workspace': str(root), 'artifacts': artifacts, 'dispatcher_tool_result_l': dispatcher_result, 'wrapper_contract': {'type': 'deterministic_field_mapping', 'public_tool_x': public_tool_name, 'internal_tool_l': internal_tool, 'mapping': {'tool_name': 'public_tool_x', 'tool_result_for': 'public_tool_x', 'called_by_30b': 'public_tool_x', 'arguments_from_30b': 'original public arguments', 'result': 'raw/structured dispatcher result L', 'answer_for_30b': 'dispatcher answer_for_30b when available', 'summary_for_30b': 'dispatcher summary/context/content or compact JSON', 'ok': 'dispatcher result ok'}}, 'internal_vulkan': {'public_tool_x': public_tool_name, 'pipeline': '3571 -> 3572 -> 11435(select L) -> 3572(dispatch L + deterministic wrap X) -> 3571 -> 30B', 'selector_backend_tool_call': (selector_response.get('message') or {}).get('tool_calls', [None])[0] if isinstance(selector_response.get('message'), dict) else None, 'tool_called_by_vulkan': internal_tool, 'tool_arguments_by_vulkan': internal_args, 'dispatcher_executed_internal_tool': True, 'wrapper_generated_by': '3572 deterministic broker mapping', 'vulkan_wrapped_dispatcher_result': False}, 'broker_pipeline_contract': '30B/OpenWebUI -> 3571 bridge -> 3572 broker -> 11435 selects internal L -> 3572 dispatcher executes L -> 3572 deterministic wrapper maps L result as public X -> 3571 -> 30B'}

def fail_selector(public_tool_name: str, task: str, original_args: dict[str, Any], root: Path, selector_response: dict[str, Any]) -> dict[str, Any]:
    content = 'Vulkan/11435 did not emit a native internal tool_call; dispatcher was not executed.'
    return {'ok': False, 'service': 'vulkan_agent', 'mode': V6_MARKER, 'verdict': 'PUBLIC_TOOL_X_RESULT_FAILED', 'tool_name': public_tool_name, 'tool_result_for': public_tool_name, 'operation_id': public_tool_name, 'called_by_30b': public_tool_name, 'arguments_from_30b': original_args, 'result': {'ok': False, 'error': content, 'selector_response': selector_response}, 'summary_for_30b': content, 'message_for_30b': content, 'content': content, 'text': content, 'final': content, 'tool_context_for_30b': content, 'session_id': root.name, 'workspace': str(root), 'internal_vulkan': {'public_tool_x': public_tool_name, 'pipeline': '3571 -> 3572 -> 11435(select L) failed before dispatcher', 'dispatcher_executed_internal_tool': False, 'vulkan_wrapped_dispatcher_result': False}}
