"""Pure internal tool contract helpers for the broker.

This module owns tool aliases and argument normalization shared by
``dispatcher`` and ``planner``. It intentionally performs no dispatch, HTTP,
filesystem writes or job state changes.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .repo_tools import compact
from .tool_registry import TOOL_ALIASES, TOOLS_SCHEMA


# ---------------------------------------------------------------------------
# Query helper for nested dictionary navigation (Guide §8.4)
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
# Tool call parsing
# ---------------------------------------------------------------------------

def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(function.get("name") or call.get("name") or "").strip()
    raw_args = function.get("arguments", call.get("arguments", {}))
    if isinstance(raw_args, str):
        try:
            decoded = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            decoded = {}
        raw_args = decoded
    return (name, dict(raw_args or {}) if isinstance(raw_args, dict) else {})


# ---------------------------------------------------------------------------
# Tool name normalization
# ---------------------------------------------------------------------------

def normalize_tool_name(value: str) -> str:
    name = re.sub("[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return TOOL_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Public tool / args extraction (flat code with early returns)
# ---------------------------------------------------------------------------

def public_tool(payload: dict[str, Any]) -> str:
    """Extract the public tool name from a payload."""
    for key in ("tool_name", "function", "operation_id", "requested_function", "bridge_public_tool_x"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "helper_for_all"


def public_args(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize arguments from a payload."""
    args: dict[str, Any] = {}
    for key in ("arguments", "parameters", "requested_parameters", "raw_bridge_payload"):
        value = payload.get(key)
        if isinstance(value, dict) and value:
            args = dict(value)
            break

    # Normalize common alias pairs
    _alias_pairs = [
        ("file", "path"),
        ("files", "paths"),
        ("pattern", "query"),
        ("symbol", "query"),
    ]
    for src, dst in _alias_pairs:
        if src in args and dst not in args:
            args[dst] = args.pop(src)
    return args


# ---------------------------------------------------------------------------
# Text extraction (flat conditional with lookup table)
# ---------------------------------------------------------------------------

_TEXT_KEYS = ("request", "task", "query", "prompt", "instruction", "command", "context")


def text_from_payload(payload: dict[str, Any], args: dict[str, Any], public_tool_name: str) -> str:
    """Extract human-readable text from payload or arguments."""
    for source in (payload, args):
        for key in _TEXT_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"PUBLIC_TOOL_X={public_tool_name}; ARGUMENTS={compact(args, 4000)}"


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

_INVALID_PATHS = frozenset({
    "/path/to/repository",
    "path/to/repository",
    "repository",
    "repo",
    "<repo>",
    "<path>",
    "your/repository/path",
})


def bad_path(value: object) -> bool:
    """Return True when the value looks like a placeholder or unsafe path."""
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return True
    low = raw.lower()
    if low in _INVALID_PATHS:
        return True
    return raw.startswith("/") or ":" in raw or raw.startswith("../") or ("/../" in raw)


# ---------------------------------------------------------------------------
# Original text extraction (flat code with lookup table)
# ---------------------------------------------------------------------------

def original_text(original_args: dict[str, Any]) -> str:
    """Extract original task/request text from original arguments."""
    for key in _TEXT_KEYS:
        value = original_args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Path extraction from items
# ---------------------------------------------------------------------------

_PATH_KEYS = ("path", "file", "filename", "name")


def _paths_from_items(value: object) -> list[str]:
    """Extract file paths from a mixed items structure."""
    paths: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str) and item.strip():
            paths.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        for key in _PATH_KEYS:
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.strip():
                paths.append(candidate.strip())
                break
        nested = item.get("paths") or item.get("files")
        if isinstance(nested, list):
            paths.extend(str(p).strip() for p in nested if str(p).strip())
    return paths


# ---------------------------------------------------------------------------
# Diagnostics helpers
# ---------------------------------------------------------------------------

def _preview(value: Any, *, limit: int = 300) -> str:
    try:
        return str(value)[:limit]
    except Exception as exc:
        return f"<unstringifiable:{type(exc).__name__}>"


