"""Deterministic public wrapper helpers for broker tool results."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MAX_TOOL_RESULT_CHARS, V6_MARKER
from .repo_tools import compact
from .application.job.response_values import strip_narrative_duplicates_from_context


def summary_from_result(result: dict[str, Any]) -> str:
    for key in ('answer_for_30b', 'context_for_30b', 'summary', 'content', 'text', 'message', 'stdout_tail'):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_TOOL_RESULT_CHARS]
    return compact(result, MAX_TOOL_RESULT_CHARS)


def _strip_dispatcher_narrative_aliases(result: dict[str, Any], evidence_guide: str) -> dict[str, Any]:
    cleaned = dict(result or {})
    for key in (
        'answer_for_30b',
        'message_for_30b',
        'summary_for_30b',
        'summary',
        'message',
    ):
        cleaned.pop(key, None)
    guide = str(evidence_guide or '').strip()
    if guide:
        for key in ('content', 'text', 'final'):
            value = cleaned.get(key)
            if isinstance(value, str) and value.strip() == guide:
                cleaned.pop(key, None)
    return cleaned


def deterministic_public_wrapper( public_tool_name: str, original_args: dict[str, Any], internal_tool: str, internal_args: dict[str, Any], dispatcher_result: dict[str, Any], selector_response: dict[str, Any], root: Path) -> dict[str, Any]:
    dispatcher_result = dict(dispatcher_result or {})
    dispatcher_result.setdefault('called_by_vulkan', internal_tool)
    ok = bool(dispatcher_result.get('ok', False))
    summary = summary_from_result(dispatcher_result)
    artifacts = [str(dispatcher_result.get('artifact'))] if dispatcher_result.get('artifact') else []
    answer = dispatcher_result.get('answer_for_30b')
    if not isinstance(answer, str) or not answer.strip():
        answer = summary
    tool_context = dispatcher_result.get('context_for_30b')
    if isinstance(tool_context, dict):
        tool_context = strip_narrative_duplicates_from_context(tool_context)
    else:
        tool_context = {
            'type': 'deterministic_public_wrapper_context',
            'top_level_evidence_guide_field': 'evidence_guide_for_30b',
            'internal_tool': internal_tool,
            'dispatcher_ok': ok,
        }
    selector_message = selector_response.get('message') if isinstance(selector_response.get('message'), dict) else {}
    tool_calls = selector_message.get('tool_calls') if isinstance(selector_message.get('tool_calls'), list) else []
    selector_backend_tool_call = tool_calls[0] if tool_calls else None
    public_dispatcher_result = _strip_dispatcher_narrative_aliases(dispatcher_result, answer)
    return {
        'ok': ok,
        'v6_marker': V6_MARKER,
        'public_tool_name': public_tool_name,
        'original_args': original_args,
        'internal_tool': internal_tool,
        'internal_args': internal_args,
        'selector_response': selector_response,
        'selector_backend_tool_call': selector_backend_tool_call,
        'dispatcher_result': public_dispatcher_result,
        'artifact': dispatcher_result.get('artifact'),
        'artifacts': artifacts,
        'summary': summary,
        'answer_for_30b': answer,
        'context_for_30b': tool_context,
    }


def fail_selector(
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    root: Path,
    selector_response: dict[str, Any],
) -> dict[str, Any]:
    return {
        'ok': False,
        'v6_marker': V6_MARKER,
        'public_tool_name': public_tool_name,
        'original_args': original_args,
        'task': task,
        'root': str(root),
        'selector_response': selector_response,
        'summary': 'Selector did not return a usable internal tool.',
        'answer_for_30b': 'Selector did not return a usable internal tool.',
        'context_for_30b': {
            'type': 'selector_failure_context',
            'selector_ok': False,
            'public_tool_name': public_tool_name,
        },
    }
