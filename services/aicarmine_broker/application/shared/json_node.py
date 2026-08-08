"""Structured JSON node builders for job_html.py helpers.

Extracted from the ~2700-line job_html.py module to reduce complexity.
All functions return dicts compatible with render_json_section / render_json_page.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def json_node_from_path(path: Path, *, max_chars: int = 50000) -> dict[str, Any]:
    """Read a JSON file and return a structured node dict."""
    if not path.exists() or not path.is_file():
        return {"available": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {
            "available": False,
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    truncated = len(text) > max_chars
    return {
        "available": True,
        "path": str(path),
        "content": text[:max_chars] + ("... <truncated>" if truncated else ""),
        "truncated": truncated,
        "size_bytes": path.stat().st_size,
    }


def json_node_from_data(data: Any, *, max_chars: int = 50000) -> dict[str, Any]:
    """Convert arbitrary data to a structured JSON node dict."""
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        return {
            "available": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "data_type": type(data).__name__,
        }
    truncated = len(text) > max_chars
    return {
        "available": True,
        "content": text[:max_chars] + ("... <truncated>" if truncated else ""),
        "truncated": truncated,
        "size_bytes": len(text.encode("utf-8")),
    }


def json_node_summary(data: dict[str, Any], *, keys: int = 20) -> dict[str, Any]:
    """Build a summary node showing top-level keys and value types."""
    if not isinstance(data, dict):
        return {"available": False, "error": "not_a_dict"}
    key_types: list[dict[str, str]] = []
    for key in sorted(data.keys())[:keys]:
        value = data[key]
        key_types.append({
            "key": key,
            "type": type(value).__name__,
            "has_content": bool(value) and value not in (None, "", [], {}),
        })
    return {
        "available": True,
        "total_keys": len(data),
        "sampled_keys": keys,
        "key_types": key_types,
    }


def json_node_nested(data: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """Navigate nested dictionary by path list and return node."""
    current: Any = data
    for segment in path:
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            try:
                idx = int(segment)
                current = current[idx] if 0 <= idx < len(current) else None
            except (ValueError, IndexError):
                return {"available": False, "error": f"invalid_index:{segment}"}
        else:
            return {"available": False, "error": f"unexpected_type:{type(current).__name__}"}
    return json_node_from_data(current) if current is not None else {"available": False, "error": "null_value"}