def _diagnostic(
    diagnostics: list[dict[str, Any]],
    reason: str,
    *,
    field: str = "",
    value: Any = None,
) -> None:
    row: dict[str, Any] = {
        "schema": "tool_arg_diagnostic.v1",
        "diagnostic_only": True,
        "reason": reason,
    }
    if field:
        row["field"] = field
    if value is not None:
        row["received_type"] = type(value).__name__
        row["received_preview"] = _preview(value)
    diagnostics.append(row)


def _dict_arg(value: Any, diagnostics: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is not None:
        _diagnostic(diagnostics, "non_object_arguments_replaced", field=field, value=value)
    return {}


def _bounded_int_arg(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
    field: str,
    diagnostics: list[dict[str, Any]],
) -> int:
    selected = default if value is None or (isinstance(value, str) and value == "") else value
    try:
        parsed = int(selected)
    except (TypeError, ValueError, OverflowError):
        _diagnostic(diagnostics, "invalid_integer_argument_defaulted", field=field, value=value)
        parsed = default
    return max(minimum, min(parsed, maximum))


def _attach_tool_arg_diagnostics(args: dict[str, Any], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    if not diagnostics:
        return args
    existing = args.get("tool_arg_diagnostics")
    rows = existing if isinstance(existing, list) else []
    args["tool_arg_diagnostics"] = [*rows, *diagnostics]
    return args


# ---------------------------------------------------------------------------
# Tool-specific sanitizers (extracted from monolithic sanitize_tool_args)
# ---------------------------------------------------------------------------

def _sanitize_repo_search(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_search arguments."""
    query = args.get("query")
    fallback_keys = ("query", "pattern", "request", "task", "context")
    if query in (None, ""):
        for key in fallback_keys:
            candidate = original.get(key)
            if candidate not in (None, ""):
                query = candidate
                break
    if query not in (None, ""):
        args["query"] = str(query)
    args["mode"] = str(args.get("mode") or "rg")
    if bad_path(args.get("path")):
        if args.get("path") not in (None, ""):
            _diagnostic(diagnostics, "invalid_path_defaulted", field="path", value=args.get("path"))
        args["path"] = "."
    args["max_results"] = _bounded_int_arg(
        args.get("max_results"), default=80, minimum=1, maximum=120,
        field="max_results", diagnostics=diagnostics,
    )


def _sanitize_repo_rg_search(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_rg_search arguments."""
    if not str(args.get("pattern") or args.get("query") or "").strip():
        fallback_keys = ("query", "pattern", "request", "task", "context")
        for key in fallback_keys:
            candidate = original.get(key)
            if candidate not in (None, ""):
                args["query"] = str(candidate)
                break
    if bad_path(args.get("path")):
        if args.get("path") not in (None, ""):
            _diagnostic(diagnostics, "invalid_path_defaulted", field="path", value=args.get("path"))
        args["path"] = "."
    args["max_results"] = _bounded_int_arg(
        args.get("max_results") or args.get("limit"), default=80, minimum=1, maximum=1000,
        field="max_results", diagnostics=diagnostics,
    )


def _sanitize_repo_semantic_search(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_semantic_search arguments."""
    query = args.get("query")
    fallback_keys = ("query", "request", "task", "context")
    if query in (None, ""):
        for key in fallback_keys:
            candidate = original.get(key)
            if candidate not in (None, ""):
                query = candidate
                break
    if query not in (None, ""):
        args["query"] = str(query)
    if bad_path(args.get("path")):
        if args.get("path") not in (None, ""):
            _diagnostic(diagnostics, "invalid_path_defaulted", field="path", value=args.get("path"))
        args["path"] = "."


def _sanitize_repo_read(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_read arguments."""
    if not args.get("paths") and not args.get("path"):
        item_paths = _paths_from_items(args.get("items") or args.get("item"))
        if item_paths:
            args["paths"] = item_paths
    if bad_path(args.get("path")) and (not args.get("paths")):
        if args.get("path") not in (None, ""):
            _diagnostic(diagnostics, "invalid_path_repaired", field="path", value=args.get("path"))
        if original.get("path") and (not bad_path(original.get("path"))):
            args["path"] = original.get("path")
        elif original.get("paths"):
            args["paths"] = original.get("paths")
        else:
            item_paths = _paths_from_items(original.get("items") or original.get("item"))
            if item_paths:
                args["paths"] = item_paths

    bounds = [
        ("max_chars", 20000, 1, 200000),
        ("max_paths", 200, 1, 200),
        ("before", 40, 0, 1000),
        ("after", 120, 0, 1000),
    ]
    for field, default, minimum, maximum in bounds:
        args[field] = _bounded_int_arg(
            args.get(field), default=default, minimum=minimum, maximum=maximum,
            field=field, diagnostics=diagnostics,
        )


def _sanitize_repo_apply_patch(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_apply_patch arguments."""
    if bad_path(args.get("path")) and original.get("path") and (not bad_path(original.get("path"))):
        _diagnostic(diagnostics, "invalid_path_repaired", field="path", value=args.get("path"))
        args["path"] = original.get("path")
    args.setdefault("max_replacements", 1)


def _sanitize_repo_write_file(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_write_file arguments."""
    if bad_path(args.get("path")) and original.get("path") and (not bad_path(original.get("path"))):
        _diagnostic(diagnostics, "invalid_path_repaired", field="path", value=args.get("path"))
        args["path"] = original.get("path")
    args.setdefault("mode", "overwrite")
    args.setdefault("encoding", "utf-8")


def _sanitize_repo_command(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize repo_command arguments."""
    if not str(args.get("command") or "").strip() and original.get("command"):
        args["command"] = original.get("command")


def _sanitize_vulkan_helper(
    args: dict[str, Any],
    original: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Sanitize vulkan_helper arguments."""
    text = original_text(original)
    task = str(args.get("task") or "").strip().lower()
    if not str(args.get("task") or "").strip() or task in {"repo", "repository", "analyze_repo"}:
        args["task"] = text or args.get("task") or ""
    args.setdefault("reason", "public tool X is generic or needs composite local evidence")
    args.setdefault("arguments", original)


# Tool-specific sanitizer dispatch table (Guide §4 - Replace conditional with strategy object)
_TOOL_SANITIZERS: dict[str, callable] = {
    "repo_search": _sanitize_repo_search,
    "repo_rg_search": _sanitize_repo_rg_search,
    "repo_semantic_search": _sanitize_repo_semantic_search,
    "repo_read": _sanitize_repo_read,
    "repo_apply_patch": _sanitize_repo_apply_patch,
    "repo_write_file": _sanitize_repo_write_file,
    "repo_command": _sanitize_repo_command,
    "vulkan_helper": _sanitize_vulkan_helper,
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def sanitize_tool_args(
    tool_name: str,
    call_args: dict[str, Any],
    original_args: dict[str, Any],
    public_tool_name: str,
) -> dict[str, Any]:
    """Sanitize and normalize tool arguments for execution.

    Extracts common aliases, applies tool-specific defaults, and collects
    diagnostics. Uses a dispatch table instead of a large if/elif chain.
    """
    diagnostics: list[dict[str, Any]] = []
    args = _dict_arg(call_args, diagnostics, "call_args")
    original = _dict_arg(original_args, diagnostics, "original_args")

    # Normalize common alias pairs (file→path, files→paths, pattern/symbol→query)
    _alias_pairs = [
        ("file", "path"),
        ("files", "paths"),
    ]
    for src, dst in _alias_pairs:
        if src in args and dst not in args:
            args[dst] = args.pop(src)

    # Expand query aliases from original args
    for alias in ("pattern", "symbol", "needle", "text"):
        if alias in args and "query" not in args:
            args["query"] = args[alias]

    args.setdefault("public_tool_name", public_tool_name)
    args.setdefault("public_tool_x", public_tool_name)
    args.setdefault("original_30b_arguments", original)

    # Dispatch to tool-specific sanitizer
    sanitizer = _TOOL_SANITIZERS.get(tool_name)
    if sanitizer:
        sanitizer(args, original, diagnostics)

    return _attach_tool_arg_diagnostics(args, diagnostics)
