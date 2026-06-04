"""Deterministic signatures for planner repo/scratchpad window requests."""
from __future__ import annotations

import json
from typing import Any

from .code_product_state import CODE_PRODUCT_BUILD_STATE_KIND
from .path_tokens import repo_rel_token


REPO_READ_WINDOW_SIGNATURE_KEYS = (
    "line",
    "line_start",
    "start",
    "start_line",
    "end",
    "end_line",
    "offset",
    "limit",
    "line_count",
    "before",
    "after",
    "max_chars",
    "window",
    "chunk",
    "range",
)


def decision_paths(args: dict[str, Any]) -> list[str]:
    args = args if isinstance(args, dict) else {}
    paths: list[str] = []

    def add_item_path(item: Any) -> None:
        if isinstance(item, dict):
            for key in ("path", "file", "filename", "target_file", "target_path"):
                value = item.get(key)
                if value:
                    paths.append(str(value))
        elif isinstance(item, str) and item.strip():
            paths.append(item)

    if isinstance(args.get("paths"), list):
        paths.extend(str(x) for x in args["paths"] if str(x).strip())
    if args.get("path"):
        paths.append(str(args.get("path")))
    if args.get("target_file"):
        paths.append(str(args.get("target_file")))
    if args.get("target_path"):
        paths.append(str(args.get("target_path")))
    if args.get("item"):
        add_item_path(args.get("item"))
    if isinstance(args.get("items"), list):
        for item in args["items"]:
            add_item_path(item)
    out: list[str] = []
    for path in paths:
        n = repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def window_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): window_signature_value(sub)
            for key, sub in sorted(value.items(), key=lambda pair: str(pair[0]))
            if sub not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [window_signature_value(sub) for sub in value]
    try:
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
    except Exception:
        pass
    return value


def repo_read_window_signature(args: dict[str, Any]) -> str:
    args = args if isinstance(args, dict) else {}
    if not any(key in args and args.get(key) not in (None, "", [], {}) for key in REPO_READ_WINDOW_SIGNATURE_KEYS):
        return ""
    payload = {
        "paths": [repo_rel_token(path) for path in decision_paths(args)],
        "window": {
            key: window_signature_value(args.get(key))
            for key in REPO_READ_WINDOW_SIGNATURE_KEYS
            if key in args and args.get(key) not in (None, "", [], {})
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def planner_scratchpad_window_signature(args: dict[str, Any]) -> str:
    args = args if isinstance(args, dict) else {}
    kind = str(args.get("kind") or "")
    document_id = str(args.get("document_id") or args.get("id") or "").strip()
    section = str(args.get("section") or args.get("tag") or "").strip()
    has_window_coordinate = any(
        key in args and args.get(key) not in (None, "", [], {})
        for key in ("offset", "max_chars", "limit", "window", "chunk", "range")
    )
    if kind not in {"prompt_context", "prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND} and not (
        document_id or section or has_window_coordinate
    ):
        return ""
    normalized_kind = CODE_PRODUCT_BUILD_STATE_KIND if kind == CODE_PRODUCT_BUILD_STATE_KIND else "prompt_context_window"
    payload = {
        "kind": normalized_kind,
        "document_id": document_id,
        "section": section,
        "target_file": repo_rel_token(args.get("target_file") or "") if args.get("target_file") else "",
        "offset": window_signature_value(args.get("offset") or 0),
        "max_chars": window_signature_value(args.get("max_chars") or 3000),
        "limit": window_signature_value(args.get("limit") or 3),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def repo_read_window_range_for_target(args: dict[str, Any], target_file: str) -> tuple[int, int] | None:
    args = args if isinstance(args, dict) else {}
    target = repo_rel_token(target_file)
    if target not in {repo_rel_token(path) for path in decision_paths(args)}:
        return None
    if not any(key in args and args.get(key) not in (None, "") for key in ("line", "line_start", "start", "start_line")):
        return None
    try:
        center = int(args.get("line") or args.get("line_start") or args.get("start_line") or args.get("start") or 1)
    except (TypeError, ValueError):
        center = 1
    try:
        before = int(args.get("before") or 0)
    except (TypeError, ValueError):
        before = 0
    try:
        after = int(args.get("after") or args.get("line_count") or 0)
    except (TypeError, ValueError):
        after = 0
    start = max(1, center - max(0, before))
    end = max(start, center + max(0, after))
    return start, end
