"""Planner-facing tool result compaction policy."""
from __future__ import annotations

import ast
from typing import Any

from ..infrastructure.result_compaction import compact
from .prompt_context_windows import compact_prompt_context_window_item


def compact_list_preview(value: Any, *, limit: int = 120) -> tuple[list[Any], int]:
    if not isinstance(value, list):
        return [], 0
    return value[:limit], len(value)


def python_static_evidence(path: str, content: str) -> dict[str, Any]:
    """Extract bounded, factual Python evidence for the planner."""
    evidence: dict[str, Any] = {"path": path}
    text = str(content or "")
    evidence["line_count"] = len(text.splitlines())
    evidence["todo_fixme_count"] = sum(
        1 for line in text.splitlines() if "todo" in line.lower() or "fixme" in line.lower()
    )
    try:
        tree = ast.parse(text)
    except Exception as exc:
        evidence.update({
            "parse_ok": False,
            "parse_error_type": type(exc).__name__,
            "parse_error": str(exc)[:300],
        })
        return evidence

    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    public_functions_missing_return_annotation = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name and alias.name not in imports:
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                mod = "." * int(node.level) + mod
            if mod and mod not in imports:
                imports.append(mod)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if not node.name.startswith("_") and node.returns is None:
                public_functions_missing_return_annotation += 1

    evidence.update({
        "parse_ok": True,
        "module_docstring": bool(ast.get_docstring(tree)),
        "imports": imports[:30],
        "classes": classes[:30],
        "functions": functions[:60],
        "top_level_defs_total": len(classes) + len(functions),
        "public_functions_missing_return_annotation": public_functions_missing_return_annotation,
    })
    flags: list[str] = []
    if not evidence["module_docstring"] and (classes or functions):
        flags.append("missing_module_docstring")
    if evidence["todo_fixme_count"]:
        flags.append("todo_or_fixme_present")
    if evidence["line_count"] > 800:
        flags.append("long_file")
    if public_functions_missing_return_annotation:
        flags.append("public_functions_without_return_annotation")
    evidence["evidence_flags"] = flags
    return evidence


def summary_from_result(result: dict[str, Any]) -> str:
    tool = str(result.get("tool") or "")
    if tool == "repo_tree":
        return (
            f"repo_tree path={result.get('path')} count={result.get('count')} "
            f"truncated={result.get('truncated')} artifact={result.get('artifact')}"
        )
    if tool == "repo_list_files":
        return (
            f"repo_list_files path={result.get('path')} suffix={result.get('suffix')} "
            f"total_matches={result.get('total_matches')} limit={result.get('limit')} "
            f"truncated={result.get('truncated')} artifact={result.get('artifact')}"
        )
    if tool == "repo_search":
        matches = result.get("matches") if isinstance(result.get("matches"), list) else []
        return (
            f"repo_search query={result.get('query')} matches={len(matches)} "
            f"returncode={result.get('returncode')} artifact={result.get('artifact')}"
        )
    if tool == "repo_read":
        items = result.get("items") if isinstance(result.get("items"), list) else []
        paths = [str(x.get("path")) for x in items[:8] if isinstance(x, dict) and x.get("path")]
        return f"repo_read items={len(items)} paths={paths} artifact={result.get('artifact')}"
    if tool == "repo_propose_code_edit":
        return (
            f"repo_propose_code_edit target={result.get('target_file')} "
            f"edit_kind={result.get('edit_kind')} ok={result.get('ok')} "
            f"errors={result.get('errors')} artifact={result.get('artifact')}"
        )
    for key in ("answer_for_30b", "context_for_30b", "summary", "content",
                "text", "message", "stdout_tail"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return compact(result, 2000)


def compact_tool_result_for_planner(
    tool: str,
    result: dict[str, Any],
    *,
    result_compact_chars: int,
) -> dict[str, Any]:
    """Return a planner-safe digest, never the full raw tool result."""
    payload: dict[str, Any] = {
        "tool": tool,
        "ok": bool(result.get("ok")),
        "summary": summary_from_result(result)[:result_compact_chars],
    }

    if tool == "repo_propose_code_edit":
        for key in (
            "kind", "target_file", "edit_kind", "rationale",
            "source_writes_performed", "patch_application_performed",
            "manual_review_required", "validation_commands",
            "unified_diff", "structured_operations", "errors", "warnings",
            "target_metadata", "ast_evidence", "artifact",
        ):
            if result.get(key) not in (None, "", [], {}):
                payload[key] = result.get(key)
        return payload

    if tool == "planner_scratchpad_read" and str(result.get("mode") or "") in {"prompt_context_window", "code_product_build_state"}:
        for key in ("mode", "count", "artifact", "error", "details"):
            if result.get(key) not in (None, "", [], {}):
                payload[key] = result.get(key)
        for key in ("schema", "kind", "target_file", "status", "complete_payload_ready", "state_parse_error"):
            if result.get(key) not in (None, "", [], {}):
                payload[key] = result.get(key)
        items = result.get("items") if isinstance(result.get("items"), list) else []
        payload["items"] = [
            compact_prompt_context_window_item(item)
            for item in items
            if isinstance(item, dict)
        ]
        payload["items_total"] = len(items)
        return payload

    scalar_keys = (
        "path", "paths", "count", "total_matches", "limit", "suffix",
        "truncated", "returncode", "stderr_tail", "stdout_tail", "artifact",
        "changed", "replacements", "line_count_before", "line_count_after",
        "command", "query", "mode", "success_count", "failed_count", "all_ok",
        "max_paths", "requested_limit", "db", "record_id", "expires_at",
        "dry_run", "written", "deleted_count", "schema", "document_id",
        "section", "target_file", "status", "complete_payload_ready", "sha256",
    )
    for key in scalar_keys:
        if key not in result:
            continue
        value = result.get(key)
        if isinstance(value, str):
            payload[key] = value[:result_compact_chars]
        elif isinstance(value, (int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, list):
            preview, total = compact_list_preview(value, limit=120)
            payload[key] = preview
            payload[f"{key}_total"] = total
        elif isinstance(value, dict):
            payload[key] = {
                str(k): (str(v)[:700] if isinstance(v, str) else v)
                for k, v in value.items()
                if v not in (None, "", [], {})
            }

    for key in ("entries", "matches", "files", "paths"):
        value = result.get(key)
        if isinstance(value, list):
            preview, total = compact_list_preview(value, limit=120)
            payload[f"{key}_preview"] = preview
            payload[f"{key}_total"] = total

    if isinstance(result.get("items"), list):
        items = result.get("items", [])
        compact_items: list[dict[str, Any]] = []
        python_evidence: list[dict[str, Any]] = []
        for item in items[:120]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            content = str(item.get("content") or "")
            compact_item = {
                "ok": item.get("ok"),
                "id": item.get("id"),
                "kind": item.get("kind"),
                "tag": item.get("tag"),
                "path": path,
                "line_count": item.get("line_count"),
                "truncated": item.get("truncated"),
                "artifact": item.get("artifact"),
                "error": item.get("error"),
                "error_type": item.get("error_type"),
            }
            if content:
                compact_item["content_preview"] = content[:700]
            text = str(item.get("text") or "")
            if text:
                compact_item["text_preview"] = text[:700]
            compact_items.append({k: v for k, v in compact_item.items() if v not in (None, "", [], {})})
            if path.endswith(".py") and item.get("ok"):
                python_evidence.append(python_static_evidence(path, content))
        payload["items"] = compact_items
        payload["items_total"] = len(items)
        if python_evidence:
            payload["python_static_evidence"] = python_evidence
            payload["python_static_evidence_total"] = len(python_evidence)
    return payload
