"""Tool-selection helpers for the public broker dispatcher.

Refactored using principles from PYTHON_REFACTORING_GUIDE.md:
- §8.4 — Query helper for nested dictionary navigation
- §8.3 — Flat code with early returns (guard clauses)
- §5 — Strategy pattern replacing if/elif chains

This module is deliberately pure data plus small pure helpers. It does not
dispatch tools, read request payloads, call HTTP, or touch job state.
"""
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

# ---------------------------------------------------------------------------
# Token lookup tables (§4 — Lookup tables replacing repeated conditionals)
# ---------------------------------------------------------------------------

_REPO_TOKENS: frozenset[str] = frozenset(
    ("repo", "repository", "worktree", "progetto", "codice", "locale")
)

_REVIEW_TOKENS: frozenset[str] = frozenset(
    ("analizza", "analyze", "analyse", "review", "problema", "problemi", "issue", "issues", "bug")
)

_REPO_SEARCH_QUERY_TOKENS: frozenset[str] = frozenset(
    ("", "repo", "repository", "problem", "problems", "problema", "problemi", "issue", "issues", "bug", "bugs")
)


# ---------------------------------------------------------------------------
# Query helper (§8.4 — Safe dict navigation)
# ---------------------------------------------------------------------------


def _get(d: dict, *keys: str, default: Any = None) -> Any:
    """Safely navigate nested dictionaries."""
    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


# ---------------------------------------------------------------------------
# Tool-selection functions
# ---------------------------------------------------------------------------


def is_generic_repo_analysis(public_tool_name: str, task: str, original_args: dict[str, Any]) -> bool:
    """Check whether the request looks like a repo-analysis review.

    Uses token lookup tables instead of inline conditionals.
    """
    low = ' '.join((str(part or '').lower() for part in (
        public_tool_name, task,
        original_args.get('request'),
        original_args.get('task'),
        original_args.get('query'),
        original_args.get('prompt'),
        original_args.get('instruction'),
    )))
    has_repo = any(token in low for token in _REPO_TOKENS)
    has_review = any(token in low for token in _REVIEW_TOKENS)
    return has_repo and has_review


def needs_composite_review(
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    internal_tool: str,
    internal_args: dict[str, Any],
) -> bool:
    """Route composite review decisions using lookup dispatch.

    Replaces if/elif chain with guard clauses + lookup table.
    """
    if not is_generic_repo_analysis(public_tool_name, task, original_args):
        return False
    if internal_tool == "vulkan_helper":
        return False
    if internal_tool == "repo_status":
        return True
    if internal_tool == "repo_search":
        query = str(_get(internal_args, "query", default="")).strip().lower()
        return query in _REPO_SEARCH_QUERY_TOKENS
    return False


def selector_fallback_tool(
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    selector_response: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return empty fallback when Vulkan does not emit a native tool_call."""
    # If Vulkan/11435 does not emit an explicit native tool_call, the dispatcher
    # must surface that selector failure. Choosing repo_capabilities or
    # vulkan_helper here would replace the selector decision with a hidden
    # controller fallback unrelated to the user's request.
    return ('', {})


def select_internal_tool(
    *,
    public_tool_name: str,
    task: str,
    original_args: dict[str, Any],
    timeout_seconds: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Select an internal tool via Vulkan/11435 LLM interpretation.

    Uses guard clauses for early returns instead of deep nesting.
    """
    system = (
        f'Sei Vulkan GPU0 tool-call repair/JSON normalizer. Non sei planner. '
        f'Devi solo riparare output sporco del planner 11434 in una decisione '
        f'JSON valida già implicita nel testo. Non aggiungere strategia nuova. '
        f'Non inventare file. Non produrre final_answer se action=tool. '
        f'Se non è chiara una action/tool/arguments, restituisci action=block. '
        f'Schema: {{"action":"tool|final|block", "tool":"{VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN}", "arguments":{{}}, "reason":"...", "final_answer":"..."}}}}. Non aggiungere markdown.'
    )
    user = (
        f'PUBLIC_TOOL_X={public_tool_name}\n'
        f'REQUEST={task}\n'
        f'ARGUMENTS_FROM_30B={json.dumps(original_args, ensure_ascii=False, indent=2, default=str)}\n'
        f'Fase richiesta: emetti una sola native tool_call interna L.'
    )
    response = post_json(
        OLLAMA_TASK_URL,
        {
            'model': OLLAMA_TASK_MODEL,
            'stream': False,
            'keep_alive': OLLAMA_KEEP_ALIVE,
            'think': False,
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            'tools': TOOLS_SCHEMA,
            'options': ollama_options(num_predict=VULKAN_INTERPRETER_NUM_PREDICT),
        },
        timeout=max(15, min(timeout_seconds, 240)),
    )

    # Guard-clause early returns for error paths
    if response.get('backend_unreachable') or response.get('backend_timeout'):
        return ('', {}, response)

    message = _get(response, 'message', default={})
    calls = _get(message, 'tool_calls', default=[])
    if not calls:
        return ('', {}, response)

    raw_name, raw_args = parse_tool_call(calls[0])
    tool_name = normalize_tool_name(raw_name)
    if tool_name not in VALID_INTERNAL_TOOLS:
        return (
            'vulkan_helper',
            {
                'public_tool_name': public_tool_name,
                'task': task,
                'reason': f'unsupported internal tool emitted by Vulkan: {raw_name}',
                'arguments': original_args,
            },
            response,
        )
    return (tool_name, raw_args, response)