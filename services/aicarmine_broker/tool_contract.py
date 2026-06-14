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


def normalize_tool_name(value: str) -> str:
    name = re.sub("[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return TOOL_ALIASES.get(name, name)


def public_tool(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "function", "operation_id", "requested_function", "bridge_public_tool_x"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "helper_for_all"


def public_args(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("arguments", "parameters", "requested_parameters", "raw_bridge_payload"):
        value = payload.get(key)
        if isinstance(value, dict) and value:
            args = dict(value)
            break
    else:
        args = {}
    if "file" in args and "path" not in args:
        args["path"] = args["file"]
    if "files" in args and "paths" not in args:
        args["paths"] = args["files"]
    if "pattern" in args and "query" not in args:
        args["query"] = args["pattern"]
    if "symbol" in args and "query" not in args:
        args["query"] = args["symbol"]
    return args


def text_from_payload(payload: dict[str, Any], args: dict[str, Any], public_tool_name: str) -> str:
    for source in (payload, args):
        for key in ("request", "task", "query", "prompt", "instruction", "command", "context"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"PUBLIC_TOOL_X={public_tool_name}; ARGUMENTS={compact(args, 4000)}"


def bad_path(value: object) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return True
    low = raw.lower()
    if low in {
        "/path/to/repository",
        "path/to/repository",
        "repository",
        "repo",
        "<repo>",
        "<path>",
        "your/repository/path",
    }:
        return True
    return raw.startswith("/") or ":" in raw or raw.startswith("../") or ("/../" in raw)


def original_text(original_args: dict[str, Any]) -> str:
    for key in ("request", "task", "query", "prompt", "instruction", "context"):
        value = original_args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _paths_from_items(value: object) -> list[str]:
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
        for key in ("path", "file", "filename", "name"):
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.strip():
                paths.append(candidate.strip())
                break
        nested = item.get("paths") or item.get("files")
        if isinstance(nested, list):
            paths.extend(str(path).strip() for path in nested if str(path).strip())
    return paths


def sanitize_tool_args(
    tool_name: str,
    call_args: dict[str, Any],
    original_args: dict[str, Any],
    public_tool_name: str,
) -> dict[str, Any]:
    args = dict(call_args or {})

    # Normalize aliases emitted by local models before falling back to the public
    # request text.
    if "file" in args and "path" not in args:
        args["path"] = args["file"]
    if "files" in args and "paths" not in args:
        args["paths"] = args["files"]
    for alias in ("pattern", "symbol", "needle", "text"):
        if alias in args and "query" not in args:
            args["query"] = args[alias]

    args.setdefault("public_tool_name", public_tool_name)
    args.setdefault("public_tool_x", public_tool_name)
    args.setdefault("original_30b_arguments", original_args)
    if tool_name == "repo_search":
        query = args.get("query")
        if query in (None, ""):
            query = (
                original_args.get("query")
                or original_args.get("pattern")
                or original_args.get("request")
                or original_args.get("task")
                or original_args.get("context")
            )
        if query not in (None, ""):
            args["query"] = str(query)
        args["mode"] = str(args.get("mode") or "rg")
        if bad_path(args.get("path")):
            args["path"] = "."
        args["max_results"] = max(1, min(int(args.get("max_results") or 80), 120))
    elif tool_name == "repo_rg_search":
        if not str(args.get("pattern") or args.get("query") or "").strip():
            query = (
                original_args.get("query")
                or original_args.get("pattern")
                or original_args.get("request")
                or original_args.get("task")
                or original_args.get("context")
            )
            if query not in (None, ""):
                args["query"] = str(query)
        if bad_path(args.get("path")):
            args["path"] = "."
        args["max_results"] = max(1, min(int(args.get("max_results") or args.get("limit") or 80), 1000))
    elif tool_name == "repo_semantic_search":
        query = args.get("query")
        if query in (None, ""):
            query = (
                original_args.get("query")
                or original_args.get("request")
                or original_args.get("task")
                or original_args.get("context")
            )
        if query not in (None, ""):
            args["query"] = str(query)
        if bad_path(args.get("path")):
            args["path"] = "."
    elif tool_name == "repo_read":
        if not args.get("paths") and not args.get("path"):
            item_paths = _paths_from_items(args.get("items") or args.get("item"))
            if item_paths:
                args["paths"] = item_paths
        if bad_path(args.get("path")) and (not args.get("paths")):
            if original_args.get("path") and (not bad_path(original_args.get("path"))):
                args["path"] = original_args.get("path")
            elif original_args.get("paths"):
                args["paths"] = original_args.get("paths")
            else:
                item_paths = _paths_from_items(original_args.get("items") or original_args.get("item"))
                if item_paths:
                    args["paths"] = item_paths
        args.setdefault("max_chars", 20000)
    elif tool_name == "repo_apply_patch":
        if bad_path(args.get("path")) and original_args.get("path") and (not bad_path(original_args.get("path"))):
            args["path"] = original_args.get("path")
        args.setdefault("max_replacements", 1)
    elif tool_name == "repo_write_file":
        if bad_path(args.get("path")) and original_args.get("path") and (not bad_path(original_args.get("path"))):
            args["path"] = original_args.get("path")
        args.setdefault("mode", "overwrite")
        args.setdefault("encoding", "utf-8")
    elif tool_name == "repo_command":
        if not str(args.get("command") or "").strip() and original_args.get("command"):
            args["command"] = original_args.get("command")
    elif tool_name == "vulkan_helper":
        text = original_text(original_args)
        if not str(args.get("task") or "").strip() or str(args.get("task")).strip().lower() in {
            "repo",
            "repository",
            "analyze_repo",
        }:
            args["task"] = text or args.get("task") or ""
        args.setdefault("reason", "public tool X is generic or needs composite local evidence")
        args.setdefault("arguments", original_args)
    return args
