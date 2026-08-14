"""Tool-selection helpers for the public broker dispatcher."""
from __future__ import annotations

import json
from typing import Any

from .config import (
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    VALID_INTERNAL_TOOLS,
    VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN,
    VULKAN_INTERPRETER_NUM_PREDICT,
    ollama_options,
)
from .planner_core.json_io import post_json
from .tool_contract import TOOLS_SCHEMA, normalize_tool_name, parse_tool_call


def is_generic_repo_analysis(public_tool_name: str, task: str, original_args: dict[str, Any]) -> bool:
    low = ' '.join((str(part or '').lower() for part in (public_tool_name, task, original_args.get('request'), original_args.get('task'), original_args.get('query'), original_args.get('prompt'), original_args.get('instruction'))))
    has_repo = any((token in low for token in ('repo', 'repository', 'worktree', 'progetto', 'codice', 'locale')))
    has_review = any((token in low for token in ('analizza', 'analyze', 'analyse', 'review', 'problema', 'problemi', 'issue', 'issues', 'bug')))
    return has_repo and has_review

def needs_composite_review(public_tool_name: str, task: str, original_args: dict[str, Any], internal_tool: str, internal_args: dict[str, Any]) -> bool:
    if not is_generic_repo_analysis(public_tool_name, task, original_args):
        return False
    if internal_tool == 'vulkan_helper':
        return False
    if internal_tool == 'repo_status':
        return True
    if internal_tool == 'repo_search':
        query = str(internal_args.get('query') or '').strip().lower()
        return query in {'', 'repo', 'repository', 'problem', 'problems', 'problema', 'problemi', 'issue', 'issues', 'bug', 'bugs'}
    return False

def selector_fallback_tool(public_tool_name: str, task: str, original_args: dict[str, Any], selector_response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # If Vulkan/11435 does not emit an explicit native tool_call, the dispatcher
    # must surface that selector failure. Choosing repo_capabilities or
    # vulkan_helper here would replace the selector decision with a hidden
    # controller fallback unrelated to the user's request.
    return ('', {})

def select_internal_tool( public_tool_name: str, task: str, original_args: dict[str, Any], timeout_seconds: int) -> tuple[str, dict[str, Any], dict[str, Any]]:
    system = f'Sei Vulkan GPU0 tool-call repair/JSON normalizer. Non sei planner. Devi solo riparare output sporco del planner 11434 in una decisione JSON valida già implicita nel testo. Non aggiungere strategia nuova. Non inventare file. Non produrre final_answer se action=tool. Se non è chiara una action/tool/arguments, restituisci action=block. Schema: {{"action":"tool|final|block", "tool":"{VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN}", "arguments":{{}}, "reason":"...", "final_answer":"..."}}}}. Non aggiungere markdown.'
    user = f'PUBLIC_TOOL_X={public_tool_name}\nREQUEST={task}\nARGUMENTS_FROM_30B={json.dumps(original_args, ensure_ascii=False, indent=2, default=str)}\nFase richiesta: emetti una sola native tool_call interna L.'
    response = post_json(OLLAMA_TASK_URL, {'model': OLLAMA_TASK_MODEL, 'stream': False, 'keep_alive': OLLAMA_KEEP_ALIVE, 'think': False, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'tools': TOOLS_SCHEMA, 'options': ollama_options(num_predict=VULKAN_INTERPRETER_NUM_PREDICT)}, timeout=max(15, min(timeout_seconds, 240)))
    if response.get('backend_unreachable') or response.get('backend_timeout'):
        return ('', {}, response)
    message = response.get('message') if isinstance(response.get('message'), dict) else {}
    calls = message.get('tool_calls') if isinstance(message.get('tool_calls'), list) else []
    if not calls:
        return ('', {}, response)
    raw_name, raw_args = parse_tool_call(calls[0])
    tool_name = normalize_tool_name(raw_name)
    if tool_name not in VALID_INTERNAL_TOOLS:
        return ('vulkan_helper', {'public_tool_name': public_tool_name, 'task': task, 'reason': f'unsupported internal tool emitted by Vulkan: {raw_name}', 'arguments': original_args}, response)
    return (tool_name, raw_args, response)
