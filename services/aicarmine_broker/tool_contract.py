"""Pure internal tool contract helpers for the broker.

This module owns tool schemas, aliases and argument normalization shared by
``dispatcher`` and ``planner``. It intentionally performs no dispatch, HTTP,
filesystem writes or job state changes.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .repo_tools import compact
from .tool_registry import TOOL_ALIASES as REGISTRY_TOOL_ALIASES
from .tool_registry import TOOLS_SCHEMA as REGISTRY_TOOLS_SCHEMA


TOOLS_SCHEMA: list[dict[str, Any]] = [{'type': 'function', 'function': {'name': 'repo_capabilities', 'description': 'Return available local repo/file tools, when to use them, required arguments, examples and safety policy. Use this when unsure which tool to call.', 'parameters': {'type': 'object', 'properties': {}}}}, {'type': 'function', 'function': {'name': 'repo_status', 'description': 'Read real git status, diff stat, changed files, diff check and stack.', 'parameters': {'type': 'object', 'properties': {}}}}, {'type': 'function', 'function': {'name': 'repo_tree', 'description': 'List repo-relative files and directories under a path. Use for directory structure, module layout, file inventory or key files. Do not use repo_search for directory listing.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'default': '.'}, 'max_depth': {'type': 'integer', 'default': 3}, 'max_files': {'type': 'integer', 'default': 200}}}}}, {'type': 'function', 'function': {'name': 'repo_list_files', 'description': 'List repo-relative files by path, suffix and limit. Use for natural file inventory requests such as first N Python files, core files, or list .py files. Do not use repo_search for glob patterns like *.py.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'default': '.'}, 'suffix': {'type': 'string', 'default': ''}, 'extension': {'type': 'string', 'default': ''}, 'limit': {'type': 'integer', 'default': 20}, 'max_files': {'type': 'integer', 'default': 20}, 'max_depth': {'type': 'integer', 'default': 50}, 'core': {'type': 'boolean', 'default': False}, 'exclude_dirs': {'type': 'array', 'items': {'type': 'string'}}}}}}, {'type': 'function', 'function': {'name': 'repo_search', 'description': 'Search repo code/docs by query/pattern/symbol. Requires query, pattern or symbol.', 'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'pattern': {'type': 'string'}, 'symbol': {'type': 'string'}, 'path': {'type': 'string', 'default': '.'}, 'mode': {'type': 'string', 'enum': ['rg', 'git_grep', 'fd'], 'default': 'rg'}, 'max_results': {'type': 'integer', 'default': 80}}}}}, {'type': 'function', 'function': {'name': 'repo_read', 'description': 'Read one or more repo-relative files. Requires path, paths, item or items.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'paths': {'type': 'array', 'items': {'type': 'string'}}, 'item': {'type': 'object'}, 'items': {'type': 'array', 'items': {'type': 'object'}}, 'max_chars': {'type': 'integer', 'default': 80000}, 'line': {'type': 'integer'}, 'before': {'type': 'integer', 'default': 40}, 'after': {'type': 'integer', 'default': 120}}}}}, {'type': 'function', 'function': {'name': 'repo_apply_patch', 'description': 'Modify one repo-relative file by replacing exact old_text with new_text. Use only when exact old_text is known from repo_read or user input.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'old_text': {'type': 'string'}, 'new_text': {'type': 'string'}, 'max_replacements': {'type': 'integer', 'default': 1}}, 'required': ['path', 'old_text', 'new_text']}}}, {'type': 'function', 'function': {'name': 'repo_write_file', 'description': 'Create, overwrite or append a small repo-relative text file in LAB_REPO. Use for new helper files, tests, docs or generated artifacts. Prefer repo_apply_patch for editing existing source with exact old_text.', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['overwrite', 'create', 'append'], 'default': 'overwrite'}, 'encoding': {'type': 'string', 'default': 'utf-8'}}, 'required': ['path', 'content']}}}, {'type': 'function', 'function': {'name': 'repo_validate', 'description': 'Run standard validation after changes: git diff --check and Python compileall.', 'parameters': {'type': 'object', 'properties': {'commands': {'type': 'array', 'items': {'type': 'string'}}, 'timeout_seconds': {'type': 'integer', 'default': 300}, 'continue_on_failure': {'type': 'boolean', 'default': False}}}}}, {'type': 'function', 'function': {'name': 'repo_command', 'description': 'Run a safe diagnostic command. Requires command. Dangerous commands require explicit consent.', 'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}, 'timeout_seconds': {'type': 'integer', 'default': 120}, 'user_consent': {'type': 'string'}}, 'required': ['command']}}}, {'type': 'function', 'function': {'name': 'terminal_list_files', 'description': 'Windows-aware Open Terminal file listing. Normalizes paths like \\\\Users\\\\carmi\\\\AI\\\\services to C:\\\\Users\\\\carmi\\\\AI\\\\services and returns final structured items.', 'parameters': {'type': 'object', 'properties': {'directory': {'type': 'string'}, 'path': {'type': 'string'}, 'pattern': {'type': 'string', 'default': '*'}, 'recurse': {'type': 'boolean', 'default': False}, 'limit': {'type': 'integer', 'default': 200}}}}}, {'type': 'function', 'function': {'name': 'terminal_search_files', 'description': 'Windows-aware filename/content search under a user directory. Use when native Open Terminal list_files produced Directory not found or when searching user files outside LAB_REPO.', 'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'directory': {'type': 'string'}, 'path': {'type': 'string'}, 'content': {'type': 'boolean', 'default': False}, 'limit': {'type': 'integer', 'default': 200}}, 'required': ['query']}}}, {'type': 'function', 'function': {'name': 'terminal_run_command_wait', 'description': 'Run a Windows PowerShell diagnostic command synchronously and return final stdout/stderr; avoids Open Terminal async null/running semantics and strips ANSI noise.', 'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}, 'cwd': {'type': 'string'}, 'directory': {'type': 'string'}, 'timeout_seconds': {'type': 'integer', 'default': 120}, 'user_consent': {'type': 'string'}}, 'required': ['command']}}}, {'type': 'function', 'function': {'name': 'vulkan_helper', 'description': 'Operational composite helper for generic local repo/helper/multi-task requests.', 'parameters': {'type': 'object', 'properties': {'public_tool_name': {'type': 'string'}, 'task': {'type': 'string'}, 'reason': {'type': 'string'}, 'arguments': {'type': 'object'}}, 'required': ['public_tool_name', 'task', 'reason']}}}]

TOOLS_SCHEMA.extend([
    {
        'type': 'function',
        'function': {
            'name': 'planner_scratchpad_write',
            'description': 'Write a job-scoped planner scratchpad note. This is volatile to the current agent job and is not persistent memory.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'},
                    'content': {'type': 'string'},
                    'kind': {'type': 'string', 'default': 'note'},
                    'tag': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'planner_scratchpad_read',
            'description': 'Read job-scoped planner scratchpad notes. Read-only.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'tag': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 50},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'runtime_sqlite_memory_search',
            'description': 'Search broker-owned persistent SQLite/FTS5 planner memory records. Read-only.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'kind': {'type': 'string'},
                    'tag': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 50},
                    'db': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'runtime_sqlite_memory_write',
            'description': 'Write a broker-owned persistent SQLite/FTS5 planner memory record. Use for durable operational notes only.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string'},
                    'content': {'type': 'string'},
                    'kind': {'type': 'string', 'default': 'planner_note'},
                    'tag': {'type': 'string'},
                    'metadata': {'type': 'object'},
                    'ttl_days': {'type': 'integer'},
                    'pinned': {'type': 'boolean', 'default': False},
                    'db': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'runtime_sqlite_memory_cleanup',
            'description': 'Dry-run or apply cleanup of broker-owned persistent memory records. Defaults to dry-run; apply=true is required to delete.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dry_run': {'type': 'boolean', 'default': True},
                    'apply': {'type': 'boolean', 'default': False},
                    'kind': {'type': 'string'},
                    'tag': {'type': 'string'},
                    'older_than_days': {'type': 'integer'},
                    'expired_only': {'type': 'boolean', 'default': True},
                    'pinned': {'type': 'boolean', 'default': False},
                    'db': {'type': 'string'},
                },
            },
        },
    },
])

TOOL_ALIASES = {
    'capabilities': 'repo_capabilities', 'tool_help': 'repo_capabilities',
    'tools': 'repo_capabilities', 'help_tools': 'repo_capabilities',
    'repo_help': 'repo_capabilities',
    'status': 'repo_status', 'git_status': 'repo_status',
    'get_git_status': 'repo_status', 'diff': 'repo_status', 'git_diff': 'repo_status',
    'analyze_repo': 'repo_status', 'analyze_repository': 'repo_status',
    'find_issues': 'repo_status', 'detect_problems': 'repo_status',
    'search': 'repo_search', 'grep': 'repo_search', 'rg': 'repo_search',
    'search_code': 'repo_search',
    'read': 'repo_read', 'read_file': 'repo_read', 'get_file_content': 'repo_read',
    'apply_patch': 'repo_apply_patch', 'patch': 'repo_apply_patch',
    'patch_file': 'repo_apply_patch', 'edit': 'repo_apply_patch',
    'edit_file': 'repo_apply_patch', 'modify_file': 'repo_apply_patch',
    'write_file': 'repo_write_file', 'repo_write_file': 'repo_write_file',
    'create_file': 'repo_write_file', 'overwrite_file': 'repo_write_file',
    'save_file': 'repo_write_file',
    'validate': 'repo_validate', 'validation': 'repo_validate', 'smoke': 'repo_validate',
    'command': 'repo_command', 'run': 'repo_command', 'compile': 'repo_command',
    'terminal': 'terminal_run_command_wait', 'terminal_command': 'terminal_run_command_wait',
    'run_command_wait': 'terminal_run_command_wait', 'powershell': 'terminal_run_command_wait',
    'terminal_list_files': 'terminal_list_files', 'list_user_files': 'terminal_list_files',
    'terminal_search_files': 'terminal_search_files', 'search_user_files': 'terminal_search_files',
    'scratchpad_write': 'planner_scratchpad_write', 'scratchpad_read': 'planner_scratchpad_read',
    'memory_search': 'runtime_sqlite_memory_search', 'memory_write': 'runtime_sqlite_memory_write',
    'memory_cleanup': 'runtime_sqlite_memory_cleanup',
    'runtime_sqlite_memory': 'runtime_sqlite_memory_search',
    'tree': 'repo_tree', 'repo_tree': 'repo_tree', 'list_dir': 'repo_tree',
    'directory': 'repo_tree', 'directory_structure': 'repo_tree',
    # File inventories must not be normalized to repo_tree: that loses suffix/limit.
    'list_files': 'repo_list_files', 'file_inventory': 'repo_list_files',
    'files': 'repo_list_files', 'find_files': 'repo_list_files',
    'diff_check': 'repo_command',
    'helper': 'vulkan_helper', 'helper_for_all': 'vulkan_helper',
    'help_for_all': 'vulkan_helper',
}

# Registry-owned contract surface. The literals above are retained only as a
# compatibility fallback while this module keeps the sanitize/parsing helpers;
# runtime imports consume the canonical registry values below.
TOOLS_SCHEMA = REGISTRY_TOOLS_SCHEMA
TOOL_ALIASES = REGISTRY_TOOL_ALIASES

def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get('function') if isinstance(call.get('function'), dict) else {}
    name = str(function.get('name') or call.get('name') or '').strip()
    raw_args = function.get('arguments', call.get('arguments', {}))
    if isinstance(raw_args, str):
        try:
            decoded = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            decoded = {}
        raw_args = decoded
    return (name, dict(raw_args or {}) if isinstance(raw_args, dict) else {})

def normalize_tool_name(value: str) -> str:
    name = re.sub('[^a-zA-Z0-9_]+', '_', str(value or '').strip()).strip('_').lower()
    return TOOL_ALIASES.get(name, name)

def public_tool(payload: dict[str, Any]) -> str:
    for key in ('tool_name', 'function', 'operation_id', 'requested_function', 'bridge_public_tool_x'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return 'helper_for_all'

def public_args(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ('arguments', 'parameters', 'requested_parameters', 'raw_bridge_payload'):
        value = payload.get(key)
        if isinstance(value, dict) and value:
            args = dict(value)
            break
    else:
        args = {}
    if 'file' in args and 'path' not in args:
        args['path'] = args['file']
    if 'files' in args and 'paths' not in args:
        args['paths'] = args['files']
    if 'pattern' in args and 'query' not in args:
        args['query'] = args['pattern']
    if 'symbol' in args and 'query' not in args:
        args['query'] = args['symbol']
    return args

def text_from_payload(payload: dict[str, Any], args: dict[str, Any], public_tool_name: str) -> str:
    for source in (payload, args):
        for key in ('request', 'task', 'query', 'prompt', 'instruction', 'command', 'context'):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f'PUBLIC_TOOL_X={public_tool_name}; ARGUMENTS={compact(args, 4000)}'

def bad_path(value: object) -> bool:
    raw = str(value or '').strip().replace('\\', '/')
    if not raw:
        return True
    low = raw.lower()
    if low in {'/path/to/repository', 'path/to/repository', 'repository', 'repo', '<repo>', '<path>', 'your/repository/path'}:
        return True
    return raw.startswith('/') or ':' in raw or raw.startswith('../') or ('/../' in raw)

def original_text(original_args: dict[str, Any]) -> str:
    for key in ('request', 'task', 'query', 'prompt', 'instruction', 'context'):
        value = original_args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''

def _paths_from_items(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str) and item.strip():
            paths.append(item.strip())
        elif isinstance(item, dict):
            for key in ('path', 'file', 'filename', 'name'):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    paths.append(candidate.strip())
                    break
            nested = item.get('paths') or item.get('files')
            if isinstance(nested, list):
                paths.extend(str(p).strip() for p in nested if str(p).strip())
    return paths


def sanitize_tool_args(tool_name: str, call_args: dict[str, Any], original_args: dict[str, Any], public_tool_name: str) -> dict[str, Any]:
    args = dict(call_args or {})

    # Normalize aliases emitted by local models before falling back to the public
    # request text. Without this, e.g. {"pattern": "blender_compat"} was
    # overwritten by the whole user request, and repo_read({"items": ...}) read
    # zero files.
    if 'file' in args and 'path' not in args:
        args['path'] = args['file']
    if 'files' in args and 'paths' not in args:
        args['paths'] = args['files']
    for alias in ('pattern', 'symbol', 'needle', 'text'):
        if alias in args and 'query' not in args:
            args['query'] = args[alias]

    args.setdefault('public_tool_name', public_tool_name)
    args.setdefault('public_tool_x', public_tool_name)
    args.setdefault('original_30b_arguments', original_args)
    if tool_name == 'repo_search':
        query = args.get('query')
        if query in (None, ''):
            query = (
                original_args.get('query') or original_args.get('pattern')
                or original_args.get('request') or original_args.get('task')
                or original_args.get('context')
            )
        if query not in (None, ''):
            args['query'] = str(query)
        args['mode'] = str(args.get('mode') or 'rg')
        if bad_path(args.get('path')):
            args['path'] = '.'
        args['max_results'] = max(1, min(int(args.get('max_results') or 80), 120))
    elif tool_name == 'repo_read':
        if not args.get('paths') and not args.get('path'):
            item_paths = _paths_from_items(args.get('items') or args.get('item'))
            if item_paths:
                args['paths'] = item_paths
        if bad_path(args.get('path')) and (not args.get('paths')):
            if original_args.get('path') and (not bad_path(original_args.get('path'))):
                args['path'] = original_args.get('path')
            elif original_args.get('paths'):
                args['paths'] = original_args.get('paths')
            else:
                item_paths = _paths_from_items(original_args.get('items') or original_args.get('item'))
                if item_paths:
                    args['paths'] = item_paths
        args.setdefault('max_chars', 20000)
    elif tool_name == 'repo_apply_patch':
        if bad_path(args.get('path')) and original_args.get('path') and (not bad_path(original_args.get('path'))):
            args['path'] = original_args.get('path')
        args.setdefault('max_replacements', 1)
    elif tool_name == 'repo_write_file':
        if bad_path(args.get('path')) and original_args.get('path') and (not bad_path(original_args.get('path'))):
            args['path'] = original_args.get('path')
        args.setdefault('mode', 'overwrite')
        args.setdefault('encoding', 'utf-8')
    elif tool_name == 'repo_command':
        if not str(args.get('command') or '').strip() and original_args.get('command'):
            args['command'] = original_args.get('command')
    elif tool_name == 'vulkan_helper':
        text = original_text(original_args)
        if not str(args.get('task') or '').strip() or str(args.get('task')).strip().lower() in {'repo', 'repository', 'analyze_repo'}:
            args['task'] = text or args.get('task') or ''
        args.setdefault('reason', 'public tool X is generic or needs composite local evidence')
        args.setdefault('arguments', original_args)
    return args
