"""
aicarmine_broker.planner
========================
The controlled 30B planner loop.

Responsibilities:
- Post requests to 11434 (PLANNER_URL) with streaming
- Detect degenerate / role-boundary-contaminated output
- Ask Vulkan/GPU0 11435 for explicit IA repair when planner output is malformed or a tool decision is invalid
- Run the multi-step agentic loop ``run_agentic_planner_job``
- Manage job lifecycle transitions

No FastAPI routes or HTTP server code here.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import time
import traceback
from pathlib import Path
from typing import Any

from .config import (
    AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT,
    AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
    AGENTIC_PLANNER_NATIVE_TOOLS,
    AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS,
    AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_NUM_CTX_REQUESTED,
    AGENTIC_PLANNER_NUM_PREDICT,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
    AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    AGENTIC_RESULT_COMPACT_CHARS,
    AGENTIC_PLANNER_TEMPERATURE,
    AGENT_DEFAULT_MAX_STEPS,
    AGENT_MAX_STEPS,
    LAB_REPO,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    PLANNER_MODEL,
    PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
    PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
    PLANNER_INTRINSIC_RAG_TOP_K,
    PLANNER_RAG_DB,
    PLANNER_RAG_EMBEDDING_BATCH_SIZE,
    PLANNER_RAG_EXTERNAL_RERANKER_URL,
    PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
    PLANNER_RAG_RERANKING_ENGINE,
    PLANNER_RAG_RERANKING_MODEL,
    PLANNER_URL,
    VALID_INTERNAL_TOOLS,
    internal_tool_prompt,
    internal_tools_list,
    ollama_options,
)
from .job_store import (
    agent_job_planner_stream_path,
    agent_job_root,
    append_agent_event,
    load_agent_job_state,
    write_agent_job_state,
    write_json,
)
from .memory_tools import (
    planner_composed_answer,
    planner_memory_surface,
    planner_prompt_context_store_window,
    runtime_sqlite_memory_write,
)
from .code_edit_proposal_contract import validate_unified_diff_text
from .planner_intrinsic_context import build_planner_intrinsic_context
from .repo_tools import compact, safe_rel_path, terminal_environment_contract


# ---------------------------------------------------------------------------
# Planner JSON/HTTP helpers
# ---------------------------------------------------------------------------

from .planner_core.json_io import (
    _parse_strict_json_object,
    post_json,
    post_json_stream_to_file,
)
from .application.decision_normalizer import (
    _final_answer_from_content_field,
    _native_tool_calls_decision,
    _normalize_final_answer_from_content,
    _normalize_final_answer_lines,
    _normalize_terminal_planner_decision,
    _single_embedded_json_decision,
    normalize_planner_decision,
)
from .application.goal_classifier import (
    final_answer_has_inline_code_product as _final_answer_has_inline_code_product,
    final_answer_is_action_plan_without_code_product as _final_answer_is_action_plan_without_code_product,
    goal_is_tool_envelope as _goal_is_tool_envelope,
    goal_requests_apply,
    goal_requests_code_product,
    has_any as _has_any,
    input_error_goal as _input_error_goal,
    semantic_goal_classification as _classify_goal_deliverable,
    semantic_goal_low as _semantic_goal_low,
    semantic_goal_text as _semantic_goal_text,
)
from .application.path_tokens import repo_rel_token as _repo_rel_token


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


def _compact_list_preview(value: Any, *, limit: int = 120) -> tuple[list[Any], int]:
    if not isinstance(value, list):
        return [], 0
    return value[:limit], len(value)


def _python_static_evidence(path: str, content: str) -> dict[str, Any]:
    """Extract bounded, factual Python evidence for the planner.

    This does not decide the final answer. It gives the planner usable evidence
    for many-file reviews without hiding the fact that repo_read was the source.
    """
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


_PROMPT_CONTEXT_WINDOW_COMPACT_KEYS = (
    "document_id",
    "section",
    "store",
    "metadata",
    "window_start",
    "window_end",
    "full_chars",
    "window_chars",
    "complete",
    "has_more_before",
    "has_more_after",
    "sha256",
    "window_sha256",
    "text",
)

_PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS = (
    "document_id",
    "section",
    "window_start",
    "window_end",
    "full_chars",
    "window_chars",
    "complete",
    "has_more_before",
    "has_more_after",
    "sha256",
    "window_sha256",
    "text",
)


def _compact_prompt_context_window_item(item: dict[str, Any]) -> dict[str, Any]:
    compact_item: dict[str, Any] = {}
    for key in _PROMPT_CONTEXT_WINDOW_COMPACT_KEYS:
        if key not in item:
            continue
        value = item.get(key)
        if value in (None, "", [], {}):
            continue
        compact_item[key] = str(value) if key == "text" else value
    if "window_sha256" not in compact_item and compact_item.get("text"):
        compact_item["window_sha256"] = _text_hash(str(compact_item.get("text") or ""))
    return compact_item


def compact_tool_result_for_planner(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return a planner-safe digest, never the full raw tool result.

    The digest must be large enough to preserve the evidence needed by the next
    planner step. Earlier versions truncated file lists to 30 and read items to
    5, which caused requests such as "first 50 files" to lose context and made
    the planner appear to use hard-coded counts.
    """
    payload: dict[str, Any] = {
        "tool": tool,
        "ok": bool(result.get("ok")),
        "summary": _summary_from_result(result)[:AGENTIC_RESULT_COMPACT_CHARS],
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
            _compact_prompt_context_window_item(item)
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
            payload[key] = value[:AGENTIC_RESULT_COMPACT_CHARS]
        elif isinstance(value, (int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, list):
            preview, total = _compact_list_preview(value, limit=120)
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
            preview, total = _compact_list_preview(value, limit=120)
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
                python_evidence.append(_python_static_evidence(path, content))
        payload["items"] = compact_items
        payload["items_total"] = len(items)
        if python_evidence:
            payload["python_static_evidence"] = python_evidence
            payload["python_static_evidence_total"] = len(python_evidence)
    return payload

def _summary_from_result(result: dict[str, Any]) -> str:
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
        v = result.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return compact(result, 2000)


def planner_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = _history_tool_result(item)
        row: dict[str, Any] = {
            "step": item.get("step"),
            "action": decision.get("action"),
            "tool": result.get("tool") or decision.get("tool"),
            "ok": result.get("ok"),
            "reason": str(decision.get("reason") or "")[:900],
            "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else None,
            "path": result.get("path"),
            "count": result.get("count"),
            "total_matches": result.get("total_matches"),
            "limit": result.get("limit"),
            "suffix": result.get("suffix"),
            "returncode": result.get("returncode"),
            "artifact": result.get("artifact"),
            "substep": item.get("substep"),
            "db": result.get("db"),
            "record_id": result.get("record_id"),
            "dry_run": result.get("dry_run"),
            "guard_type": result.get("guard_type"),
            "violations": result.get("violations"),
            "classification": result.get("classification"),
            "next_instruction": result.get("next_instruction"),
            "raw_planner_text_preview": result.get("raw_planner_text_preview"),
            "cache_hit": result.get("cache_hit"),
            "cache_key": result.get("cache_key"),
            "cached_from_step": result.get("cached_from_step"),
            "cached_from_artifact": result.get("cached_from_artifact"),
            "repair_cache_hit": result.get("repair_cache_hit"),
            "repair_cache_key": result.get("repair_cache_key"),
            "native_tool_call": decision.get("native_tool_call"),
            "native_tool_calls_seen": decision.get("native_tool_calls_seen"),
            "ollama_turn": _history_item_ollama_turn(item),
        }
        if result.get("tool") == "repo_propose_code_edit":
            for key in (
                "kind", "target_file", "edit_kind", "rationale",
                "source_writes_performed", "patch_application_performed",
                "manual_review_required", "validation_commands",
                "unified_diff", "structured_operations", "errors", "warnings",
                "target_metadata", "ast_evidence",
            ):
                if result.get(key) not in (None, "", [], {}):
                    row[key] = result.get(key)
        for key in ("paths_preview", "files_preview", "entries_preview", "matches_preview"):
            if isinstance(result.get(key), list):
                row[key] = result.get(key)[:120]
        for key in ("paths_total", "files_total", "entries_total", "matches_total", "items_total"):
            if result.get(key) not in (None, "", [], {}):
                row[key] = result.get(key)
        if isinstance(result.get("matches"), list):
            row["match_count"] = len(result["matches"])
            row["matches_preview"] = result["matches"][:20]
        if isinstance(result.get("items"), list):
            if result.get("tool") == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
                row["mode"] = result.get("mode")
                row["items"] = [
                    _compact_prompt_context_window_item(sub)
                    for sub in result["items"][:120]
                    if isinstance(sub, dict)
                ]
            else:
                row["items"] = [
                    {"ok": sub.get("ok"), "id": sub.get("id"), "kind": sub.get("kind"),
                     "tag": sub.get("tag"), "path": sub.get("path"),
                     "line_count": sub.get("line_count"), "truncated": sub.get("truncated"),
                     "artifact": sub.get("artifact"),
                     "error": sub.get("error"),
                     "content_preview": str(sub.get("content") or sub.get("content_preview") or "")[:700],
                     "text_preview": str(sub.get("text") or sub.get("text_preview") or "")[:700]}
                    for sub in result["items"][:120]
                    if isinstance(sub, dict)
                ]
        if isinstance(result.get("python_static_evidence"), list):
            row["python_static_evidence"] = result.get("python_static_evidence")[:120]
            row["python_static_evidence_total"] = result.get("python_static_evidence_total")
        if isinstance(result.get("evidence_contract"), dict):
            row["evidence_contract"] = result.get("evidence_contract")
        if isinstance(result.get("vulkan_repair"), dict):
            repair = result.get("vulkan_repair") or {}
            row["vulkan_repair"] = {
                k: repair.get(k)
                for k in (
                    "ok", "error", "repair_cache_key", "repair_cache_hit",
                    "cached_from_step", "raw_planner_text_preview",
                )
                if repair.get(k) not in (None, "", [], {})
            }
        ledger.append({k: v for k, v in row.items() if v not in (None, "", [], {})})
    return ledger


def planner_last_result_digest(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    digest = {
        "tool": result.get("tool"), "ok": result.get("ok"),
        "path": result.get("path"), "count": result.get("count"),
        "total_matches": result.get("total_matches"), "limit": result.get("limit"),
        "suffix": result.get("suffix"), "returncode": result.get("returncode"),
        "artifact": result.get("artifact"),
        "guard_type": result.get("guard_type"),
        "cache_hit": result.get("cache_hit"),
        "cache_key": result.get("cache_key"),
        "cached_from_step": result.get("cached_from_step"),
        "cached_from_artifact": result.get("cached_from_artifact"),
        "repair_cache_hit": result.get("repair_cache_hit"),
        "repair_cache_key": result.get("repair_cache_key"),
        "violations": result.get("violations"),
        "stderr_tail": str(result.get("stderr_tail") or "")[:1200],
        "stdout_tail": str(result.get("stdout_tail") or "")[:1200],
    }
    if result.get("tool") == "repo_propose_code_edit":
        for key in (
            "kind", "target_file", "edit_kind", "rationale",
            "source_writes_performed", "patch_application_performed",
            "manual_review_required", "validation_commands",
            "unified_diff", "structured_operations", "errors", "warnings",
            "target_metadata", "ast_evidence",
        ):
            if result.get(key) not in (None, "", [], {}):
                digest[key] = result.get(key)
        return {k: v for k, v in digest.items() if v not in (None, "", [], {})}
    for key in ("paths_preview", "files_preview", "entries_preview", "matches_preview"):
        if isinstance(result.get(key), list):
            digest[key] = result.get(key)[:120]
    for key in ("paths_total", "files_total", "entries_total", "matches_total", "items_total"):
        if result.get(key) not in (None, "", [], {}):
            digest[key] = result.get(key)
    if isinstance(result.get("matches"), list):
        digest["match_count"] = len(result["matches"])
        digest["matches_preview"] = result["matches"][:20]
    if isinstance(result.get("items"), list):
        if result.get("tool") == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
            digest["mode"] = result.get("mode")
            digest["items"] = [
                _compact_prompt_context_window_item(x)
                for x in result["items"][:120]
                if isinstance(x, dict)
            ]
        else:
            digest["items"] = [
                {"ok": x.get("ok"), "id": x.get("id"), "kind": x.get("kind"),
                 "tag": x.get("tag"), "path": x.get("path"),
                 "line_count": x.get("line_count"), "truncated": x.get("truncated"),
                 "artifact": x.get("artifact"),
                 "error": x.get("error"),
                 "content_preview": str(x.get("content") or x.get("content_preview") or "")[:700],
                 "text_preview": str(x.get("text") or x.get("text_preview") or "")[:700]}
                for x in result["items"][:120]
                if isinstance(x, dict)
            ]
    if isinstance(result.get("python_static_evidence"), list):
        digest["python_static_evidence"] = result.get("python_static_evidence")[:120]
        digest["python_static_evidence_total"] = result.get("python_static_evidence_total")
    if isinstance(result.get("evidence_contract"), dict):
        digest["evidence_contract"] = result.get("evidence_contract")
    if isinstance(result.get("vulkan_repair"), dict):
        repair = result.get("vulkan_repair") or {}
        digest["vulkan_repair"] = {
            k: repair.get(k)
            for k in (
                "ok", "error", "repair_cache_key", "repair_cache_hit",
                "cached_from_step", "raw_planner_text_preview",
            )
            if repair.get(k) not in (None, "", [], {})
        }
    return {k: v for k, v in digest.items() if v not in (None, "", [], {})}


def _json_char_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def _prompt_clip_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "")
    max_chars = int(limit or AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 40)] + "... <prompt_preview_truncated>"


def _prompt_clip_value(value: Any, *, text_limit: int | None = None, list_limit: int = 12, depth: int = 0) -> Any:
    if depth > 4:
        return _prompt_clip_text(value, text_limit)
    if isinstance(value, str):
        return _prompt_clip_text(value, text_limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        out = [
            _prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit, depth=depth + 1)
            for item in value[:list_limit]
        ]
        if len(value) > list_limit:
            out.append({"omitted_items_for_prompt": len(value) - list_limit})
        return out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            if key in {"content", "content_preview", "content_excerpt", "text", "text_preview", "stdout", "stderr", "raw_planner_text_preview"}:
                out[key] = _prompt_clip_text(item, text_limit)
            elif key == "unified_diff":
                diff_text = str(item or "")
                out["unified_diff_present"] = bool(diff_text.strip())
                out["unified_diff_chars"] = len(diff_text)
                out["unified_diff_markers_present"] = all(marker in diff_text for marker in ("---", "+++", "@@"))
            elif key == "structured_operations":
                ops = item if isinstance(item, list) else []
                out["structured_operations_present"] = bool(ops)
                out["structured_operations_count"] = len(ops)
            else:
                out[str(key)] = _prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit, depth=depth + 1)
        return out
    return _prompt_clip_text(value, text_limit)


def _compact_tool_manifest_for_prompt(tool_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for tool in tool_manifest:
        params = tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {}
        properties = params.get("properties") if isinstance(params.get("properties"), dict) else {}
        argument_contract = tool.get("argument_contract") if isinstance(tool.get("argument_contract"), dict) else {}
        description_limit = 700 if argument_contract else 180
        row: dict[str, Any] = {
            "name": tool.get("name"),
            "description": _prompt_clip_text(tool.get("description"), description_limit),
            "required": params.get("required") if isinstance(params.get("required"), list) else [],
            "properties": list(properties.keys()),
        }
        any_of = params.get("anyOf") if isinstance(params.get("anyOf"), list) else []
        if any_of:
            row["schema_any_of"] = any_of
        if argument_contract:
            row["argument_contract"] = argument_contract
        compacted.append(
            row
        )
    return compacted


def _tool_schema_name(item: dict[str, Any]) -> str:
    function = item.get("function") if isinstance(item, dict) else {}
    return str(function.get("name") or "").strip() if isinstance(function, dict) else ""


def _ordered_tool_names(names: set[str]) -> list[str]:
    ordered = [name for name in internal_tools_list(exclude_vulkan=False) if name in names]
    ordered.extend(sorted(name for name in names if name not in ordered))
    return ordered


def _filter_tool_manifest_for_names(
    tool_manifest: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    allowed = {str(name) for name in allowed_names if str(name).strip()}
    if not allowed:
        return []
    return [
        item
        for item in tool_manifest
        if str(item.get("name") or "") in allowed
    ]


def _native_tools_schema_for_planner(
    tools_schema: list[dict[str, Any]],
    allowed_names: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Return the provider-native Ollama schema for this turn.

    The provider schema stays canonical: function name, brief description and
    JSON Schema parameters. Internal argument contracts stay in the planner
    payload/evidence contract; appending them here bloats the native ``tools``
    section and makes small-context turns optimize for the wrong surface.
    """
    filter_enabled = allowed_names is not None
    allowed = {str(name) for name in allowed_names or [] if str(name).strip()}
    native_schema: list[dict[str, Any]] = []
    for source_item in tools_schema:
        name = _tool_schema_name(source_item)
        if filter_enabled and name not in allowed:
            continue
        item = copy.deepcopy(source_item)
        function = item.get("function") if isinstance(item, dict) else {}
        if not isinstance(function, dict):
            continue
        function.pop("argument_contract", None)
        function["description"] = _prompt_clip_text(function.get("description"), 420)
        native_schema.append(item)
    return native_schema


def _intrinsic_context_declares_selective_memory_gap(intrinsic_context: dict[str, Any]) -> bool:
    if not isinstance(intrinsic_context, dict):
        return False
    for key in ("retrieved_memory", "retrieved_rag_chunks"):
        section = intrinsic_context.get(key)
        if not isinstance(section, dict):
            continue
        if section.get("gap") or section.get("available") is False:
            return True
    return False


def _candidate_tool_names(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    for action in actions:
        if isinstance(action, dict):
            name = _normalize_tool_name(str(action.get("tool") or ""))
            if name:
                names.add(name)
    return names


def _contract_final_required_now(contract: dict[str, Any]) -> bool:
    contract = contract if isinstance(contract, dict) else {}
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    if final_contract.get("final_allowed") is not True:
        return False
    progress = str(contract.get("required_next_progress") or "").strip().lower()
    if "produce action=final" in progress:
        return True
    if "quality gate is satisfied" in progress and "final" in progress:
        return True
    operational = (
        contract.get("operational_notes")
        if isinstance(contract.get("operational_notes"), dict)
        else {}
    )
    next_instruction = str(operational.get("next_instruction") or "").strip().lower()
    return "produce action=final" in next_instruction


def _final_composition_tool_names_from_candidates(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = _normalize_tool_name(str(action.get("tool") or ""))
        args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        if name == "planner_scratchpad_write" and str(args.get("kind") or "").strip() == "answer_chunk":
            names.add(name)
    return names


def _candidate_action_tool(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    return _normalize_tool_name(str(action.get("tool") or ""))


def _candidate_action_args(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    args = action.get("arguments")
    return args if isinstance(args, dict) else {}


def _candidate_action_is_build_state_write(action: Any) -> bool:
    return (
        _candidate_action_tool(action) == "planner_scratchpad_write"
        and str(_candidate_action_args(action).get("kind") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def _candidate_action_is_build_state_read(action: Any) -> bool:
    args = _candidate_action_args(action)
    return (
        _candidate_action_tool(action) == "planner_scratchpad_read"
        and str(args.get("kind") or args.get("mode") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def _dedupe_candidate_actions(actions: list[Any], *, limit: int = 16) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = json.dumps(action, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
        if len(deduped) >= limit:
            break
    return deduped


def _apply_turn_surface_policy(contract: dict[str, Any]) -> dict[str, Any]:
    """Keep candidate actions and native tools aligned with required progress.

    This does not execute a fallback path. It removes contradictory options from
    the planner-visible surface when the controller contract already names the
    only admissible next progress class.
    """
    if not isinstance(contract, dict):
        return contract
    actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    progress = str(contract.get("required_next_progress") or "").strip().lower()
    policy: dict[str, Any] = {
        "schema": "planner_turn_tool_surface_policy.v1",
        "reason": "",
        "allowed_tool_names": [],
        "candidate_actions_filtered": False,
    }

    def set_actions(filtered: list[dict[str, Any]], reason: str) -> None:
        filtered = _dedupe_candidate_actions(filtered)
        contract["candidate_next_actions"] = filtered
        policy["candidate_actions_filtered"] = True
        policy["reason"] = reason
        policy["allowed_tool_names"] = _ordered_tool_names({
            name for name in (_candidate_action_tool(item) for item in filtered) if name
        })
        if len(filtered) == 1:
            policy["required_next_tool_call"] = {
                "tool": _candidate_action_tool(filtered[0]),
                "arguments": _candidate_action_args(filtered[0]),
                "reason": reason,
            }

    def set_surface_only(allowed_names: set[str], reason: str) -> None:
        policy["candidate_actions_filtered"] = False
        policy["reason"] = reason
        policy["allowed_tool_names"] = _ordered_tool_names({
            _normalize_tool_name(str(name))
            for name in allowed_names
            if _normalize_tool_name(str(name))
        })

    if _contract_final_required_now(contract):
        final_actions = [
            item for item in actions
            if _candidate_action_tool(item) == "planner_scratchpad_write"
            and str(_candidate_action_args(item).get("kind") or "").strip() == "answer_chunk"
        ]
        set_actions(final_actions, "final_allowed_and_required_now")
        contract["turn_tool_surface_policy"] = policy
        return contract

    code_contract = (
        contract.get("code_product_contract")
        if isinstance(contract.get("code_product_contract"), dict)
        else {}
    )
    if not code_contract.get("required"):
        return contract

    if "return action=block" in progress and "blocked_incomplete" in progress:
        set_actions([], "code_product_build_state_blocked_incomplete")
    elif "call repo_propose_code_edit" in progress and (
        "ready_for_propose" in progress
        or "complete repo_propose_code_edit candidate" in progress
        or "complete payload from candidate_next_actions" in progress
    ):
        propose_actions = [
            item for item in actions
            if _candidate_action_tool(item) == "repo_propose_code_edit"
            and _code_product_action_has_complete_payload(item)
        ]
        set_actions(propose_actions, "code_product_ready_for_propose")
    elif "read the internal code_product_build_state" in progress:
        read_actions = [item for item in actions if _candidate_action_is_build_state_read(item)]
        set_actions(read_actions, "code_product_build_state_read_required")
    elif (
        ("advance with one real step" in progress or "write code_product_build_state with new real progress" in progress)
        and ("call repo_propose_code_edit" in progress or "typed block" in progress)
    ):
        mixed_actions = [
            item for item in actions
            if (
                _candidate_action_tool(item) == "repo_propose_code_edit"
                and _code_product_action_has_complete_payload(item)
            )
            or _candidate_action_is_build_state_write(item)
        ]
        set_actions(mixed_actions, "code_product_mixed_real_progress_or_typed_block")
    elif (
        "persist an internal code_product_build_state" in progress
        or "write code_product_build_state" in progress
        or "code_product_build_state with real progress" in progress
    ):
        write_actions = [item for item in actions if _candidate_action_is_build_state_write(item)]
        set_actions(write_actions, "code_product_build_state_write_required")
    elif "candidate_next_actions[0]" in progress and actions:
        first = actions[0] if isinstance(actions[0], dict) else {}
        set_actions([first] if first else [], "required_candidate_next_actions_0")
    elif (
        ("target is already read" in progress or "already read" in progress)
        and ("do not repeat repo_read" in progress or "do not call repo_read" in progress)
    ):
        filtered = [
            item for item in actions
            if _candidate_action_tool(item) not in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
        ]
        set_actions(filtered, "code_product_target_already_read_no_repo_navigation")
    elif "read the target with repo_read" in progress:
        filtered = [
            item for item in actions
            if _candidate_action_tool(item) in {"repo_read", "repo_list_files", "repo_tree", "repo_search"}
        ]
        if filtered:
            set_actions(filtered, "code_product_target_read_required")
        else:
            set_surface_only({"repo_read", "repo_list_files", "repo_tree", "repo_search"}, "code_product_target_read_required")
    elif "call repo_propose_code_edit" in progress:
        propose_actions = [
            item for item in actions
            if _candidate_action_tool(item) == "repo_propose_code_edit"
            and _code_product_action_has_complete_payload(item)
        ]
        if propose_actions:
            set_actions(propose_actions, "code_product_propose_required")
        else:
            set_surface_only({"repo_propose_code_edit", "planner_scratchpad_write"}, "code_product_propose_or_build_state_required")
    else:
        filtered = [
            item for item in actions
            if not (
                _candidate_action_tool(item) == "repo_propose_code_edit"
                and not _code_product_action_has_complete_payload(item)
            )
        ]
        if "do not repeat repo_read" in progress or "do not call repo_read" in progress:
            filtered = [item for item in filtered if _candidate_action_tool(item) != "repo_read"]
        set_actions(filtered[:16], "code_product_remove_incomplete_or_repeated_candidates")

    allowed = policy.get("allowed_tool_names")
    if not allowed:
        # A typed block/final without tool calls is valid for some code-product
        # states. Mark the surface locked so provider tools are not exposed as a
        # misleading escape route.
        policy["locked_empty_tool_surface"] = True
    contract["turn_tool_surface_policy"] = policy
    return contract


def _tool_surface_names_for_turn(
    *,
    goal: str,
    evidence_contract: dict[str, Any],
    intrinsic_context: dict[str, Any],
    prompt_context_continuation_required: dict[str, Any] | None = None,
) -> list[str]:
    continuation = prompt_context_continuation_required if isinstance(prompt_context_continuation_required, dict) else {}
    if continuation.get("tool") == "planner_scratchpad_read":
        return ["planner_scratchpad_read"]

    contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    surface_policy = (
        contract.get("turn_tool_surface_policy")
        if isinstance(contract.get("turn_tool_surface_policy"), dict)
        else {}
    )
    policy_allowed = surface_policy.get("allowed_tool_names")
    if isinstance(policy_allowed, list):
        if policy_allowed or surface_policy.get("locked_empty_tool_surface") or _contract_final_required_now(contract):
            return _ordered_tool_names({
                _normalize_tool_name(str(name))
                for name in policy_allowed
                if _normalize_tool_name(str(name))
            })

    semantic = contract.get("semantic_goal_classification") if isinstance(contract.get("semantic_goal_classification"), dict) else {}
    goal_class = str(semantic.get("class") or "").strip()
    code_product_required = bool((contract.get("code_product_contract") or {}).get("required")) if isinstance(contract.get("code_product_contract"), dict) else False
    apply_required = bool(contract.get("goal_requests_apply")) or goal_requests_apply(goal)

    if _contract_final_required_now(contract):
        return _ordered_tool_names(_final_composition_tool_names_from_candidates(contract))

    goal_low = str(goal or "").lower()
    repo_discovery_tools = {
        "repo_read",
        "repo_list_files",
        "repo_tree",
        "repo_search",
        "repo_fd_files",
        "repo_rg_search",
    }
    ast_diff_tools = {
        "repo_ast_grep_search",
        "repo_ast_grep_dry_run",
        "repo_tree_sitter_parse",
        "repo_unidiff_validate",
        "repo_git_apply_check",
    }
    validation_tools = {
        "repo_validate",
        "repo_ruff_check",
        "repo_pyright_check",
        "repo_pytest_run",
    }
    names: set[str] = set(repo_discovery_tools)
    if code_product_required:
        names.update(ast_diff_tools)
        names.update({"repo_propose_code_edit", "planner_scratchpad_write"})
    elif apply_required:
        names.update(ast_diff_tools)
        names.update(validation_tools)
        names.update({"repo_apply_patch", "repo_command", "terminal_run_command_wait"})
    elif goal_class == "analysis_only":
        names = set(repo_discovery_tools)
        names.add("repo_ctags_symbols")
    else:
        names.update({"repo_status"})

    if any(token in goal_low for token in ("json", "payload", "schema", "openapi")):
        names.add("repo_jq_query")
    if any(token in goal_low for token in ("security", "sicurezza", "vulnerability", "vulnerabil", "sast", "semgrep")):
        names.add("repo_semgrep_scan")
    if any(token in goal_low for token in ("shell", "bash", ".sh", "shellcheck")):
        names.add("repo_shellcheck")
    if any(token in goal_low for token in ("benchmark", "performance", "prestazioni", "hyperfine")):
        names.add("repo_hyperfine_benchmark")

    candidate_names = _candidate_tool_names(contract)
    for candidate in candidate_names:
        if candidate.startswith("runtime_sqlite_memory_"):
            continue
        if candidate == "planner_scratchpad_read":
            continue
        names.add(candidate)

    if _intrinsic_context_declares_selective_memory_gap(intrinsic_context):
        names.add("runtime_sqlite_memory_search")
    if "runtime_sqlite_memory_write" in candidate_names:
        names.add("runtime_sqlite_memory_write")
    return _ordered_tool_names(names)


def _available_tools_for_user_payload(compact_tools: list[dict[str, Any]]) -> Any:
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        return compact_tools
    return [
        {
            "name": row.get("name"),
            "transport": "message.tool_calls",
            "schema_source": "ollama_request.tools",
        }
        for row in compact_tools
        if isinstance(row, dict) and row.get("name")
    ]


def _available_tools_window_pack(
    root: Path,
    *,
    goal: str,
    available_tools: Any,
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    tools = available_tools if isinstance(available_tools, list) else []
    text = json.dumps(tools, ensure_ascii=False, indent=2, default=str)
    window = _store_prompt_text_window(
        root,
        section="available_tools",
        text=text,
        query=goal,
        max_chars=window_chars,
        metadata={
            "kind": "available_tools_manifest",
            "format": "json",
            "reason": reason,
        },
    )
    summary: list[dict[str, Any]] = []
    for row in tools:
        if not isinstance(row, dict):
            continue
        item = {"name": row.get("name")}
        if row.get("transport"):
            item["transport"] = row.get("transport")
        if isinstance(row.get("required"), list) and row.get("required"):
            item["required"] = row.get("required")
        summary.append({k: v for k, v in item.items() if v not in (None, "", [], {})})
    payload: dict[str, Any] = {
        "schema": "planner_available_tools_window.v1",
        "tool_count": len(summary),
        "tool_names": [str(item.get("name")) for item in summary if item.get("name")],
        "summary": summary[:80],
        "window": window,
    }
    if len(summary) > 80:
        payload["summary_truncated"] = True
        payload["summary_omitted_count"] = len(summary) - 80
    if window.get("document_id") and window.get("has_more_after") is True:
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return payload


def _tool_shape_examples_for_prompt() -> dict[str, Any]:
    real_value_sources = [
        "candidate_next_actions",
        "required_working_set",
        "verified_content_reads",
        "explicit user exact old_text/new_text",
    ]
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        return {
            "schema": "planner_tool_shape_examples.v1",
            "transport": "native_tool_calls",
            "examples_are_not_runnable": True,
            "must_not_copy_example_values": True,
            "real_values_must_come_from": real_value_sources,
            "content_json_tool_calls_allowed": False,
            "examples": [
                {
                    "shape": "repo_read_known_path_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "repo_read",
                        "arguments": {"path": "EXAMPLE_ONLY/path.py", "max_chars": 8000},
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use a real repo-relative path from evidence.",
                },
                {
                    "shape": "sqlite_prompt_context_window_read_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": "EXAMPLE_ONLY_DO_NOT_COPY_document_id",
                            "offset": 2500,
                            "max_chars": 2500,
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use document_id/offset/max_chars from required_working_set or candidate_next_actions.",
                },
                {
                    "shape": "code_product_build_state_write_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "planner_scratchpad_write",
                        "arguments": {
                            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
                            "target_file": "EXAMPLE_ONLY/path.py",
                            "text": "{\"schema\":\"code_product_build_state.v1\",\"target_file\":\"EXAMPLE_ONLY/path.py\",\"status\":\"collecting_source\",\"source_windows\":[{\"document_id\":\"EXAMPLE_ONLY_DO_NOT_COPY_document_id\",\"offset\":0,\"complete\":false,\"sha256\":\"EXAMPLE_ONLY_DO_NOT_COPY_hash\"}],\"rationale\":\"EXAMPLE_ONLY_DO_NOT_COPY real progress only\"}",
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: write only a complete JSON state with real progress, never an empty template.",
                },
                {
                    "shape": "repo_propose_from_verified_old_text_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "repo_propose_code_edit",
                        "arguments": {
                            "target_file": "EXAMPLE_ONLY/path.py",
                            "edit_kind": "unified_diff",
                            "rationale": "EXAMPLE_ONLY_DO_NOT_COPY: exact replacement from verified repo_read.",
                            "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                            "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: old_text must be exact target content already verified by repo_read.",
                },
                {
                    "shape": "typed_block_when_diff_not_constructible",
                    "transport": "message.content_json",
                    "action": "block",
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY_TYPED_BLOCK",
                    "final_answer": "EXAMPLE_ONLY_DO_NOT_COPY: use typed block when no verified text/window remains to build the diff.",
                },
            ],
        }
    return {
        "schema": "planner_tool_shape_examples.v1",
        "transport": "legacy_json_content",
        "examples_are_not_runnable": True,
        "must_not_copy_example_values": True,
        "real_values_must_come_from": real_value_sources,
        "examples": [
            {
                "shape": "repo_read_known_path",
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": "EXAMPLE_ONLY/path.py", "max_chars": 8000},
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use a real repo-relative path from evidence.",
            },
            {
                "shape": "sqlite_prompt_context_window_read",
                "action": "tool",
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": "prompt_context_window",
                    "document_id": "EXAMPLE_ONLY_DO_NOT_COPY_document_id",
                    "offset": 2500,
                    "max_chars": 2500,
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use document_id/offset/max_chars from required_working_set or candidate_next_actions.",
            },
            {
                "shape": "code_product_build_state_write",
                "action": "tool",
                "tool": "planner_scratchpad_write",
                "arguments": {
                    "kind": CODE_PRODUCT_BUILD_STATE_KIND,
                    "target_file": "EXAMPLE_ONLY/path.py",
                    "text": "{\"schema\":\"code_product_build_state.v1\",\"target_file\":\"EXAMPLE_ONLY/path.py\",\"status\":\"collecting_source\",\"source_windows\":[{\"document_id\":\"EXAMPLE_ONLY_DO_NOT_COPY_document_id\",\"offset\":0,\"complete\":false,\"sha256\":\"EXAMPLE_ONLY_DO_NOT_COPY_hash\"}],\"rationale\":\"EXAMPLE_ONLY_DO_NOT_COPY real progress only\"}",
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: write only a complete JSON state with real progress, never an empty template.",
            },
            {
                "shape": "repo_propose_from_verified_old_text",
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": "EXAMPLE_ONLY/path.py",
                    "edit_kind": "unified_diff",
                    "rationale": "EXAMPLE_ONLY_DO_NOT_COPY: exact replacement from verified repo_read.",
                    "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                    "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: old_text must be exact target content already verified by repo_read.",
            },
            {
                "shape": "typed_block_when_diff_not_constructible",
                "action": "block",
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY_TYPED_BLOCK",
                "final_answer": "EXAMPLE_ONLY_DO_NOT_COPY: use typed block when no verified text/window remains to build the diff.",
            },
        ],
    }


def _compact_history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tail = max(1, int(AGENTIC_PLANNER_HISTORY_PROMPT_TAIL or 1))
    ledger = planner_history_ledger(history[-tail:])
    return [_prompt_clip_value(row, text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS, list_limit=12) for row in ledger]


def _compact_evidence_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    keep_keys = (
        "semantic_goal_classification",
        "goal_requests_code_product",
        "goal_requires_code_product_report",
        "goal_requests_apply",
        "action_plan_candidate",
        "target_kind",
        "resolved_goal_file",
        "resolved_goal_scope",
        "successful_repo_read_paths",
        "successful_repo_read_count",
        "verified_content_read_count",
        "verified_content_reads",
        "user_scope_claims",
        "core_discovery_status",
        "core_discovery_candidates",
        "initial_orientation_surface",
        "candidate_next_actions",
        "planner_may_choose_final",
        "code_product_contract",
        "finalization_contract",
        "required_next_progress",
        "validation_rejections_tail",
        "failed_repo_read_paths",
        "failed_repo_list_files_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
    )
    out = {key: contract.get(key) for key in keep_keys if contract.get(key) not in (None, "", [], {})}
    file_memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    out["file_memory"] = [
        {
            "path": row.get("path"),
            "line_count": row.get("line_count"),
            "truncated": row.get("truncated"),
            "key_lines": _prompt_clip_value(row.get("key_lines") or [], text_limit=220, list_limit=8),
            "content_excerpt": _prompt_clip_text(row.get("content_excerpt"), 500),
        }
        for row in file_memory[:6]
        if isinstance(row, dict)
    ]
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    if operational:
        out["operational_notes"] = {
            "final_allowed": operational.get("final_allowed"),
            "next_instruction": _prompt_clip_text(operational.get("next_instruction"), 500),
            "candidate_next_actions": _prompt_clip_value(operational.get("candidate_next_actions") or [], list_limit=6),
        }
    return _prompt_clip_value(out, text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS, list_limit=12)


def _windowed_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(contract, dict) or not contract:
        return {}
    compact_full = _compact_evidence_contract_for_prompt(contract)
    window = _store_prompt_value_window(
        root,
        section="evidence_contract",
        value=contract,
        query=goal,
        max_chars=window_chars,
        metadata={"kind": "evidence_contract", "format": "json"},
    )
    summary_limit = max(3500, min(7000, int(window_chars or 2500) * 2))
    if _json_char_len(compact_full) > summary_limit:
        compact: dict[str, Any] = {}
        for key in (
            "semantic_goal_classification",
            "goal_requests_code_product",
            "goal_requires_code_product_report",
            "goal_requests_apply",
            "action_plan_candidate",
            "target_kind",
            "resolved_goal_file",
            "resolved_goal_scope",
            "successful_repo_read_count",
            "verified_content_read_count",
            "planner_may_choose_final",
            "required_next_progress",
        ):
            value = contract.get(key)
            if value not in (None, "", [], {}):
                compact[key] = _prompt_clip_value(value, text_limit=300, list_limit=4)
        for key in (
            "successful_repo_read_paths",
            "read_admissible_paths",
            "validator_admissible_repo_read_paths",
            "failed_repo_read_paths",
            "failed_repo_list_files_paths",
        ):
            value = contract.get(key)
            if value not in (None, "", [], {}):
                compact[key] = _prompt_clip_value(value, text_limit=180, list_limit=20)
        for key in (
            "core_discovery_status",
            "code_product_contract",
            "finalization_contract",
            "initial_orientation_surface",
        ):
            value = contract.get(key)
            if value not in (None, "", [], {}):
                compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
        candidates = contract.get("candidate_next_actions")
        if isinstance(candidates, list) and candidates:
            compact["candidate_next_actions"] = _prompt_clip_value(
                candidates,
                text_limit=260,
                list_limit=6,
            )
        discovery_candidates = contract.get("core_discovery_candidates")
        if isinstance(discovery_candidates, list) and discovery_candidates:
            compact["core_discovery_candidates"] = _prompt_clip_value(
                discovery_candidates,
                text_limit=220,
                list_limit=4,
            )
        operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
        if operational:
            compact["operational_notes"] = {
                "final_allowed": operational.get("final_allowed"),
                "next_instruction": _prompt_clip_text(operational.get("next_instruction"), 320),
                "candidate_next_actions": _prompt_clip_value(
                    operational.get("candidate_next_actions") or [],
                    text_limit=220,
                    list_limit=3,
                ),
            }
        compact["windowed_due_to_prompt_budget"] = True
        compact["full_contract_required_from_sqlite_window"] = False
        compact["full_contract_available_from_sqlite_window"] = True
        compact["full_contract_sqlite_window_is_hard_gate"] = False
        compact["windowed_keys_available_in_full_evidence_contract_window"] = [
            str(key)
            for key, value in contract.items()
            if value not in (None, "", [], {}) and key not in compact
        ][:40]
    else:
        compact = compact_full
    compact["full_evidence_contract_window"] = window
    if window.get("document_id") and window.get("has_more_after") is True:
        compact["planner_can_request_more_evidence_contract"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
        continuation = _evidence_contract_continuation_action(
            compact,
            history=history or [],
            window_chars=window_chars,
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact


def _prompt_section_window_pack(
    root: Path,
    *,
    goal: str,
    section: str,
    value: Any,
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    window = _store_prompt_value_window(
        root,
        section=section,
        value=value,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "planner_prompt_section",
            "section": section,
            "format": "json",
            "reason": reason,
        },
    )
    out = {
        "schema": "planner_prompt_section_window.v1",
        "store": "job_local_sqlite",
        "section": section,
        "reason": reason,
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _hard_budget_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(contract, dict) or not contract:
        return {}
    window = _store_prompt_value_window(
        root,
        section="evidence_contract:hard_budget",
        value=contract,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={"kind": "evidence_contract", "format": "json", "reason": reason},
    )
    compact: dict[str, Any] = {
        "schema": "planner_evidence_contract_hard_budget.v1",
        "windowed_due_to_prompt_budget": True,
        "full_contract_available_from_sqlite_window": True,
        "full_contract_sqlite_window_is_hard_gate": False,
        "hard_budget_reason": reason,
    }
    for key in (
        "semantic_goal_classification",
        "goal_requests_code_product",
        "goal_requires_code_product_report",
        "goal_requests_apply",
        "target_kind",
        "resolved_goal_file",
        "resolved_goal_scope",
        "successful_repo_read_count",
        "verified_content_read_count",
        "planner_may_choose_final",
        "required_next_progress",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=320, list_limit=6)
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        compact["finalization_contract"] = {
            key: _prompt_clip_value(final_contract.get(key), text_limit=260, list_limit=4)
            for key in ("final_allowed", "planner_may_choose_final", "reason")
            if final_contract.get(key) not in (None, "", [], {})
        }
    code_contract = contract.get("code_product_contract")
    if isinstance(code_contract, dict):
        compact["code_product_contract"] = {
            key: _prompt_clip_value(code_contract.get(key), text_limit=320, list_limit=8)
            for key in (
                "required",
                "required_tool",
                "successful_proposal_count",
                "latest_target_file",
                "candidate_target_file",
                "candidate_target_line_count",
                "candidate_payload_must_be_generated_from_required_working_set",
                "action_plan_candidate_available",
                "latest_payload_complete",
                "latest_violations",
                "build_state_status",
                "build_state_payload_loaded",
                "build_state_complete_payload_ready",
                "inline_payload_required",
                "artifact_path_is_not_payload",
                "full_payload_fields",
            )
            if code_contract.get(key) not in (None, "", [], {})
        }
    candidates = contract.get("candidate_next_actions")
    if isinstance(candidates, list) and candidates:
        compact["candidate_next_actions"] = _prompt_clip_value(
            candidates,
            text_limit=700,
            list_limit=3,
        )
    for key in ("required_next_tool_call", "forbidden_repeated_tool_calls"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=500, list_limit=8)
    for key in ("successful_repo_read_paths", "read_admissible_paths", "validator_admissible_repo_read_paths"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=160, list_limit=5)
    compact["full_evidence_contract_window"] = window
    if window.get("document_id") and window.get("has_more_after") is True:
        compact["planner_can_request_more_evidence_contract"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
        continuation = _evidence_contract_continuation_action(
            compact,
            history=history or [],
            window_chars=max(500, int(window_chars or 1000)),
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact


def _report_exceeds_generation_headroom(report: dict[str, Any], headroom_char_budget: int) -> bool:
    if int(headroom_char_budget or 0) <= 0:
        return False
    total = int((report or {}).get("total_prompt_chars") or 0)
    if total <= int(headroom_char_budget):
        return False
    native_reserve = int((report or {}).get("native_history_reserve_chars") or 0)
    if native_reserve > 0 and max(0, total - native_reserve) <= int(headroom_char_budget):
        return False
    return True


def _preserve_required_next_tool_call_for_prompt(
    payload: dict[str, Any],
    previous_evidence_contract: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or not isinstance(previous_evidence_contract, dict):
        return
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
    required = (
        previous_evidence_contract.get("required_next_tool_call")
        if isinstance(previous_evidence_contract.get("required_next_tool_call"), dict)
        else {}
    )
    if not required:
        return
    evidence["required_next_tool_call"] = required
    payload["required_next_tool_call"] = required
    for key in ("forbidden_repeated_tool_calls",):
        value = previous_evidence_contract.get(key)
        if isinstance(value, list) and value:
            evidence[key] = value
            payload[key] = value
    prev_actions = (
        previous_evidence_contract.get("candidate_next_actions")
        if isinstance(previous_evidence_contract.get("candidate_next_actions"), list)
        else []
    )
    current_actions = evidence.get("candidate_next_actions") if isinstance(evidence.get("candidate_next_actions"), list) else []
    required_key = json.dumps(required, ensure_ascii=False, sort_keys=True, default=str)
    matched_action = {}
    for action in prev_actions:
        if not isinstance(action, dict):
            continue
        action_required = _required_next_tool_call_from_action(action)
        if json.dumps(action_required, ensure_ascii=False, sort_keys=True, default=str) == required_key:
            matched_action = action
            break
    if matched_action:
        action_key = json.dumps(matched_action, ensure_ascii=False, sort_keys=True, default=str)
        evidence["candidate_next_actions"] = [matched_action] + [
            item for item in current_actions
            if json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) != action_key
        ][:10]
    progress = previous_evidence_contract.get("required_next_progress")
    if progress not in (None, "", [], {}):
        evidence["required_next_progress"] = progress
    final_contract = evidence.get("finalization_contract") if isinstance(evidence.get("finalization_contract"), dict) else {}
    prev_final_contract = (
        previous_evidence_contract.get("finalization_contract")
        if isinstance(previous_evidence_contract.get("finalization_contract"), dict)
        else {}
    )
    if prev_final_contract.get("final_allowed") is False or required.get("tool") == "planner_scratchpad_read":
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = prev_final_contract.get("reason") or evidence.get("required_next_progress")
        evidence["planner_may_choose_final"] = False
    evidence["finalization_contract"] = final_contract
    payload["evidence_contract"] = evidence


def _compact_intrinsic_context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    out = dict(context)
    rag = out.get("retrieved_rag_chunks") if isinstance(out.get("retrieved_rag_chunks"), dict) else {}
    if rag:
        rag = dict(rag)
        rag["items"] = _prompt_clip_value(rag.get("items") or [], text_limit=360, list_limit=3)
        rag["count"] = len(rag.get("items") or [])
        out["retrieved_rag_chunks"] = rag
    mem = out.get("retrieved_memory") if isinstance(out.get("retrieved_memory"), dict) else {}
    if mem:
        mem = dict(mem)
        mem["items"] = _prompt_clip_value(mem.get("items") or [], text_limit=360, list_limit=4)
        mem["count"] = len(mem.get("items") or [])
        out["retrieved_memory"] = mem
    return _prompt_clip_value(out, text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS, list_limit=8)


def _windowed_optional_context_value(
    root: Path,
    *,
    goal: str,
    key: str,
    value: Any,
    window_chars: int,
) -> Any:
    if value in (None, "", [], {}):
        return value
    if _json_char_len(value) <= max(800, int(window_chars or 1000)):
        return value
    window = _store_prompt_value_window(
        root,
        section=f"optional_context:{key}",
        value=value,
        query=goal,
        max_chars=window_chars,
        metadata={"kind": "optional_context", "key": key, "format": "json"},
    )
    out = {
        "schema": "planner_optional_context_window.v1",
        "source_key": key,
        "store": "job_local_sqlite",
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return out


def _optional_context_window_pack(
    root: Path,
    *,
    goal: str,
    optional_context: dict[str, Any],
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    source_keys = [
        str(key)
        for key, value in (optional_context or {}).items()
        if value not in (None, "", [], {})
    ]
    successful_payload_windows = (
        optional_context.get("successful_tool_payload_windows")
        if isinstance(optional_context.get("successful_tool_payload_windows"), list)
        else []
    )
    window_source = dict(optional_context or {})
    if successful_payload_windows:
        window_source.pop("successful_tool_payload_windows", None)
    window = _store_prompt_value_window(
        root,
        section="optional_context:hard_budget_pack",
        value=window_source,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "optional_context_hard_budget_pack",
            "format": "json",
            "reason": reason,
            "source_keys": source_keys,
        },
    )
    out = {
        "schema": "planner_optional_context_window_pack.v1",
        "store": "job_local_sqlite",
        "reason": reason,
        "source_keys": source_keys,
        "serialized_json_window": window,
    }
    if successful_payload_windows:
        out["successful_tool_payload_windows"] = successful_payload_windows
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _optional_context_for_prompt(
    *,
    root: Path,
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    compact_mode: bool,
    window_chars: int,
) -> dict[str, Any]:
    optional = {
        "planner_memory": _prompt_clip_value(planner_memory, text_limit=360, list_limit=4),
        "intrinsic_context": _compact_intrinsic_context_for_prompt(intrinsic_context),
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        optional["history_transport"] = {
            "schema": "planner_history_transport.v1",
            "tool_history_and_results": "ollama_messages",
            "tool_result_payloads": "sqlite_windows",
            "read_more_tool": "planner_scratchpad_read",
            "history_items_available": len(history if isinstance(history, list) else []),
        }
    else:
        optional.update({
            "history_tail": _compact_history_for_prompt(history),
            "turn_memory": _prompt_clip_value(_planner_turn_memory(history), list_limit=8),
            "last_tool_result_digest": _prompt_clip_value(
                planner_last_result_digest(last_tool_result),
                text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
                list_limit=8,
            ),
        })
    if not compact_mode:
        return optional
    tool_payload_windows: list[dict[str, Any]] = []
    for row in reversed(history if isinstance(history, list) else []):
        result = _history_tool_result(row)
        if not result.get("ok"):
            continue
        if result.get("tool") == "controller_guard":
            continue
        raw_payload = _same_tool_artifact_payload(result)
        if not isinstance(raw_payload, dict):
            continue
        raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
        if not raw_text.strip():
            continue
        window = _store_prompt_text_window(
            root,
            section=f"tool_result:{row.get('step')}:{result.get('tool')}",
            text=raw_text,
            query=goal,
            max_chars=window_chars,
            metadata={
                "kind": "successful_tool_result_payload",
                "step": row.get("step"),
                "tool": result.get("tool"),
                "format": "json",
            },
        )
        item = {
            "step": row.get("step"),
            "tool": result.get("tool"),
            "window": window,
        }
        if window.get("document_id") and window.get("has_more_after") is True:
            item["planner_can_request_more"] = {
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": "prompt_context_window",
                    "document_id": window.get("document_id"),
                    "offset": window.get("window_end"),
                    "max_chars": window_chars,
                },
            }
        tool_payload_windows.append(item)
        if len(tool_payload_windows) >= 4:
            break
    if tool_payload_windows:
        optional["successful_tool_payload_windows"] = list(reversed(tool_payload_windows))
    return {
        key: (
            value
            if key == "successful_tool_payload_windows"
            else _windowed_optional_context_value(
                root,
                goal=goal,
                key=key,
                value=value,
                window_chars=window_chars,
            )
        )
        for key, value in optional.items()
    }


def _prompt_budget_report(
    user_payload: dict[str, Any],
    *,
    system_prompt: str = "",
    extra_prompt_sections: dict[str, int] | None = None,
) -> dict[str, Any]:
    sections = {
        key: _json_char_len(value)
        for key, value in user_payload.items()
        if key not in {"available_tools"}
    }
    sections["available_tools"] = _json_char_len(user_payload.get("available_tools"))
    extra_sections = {
        str(key): int(value)
        for key, value in (extra_prompt_sections or {}).items()
        if int(value or 0) > 0
    }
    sections.update(extra_sections)
    total_user = _json_char_len(user_payload)
    system_chars = len(str(system_prompt or ""))
    extra_chars = sum(extra_sections.values())
    total = total_user + system_chars + extra_chars
    headroom_budget = _prompt_generation_headroom_char_budget()
    generation_reserve = max(0, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET - headroom_budget)
    return {
        "schema": "planner_prompt_budget.v1",
        "char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
        "generation_headroom_char_budget": headroom_budget,
        "generation_headroom_reserve_chars": generation_reserve,
        "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
        "generation_token_reserve": _planner_token_generation_reserve(),
        "system_prompt_chars": system_chars,
        "total_user_payload_chars": total_user,
        "extra_prompt_chars": extra_chars,
        "total_prompt_chars": total,
        "over_budget": bool(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0 and total > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET),
        "over_generation_headroom_budget": bool(headroom_budget > 0 and total > headroom_budget),
        "sections": sections,
    }


def _read_json_file(path: str) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _repo_read_file_content_from_repo(item: dict[str, Any], known_prefix: str = "") -> tuple[str, dict[str, Any]]:
    path = _repo_rel_token(item.get("path") or "")
    meta: dict[str, Any] = {"source": "repo_file_rehydrate_unavailable", "path": path}
    if not path:
        meta["error"] = "missing_path"
        return "", meta
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        if not full.exists() or not full.is_file():
            meta["error"] = "file_not_found"
            return "", meta
        text = full.read_text(encoding="utf-8-sig", errors="replace")
        prefix = str(known_prefix or "")
        if prefix and not text.startswith(prefix):
            meta.update(
                {
                    "source": "repo_file_rehydrate_prefix_mismatch",
                    "error": "repo_file_no_longer_matches_repo_read_prefix",
                    "known_prefix_chars": len(prefix),
                    "file_chars": len(text),
                }
            )
            return "", meta
        meta.update(
            {
                "source": "repo_file_rehydrated_for_prompt_window",
                "file_chars": len(text),
                "known_prefix_matched": bool(prefix),
            }
        )
        return text, meta
    except Exception as exc:
        meta.update({"error": "repo_file_rehydrate_failed", "error_type": type(exc).__name__})
        return "", meta


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    meta = {"source": "tool_result_inline"}
    artifact = str(item.get("artifact") or "")
    content = item.get("content")
    loaded = _read_json_file(artifact)
    artifact_content = loaded.get("content")
    preview = item.get("content_preview")
    known_prefix = (
        content if isinstance(content, str)
        else artifact_content if isinstance(artifact_content, str)
        else preview if isinstance(preview, str)
        else ""
    )
    if isinstance(artifact_content, str) and artifact_content:
        inline_prefix = content if isinstance(content, str) else preview if isinstance(preview, str) else ""
        if not inline_prefix or artifact_content.startswith(inline_prefix):
            meta.update(
                {
                    "source": "repo_read_artifact_rehydrated_for_prompt",
                    "artifact": artifact,
                    "artifact_chars": len(artifact_content),
                    "inline_prefix_matched": bool(inline_prefix),
                }
            )
            return artifact_content, meta
    if item.get("truncated") is True:
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, known_prefix)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
    if isinstance(content, str) and item.get("truncated") is not True:
        return content, meta
    if isinstance(known_prefix, str) and known_prefix:
        if item.get("truncated") is True:
            meta.update(
                {
                    "source": "tool_result_inline_truncated_prefix_only",
                    "artifact": artifact,
                }
            )
        return known_prefix, meta
    if isinstance(preview, str):
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, preview)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
        meta.update({"source": "content_preview_only", "artifact": artifact})
        return preview, meta
    return "", meta


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()


def _window_text(
    text: str,
    *,
    center: str = "",
    max_chars: int = 6000,
) -> dict[str, Any]:
    full = str(text or "")
    budget = max(500, int(max_chars or 6000))
    if len(full) <= budget:
        return {
            "text": full,
            "window_start": 0,
            "window_end": len(full),
            "full_chars": len(full),
            "window_chars": len(full),
            "complete": True,
            "has_more_before": False,
            "has_more_after": False,
            "sha256": _text_hash(full),
            "window_sha256": _text_hash(full),
        }
    start = 0
    if center:
        idx = full.find(center)
        if idx >= 0:
            start = max(0, idx - budget // 3)
    end = min(len(full), start + budget)
    start = max(0, end - budget)
    return {
        "text": full[start:end],
        "window_start": start,
        "window_end": end,
        "full_chars": len(full),
        "window_chars": end - start,
        "complete": False,
        "has_more_before": start > 0,
        "has_more_after": end < len(full),
        "sha256": _text_hash(full),
        "window_sha256": _text_hash(full[start:end]),
    }


def _diff_chunks(diff_text: str, *, chunk_chars: int = 6000) -> list[dict[str, Any]]:
    text = str(diff_text or "")
    if not text:
        return []
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 1
    while start < len(text):
        end = min(len(text), start + max(1000, int(chunk_chars or 6000)))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        part = text[start:end]
        chunks.append({
            "index": index,
            "start": start,
            "end": end,
            "chars": len(part),
            "sha256": _text_hash(part),
            "text": part,
        })
        start = end
        index += 1
    return chunks


def _prompt_compaction_threshold() -> int:
    if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET <= 0:
        return 0
    ratio = float(AGENTIC_PLANNER_PROMPT_COMPACT_RATIO or 0.5)
    ratio = max(0.1, min(ratio, 0.95))
    return max(1000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET * ratio))


def _prompt_generation_headroom_char_budget() -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if budget <= 0:
        return 0
    generation_reserve = max(12000, min(18000, budget // 4))
    char_budget_limit = budget - generation_reserve
    token_budget_limit = int(max(1, AGENTIC_PLANNER_NUM_CTX - _planner_token_generation_reserve()) * 2.65)
    return max(1000, min(char_budget_limit, token_budget_limit))


def _planner_token_generation_reserve(num_ctx: int | None = None) -> int:
    try:
        ctx = int(num_ctx if num_ctx is not None else AGENTIC_PLANNER_NUM_CTX)
    except Exception:
        ctx = 0
    if ctx <= 0:
        return 0
    return max(512, min(2048, ctx // 16))


def _prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    if compact_mode:
        sequence = (4000, 3000, 2500, 1800, 1200, 900, 700, 500)
        return sequence[min(max(0, attempt), len(sequence) - 1)]
    return max(1000, min(6000, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET // 5))


def _store_prompt_text_window(
    root: Path,
    *,
    section: str,
    text: str,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return planner_prompt_context_store_window(
        root,
        section=section,
        text=str(text or ""),
        query=query,
        max_chars=max(500, int(max_chars or 1000)),
        metadata=metadata or {},
    )


def _store_prompt_value_window(
    root: Path,
    *,
    section: str,
    value: Any,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return _store_prompt_text_window(
        root,
        section=section,
        text=text,
        query=query,
        max_chars=max_chars,
        metadata=metadata,
    )


def _prompt_window_consumed_offsets(history: list[dict[str, Any]]) -> dict[str, int]:
    consumed: dict[str, int] = {}
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            if any(key not in item for key in _PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS):
                continue
            doc_id = str(item.get("document_id") or "").strip()
            if not doc_id:
                continue
            try:
                end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                end = 0
            if end > consumed.get(doc_id, 0):
                consumed[doc_id] = end
    return consumed


def _prompt_window_tracking_metadata_errors(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
            continue
        items = result.get("items") if isinstance(result.get("items"), list) else []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({
                    "step": row.get("step"),
                    "item_index": index,
                    "error": "prompt_context_window_item_not_object",
                })
                continue
            missing = [
                key for key in _PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS
                if key not in item or item.get(key) in (None, "")
            ]
            if missing:
                errors.append({
                    "step": row.get("step"),
                    "document_id": item.get("document_id"),
                    "item_index": index,
                    "missing": missing,
                    "error": "prompt_context_window_tracking_metadata_missing",
                })
    return errors


def _prompt_context_continue_action(window: dict[str, Any], *, max_chars: int, reason: str) -> dict[str, Any] | None:
    if not isinstance(window, dict) or window.get("has_more_after") is not True:
        return None
    doc_id = str(window.get("document_id") or "").strip()
    if not doc_id:
        return None
    try:
        offset = int(window.get("next_unconsumed_offset") or window.get("window_end") or 0)
    except (TypeError, ValueError):
        offset = int(window.get("window_end") or 0)
    metadata = window.get("metadata") if isinstance(window.get("metadata"), dict) else {}
    kind = (
        CODE_PRODUCT_BUILD_STATE_KIND
        if metadata.get("kind") == CODE_PRODUCT_BUILD_STATE_KIND
        else "prompt_context_window"
    )
    args: dict[str, Any] = {
        "kind": kind,
        "document_id": doc_id,
        "offset": offset,
        "max_chars": max(500, int(max_chars or 1000)),
    }
    if kind == CODE_PRODUCT_BUILD_STATE_KIND and metadata.get("target_file"):
        args["target_file"] = metadata.get("target_file")
    return {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": args,
        "reason": reason,
    }


def _planner_scratchpad_next_window_action_from_history(
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    args = args if isinstance(args, dict) else {}
    document_id = str(args.get("document_id") or args.get("id") or "").strip()
    if not document_id:
        return {}
    latest_window: dict[str, Any] = {}
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("document_id") or "") != document_id:
                continue
            try:
                item_end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                item_end = 0
            try:
                latest_end = int(latest_window.get("window_end") or 0)
            except (TypeError, ValueError):
                latest_end = 0
            if item_end >= latest_end:
                latest_window = dict(item)
    if not latest_window or latest_window.get("has_more_after") is not True:
        return {}
    consumed = _prompt_window_consumed_offsets(history).get(document_id, 0)
    try:
        current_end = int(latest_window.get("window_end") or 0)
    except (TypeError, ValueError):
        current_end = 0
    try:
        full_chars = int(latest_window.get("full_chars") or current_end)
    except (TypeError, ValueError):
        full_chars = current_end
    next_offset = max(consumed, current_end)
    if next_offset >= full_chars:
        return {}
    latest_window["next_unconsumed_offset"] = next_offset
    if str(args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
        metadata = latest_window.get("metadata") if isinstance(latest_window.get("metadata"), dict) else {}
        metadata = dict(metadata)
        metadata["kind"] = CODE_PRODUCT_BUILD_STATE_KIND
        if args.get("target_file"):
            metadata["target_file"] = args.get("target_file")
        latest_window["metadata"] = metadata
    return _prompt_context_continue_action(
        latest_window,
        max_chars=int(args.get("max_chars") or 2500),
        reason=(
            "Repeated SQLite window was already consumed; continue with the next real "
            "unconsumed window before deciding final or code-product output."
        ),
    ) or {}


def _repo_read_items_for_prompt(
    history: list[dict[str, Any]],
    paths: set[str],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(history if isinstance(history, list) else []):
        result = _history_tool_result(row)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        for raw in result.get("items") or []:
            if not isinstance(raw, dict) or not raw.get("ok"):
                continue
            path = _repo_rel_token(raw.get("path") or "")
            if not path or path in seen:
                continue
            if paths and path not in paths:
                continue
            content, content_meta = _repo_read_item_full_content(raw)
            if compact_mode or len(content) > max(800, int(window_chars or 3000)):
                window = _store_prompt_text_window(
                    job_root,
                    section=f"repo_read:{path}",
                    text=content,
                    query=goal,
                    max_chars=window_chars,
                    metadata={"kind": "repo_read_content", "path": path},
                )
            else:
                window = _window_text(
                    content,
                    max_chars=max(800, int(window_chars or 3000)),
                )
            items.append(
                {
                    "path": path,
                    "line_count": raw.get("line_count"),
                    "truncated": raw.get("truncated"),
                    "content_source": content_meta.get("source"),
                    "full_context_reconstructed": content_meta.get("source") in {
                        "repo_file_rehydrated_for_prompt_window",
                        "repo_read_artifact_rehydrated_for_prompt",
                    },
                    "content_rehydrated_from_repo_file": content_meta.get("source") == "repo_file_rehydrated_for_prompt_window",
                    "content_source_error": content_meta.get("error"),
                    "content_window": window,
                    "planner_can_request_more": {
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": window.get("document_id"),
                            "offset": window.get("window_end"),
                            "max_chars": window_chars,
                        },
                    } if window.get("document_id") and window.get("has_more_after") is True else None,
                    "content_chars": len(content),
                }
            )
            seen.add(path)
    items.reverse()
    return items


def _latest_code_product_for_prompt(
    history: list[dict[str, Any]],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> dict[str, Any]:
    for row in reversed(history if isinstance(history, list) else []):
        result = row.get("tool_result") if isinstance(row, dict) and isinstance(row.get("tool_result"), dict) else {}
        if result.get("tool") != "repo_propose_code_edit":
            continue
        out = {
            "ok": result.get("ok"),
            "target_file": result.get("target_file"),
            "edit_kind": result.get("edit_kind"),
            "rationale": result.get("rationale"),
            "validation_commands": result.get("validation_commands"),
            "errors": result.get("errors"),
            "warnings": result.get("warnings"),
            "source_writes_performed": result.get("source_writes_performed"),
            "patch_application_performed": result.get("patch_application_performed"),
        }
        if result.get("unified_diff") not in (None, ""):
            diff_text = str(result.get("unified_diff") or "")
            max_diff_chars = max(800, int(window_chars or 3000))
            if not compact_mode and len(diff_text) <= max_diff_chars:
                out["unified_diff"] = diff_text
            else:
                window = _store_prompt_text_window(
                    job_root,
                    section=f"repo_propose_code_edit:{result.get('target_file') or 'diff'}",
                    text=diff_text,
                    query=goal,
                    max_chars=max_diff_chars,
                    metadata={
                        "kind": "repo_propose_code_edit_unified_diff",
                        "target_file": result.get("target_file"),
                    },
                )
                out["unified_diff_window"] = window
                if window.get("document_id") and window.get("has_more_after") is True:
                    out["planner_can_request_more"] = {
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": window.get("document_id"),
                            "offset": window.get("window_end"),
                            "max_chars": max_diff_chars,
                        },
                    }
                out["unified_diff_chars"] = len(diff_text)
                out["unified_diff_sha256"] = _text_hash(diff_text)
        if result.get("structured_operations") not in (None, "", [], {}):
            out["structured_operations"] = result.get("structured_operations")
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    return {}


def _required_working_set_for_prompt(
    goal: str,
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    job_root: Path,
    window_chars: int,
    compact_mode: bool,
) -> dict[str, Any]:
    target_paths: set[str] = set()
    target_file = _repo_rel_token(contract.get("resolved_goal_file") or _goal_target_file(goal) or "")
    if target_file:
        target_paths.add(target_file)
    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    latest_target = _repo_rel_token(code_contract.get("latest_target_file") or "")
    if latest_target:
        target_paths.add(latest_target)
    candidate_target = _repo_rel_token(code_contract.get("candidate_target_file") or "")
    if candidate_target and candidate_target != ".":
        target_paths.add(candidate_target)
    build_state = _latest_code_product_build_state(history, candidate_target or target_file)
    required = {
        "schema": "planner_required_working_set.v1",
        "no_truncation_allowed": True,
        "context_storage": {
            "enabled": bool(compact_mode),
            "store": "job_local_sqlite",
            "recursive_window_tool": "planner_scratchpad_read",
            "window_policy": "real_text_windows_with_offsets_and_hashes",
        },
        "target_paths": sorted(target_paths),
        "repo_reads": _repo_read_items_for_prompt(
            history,
            target_paths,
            job_root=job_root,
            goal=goal,
            window_chars=window_chars,
            compact_mode=compact_mode,
        ),
        "code_product": _latest_code_product_for_prompt(
            history,
            job_root=job_root,
            goal=goal,
            window_chars=window_chars,
            compact_mode=compact_mode,
        ),
        "code_product_build_state": build_state,
        "limits": [],
        "errors": [],
    }
    for item in required["repo_reads"]:
        window = item.get("content_window") if isinstance(item.get("content_window"), dict) else {}
        has_real_window_text = bool(str(window.get("text") or ""))
        if item.get("truncated") is True and item.get("full_context_reconstructed") is not True:
            row = {"path": item.get("path"), "kind": "repo_read_not_full_content", "content_source": item.get("content_source")}
            if has_real_window_text:
                required["limits"].append(row)
            else:
                required["errors"].append({"path": item.get("path"), "error": "repo_read_full_content_window_unavailable"})
        if item.get("content_source") == "content_preview_only":
            row = {"path": item.get("path"), "kind": "repo_read_content_preview_only"}
            if has_real_window_text:
                required["limits"].append(row)
            else:
                required["errors"].append({"path": item.get("path"), "error": "repo_read_full_content_missing_in_required_working_set"})
    return required


def _required_working_set_continuation_action(
    required_working_set: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    consumed = _prompt_window_consumed_offsets(history)
    windows: list[dict[str, Any]] = []
    for item in (required_working_set or {}).get("repo_reads") or []:
        if isinstance(item, dict) and isinstance(item.get("content_window"), dict):
            windows.append(item["content_window"])
    code_product = (required_working_set or {}).get("code_product")
    if isinstance(code_product, dict) and isinstance(code_product.get("unified_diff_window"), dict):
        windows.append(code_product["unified_diff_window"])
    build_state = (required_working_set or {}).get("code_product_build_state")
    if isinstance(build_state, dict) and build_state.get("has_more_after") is True:
        state_window = dict(build_state)
        state_window["metadata"] = {
            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
            "target_file": build_state.get("target_file"),
            "status": build_state.get("status"),
        }
        windows.append(state_window)
    for window in windows:
        doc_id = str(window.get("document_id") or "").strip()
        if not doc_id or window.get("has_more_after") is not True:
            continue
        try:
            current_end = int(window.get("window_end") or 0)
        except (TypeError, ValueError):
            current_end = 0
        try:
            full_chars = int(window.get("full_chars") or current_end)
        except (TypeError, ValueError):
            full_chars = current_end
        consumed_end = max(current_end, consumed.get(doc_id, 0))
        if consumed_end >= full_chars:
            continue
        window["next_unconsumed_offset"] = consumed_end
        return _prompt_context_continue_action(
            window,
            max_chars=window_chars,
            reason=(
                "Continue consuming the real required_working_set SQLite window before "
                "deciding final or code-product output."
            ),
        )
    return None


def _evidence_contract_continuation_action(
    evidence_contract: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    window = evidence_contract.get("full_evidence_contract_window") if isinstance(evidence_contract, dict) else {}
    if not isinstance(window, dict) or window.get("has_more_after") is not True:
        return None
    doc_id = str(window.get("document_id") or "").strip()
    if not doc_id:
        return None
    try:
        current_end = int(window.get("window_end") or 0)
    except (TypeError, ValueError):
        current_end = 0
    try:
        full_chars = int(window.get("full_chars") or current_end)
    except (TypeError, ValueError):
        full_chars = current_end
    consumed_end = max(current_end, _prompt_window_consumed_offsets(history).get(doc_id, 0))
    if consumed_end >= full_chars:
        return None
    window["next_unconsumed_offset"] = consumed_end
    return _prompt_context_continue_action(
        window,
        max_chars=window_chars,
        reason=(
            "Continue consuming the real evidence_contract SQLite window before "
            "deciding final or code-product output."
        ),
    )


def _prompt_context_continuation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
    required = evidence.get("required_next_tool_call") if isinstance(evidence.get("required_next_tool_call"), dict) else {}
    if required.get("tool") == "planner_scratchpad_read":
        args = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
        kind = str(args.get("kind") or "")
        if kind in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND} and str(args.get("document_id") or "").strip():
            return {
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": kind,
                    "document_id": str(args.get("document_id") or ""),
                    "offset": args.get("offset"),
                    "max_chars": args.get("max_chars"),
                    **({"target_file": args.get("target_file")} if args.get("target_file") else {}),
                },
                "reason": required.get("reason") or evidence.get("required_next_progress"),
            }
    actions = evidence.get("candidate_next_actions") if isinstance(evidence.get("candidate_next_actions"), list) else []
    first = actions[0] if actions and isinstance(actions[0], dict) else {}
    if first.get("tool") != "planner_scratchpad_read":
        return {}
    args = first.get("arguments") if isinstance(first.get("arguments"), dict) else {}
    kind = str(args.get("kind") or "")
    if kind not in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND} or not str(args.get("document_id") or "").strip():
        return {}
    return {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": kind,
            "document_id": str(args.get("document_id") or ""),
            "offset": args.get("offset"),
            "max_chars": args.get("max_chars"),
            **({"target_file": args.get("target_file")} if args.get("target_file") else {}),
        },
        "reason": first.get("reason"),
    }


def _decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    if not isinstance(decision, dict) or not isinstance(continuation, dict):
        return True
    if continuation.get("tool") != "planner_scratchpad_read":
        return True
    if _normalize_tool_name(str(decision.get("tool") or "")) != "planner_scratchpad_read":
        return False
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    expected = continuation.get("arguments") if isinstance(continuation.get("arguments"), dict) else {}
    expected_kind = str(expected.get("kind") or "prompt_context_window")
    if str(args.get("kind") or "") != expected_kind:
        return False
    if str(args.get("document_id") or "") != str(expected.get("document_id") or ""):
        return False
    try:
        if int(args.get("offset") or 0) != int(expected.get("offset") or 0):
            return False
        if expected.get("max_chars") not in (None, ""):
            return int(args.get("max_chars") or 0) == int(expected.get("max_chars") or 0)
        return True
    except (TypeError, ValueError):
        return False


def _required_next_tool_call_from_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    tool = _normalize_tool_name(str(action.get("tool") or ""))
    args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    if tool != "planner_scratchpad_read" or not args:
        return {}
    return {
        "tool": "planner_scratchpad_read",
        "arguments": {
            key: args.get(key)
            for key in ("kind", "document_id", "offset", "max_chars", "target_file")
            if args.get(key) not in (None, "", [], {})
        },
        "reason": action.get("reason"),
    }


def _forbidden_repeated_prompt_window_calls(
    history: list[dict[str, Any]],
    continuation_action: dict[str, Any],
) -> list[dict[str, Any]]:
    required = _required_next_tool_call_from_action(continuation_action)
    required_args = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
    required_doc_id = str(required_args.get("document_id") or "").strip()
    if not required_doc_id:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        if str(result.get("mode") or "") not in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
            continue
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("document_id") or "").strip()
            if doc_id != required_doc_id:
                continue
            try:
                start = int(item.get("window_start") or 0)
                chars = int(item.get("window_chars") or 0)
                end = int(item.get("window_end") or 0)
            except (TypeError, ValueError):
                continue
            key = (doc_id, start, chars)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": str(result.get("mode") or "prompt_context_window"),
                        "document_id": doc_id,
                        "offset": start,
                        "max_chars": chars,
                    },
                    "window_end": end,
                    "reason": "already_consumed",
                }
            )
    return out[-20:]


def _native_history_message_reserve_chars(history: list[dict[str, Any]], window_chars: int) -> int:
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        return 0
    if not any(_history_tool_result(item) for item in (history if isinstance(history, list) else [])):
        return 0
    window = max(2500, int(window_chars or 0))
    return max(6000, window + 3000)


def _build_planner_user_payload(
    *,
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    tool_manifest: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    native_tools_schema: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    goal = str(state.get("goal") or "")
    compact_tools = _compact_tool_manifest_for_prompt(tool_manifest)
    available_tools_for_payload = _available_tools_for_user_payload(compact_tools)
    system_prompt_for_budget = _planner_system_for_current_mode()
    extra_prompt_sections = (
        {"native_tools_schema": _json_char_len(native_tools_schema or [])}
        if AGENTIC_PLANNER_NATIVE_TOOLS
        else {}
    )
    native_history_reserve_chars = _native_history_message_reserve_chars(
        history,
        _prompt_window_chars(True, 0),
    )
    if native_history_reserve_chars:
        extra_prompt_sections["native_history_messages_reserve"] = native_history_reserve_chars
    root = agent_job_root(job_id)
    headroom_char_budget = _prompt_generation_headroom_char_budget()

    def assemble(*, compact_mode: bool, window_chars: int) -> tuple[dict[str, Any], dict[str, Any], int, list[dict[str, Any]]]:
        required_working_set = _required_working_set_for_prompt(
            goal,
            history,
            evidence_contract,
            job_root=root,
            window_chars=window_chars,
            compact_mode=compact_mode,
        )
        required_chars_local = _json_char_len(required_working_set)
        required_errors_local = list(required_working_set.get("errors") or [])
        evidence_for_prompt = (
            _windowed_evidence_contract_for_prompt(
                root,
                goal=goal,
                contract=evidence_contract,
                window_chars=window_chars,
                history=history,
            )
            if compact_mode
            else _compact_evidence_contract_for_prompt(evidence_contract)
        )
        continuation_action = _required_working_set_continuation_action(
            required_working_set,
            history=history,
            window_chars=window_chars,
        )
        if continuation_action:
            required_next_tool_call = _required_next_tool_call_from_action(continuation_action)
            forbidden_repeated_calls = _forbidden_repeated_prompt_window_calls(
                history,
                continuation_action,
            )
            actions = evidence_for_prompt.get("candidate_next_actions") if isinstance(evidence_for_prompt.get("candidate_next_actions"), list) else []
            action_key = json.dumps(continuation_action, sort_keys=True, default=str)
            deduped = [
                item for item in actions
                if json.dumps(item, sort_keys=True, default=str) != action_key
            ]
            evidence_for_prompt["candidate_next_actions"] = [continuation_action] + deduped[:10]
            if required_next_tool_call:
                evidence_for_prompt["required_next_tool_call"] = required_next_tool_call
            if forbidden_repeated_calls:
                evidence_for_prompt["forbidden_repeated_tool_calls"] = forbidden_repeated_calls
            evidence_for_prompt["planner_may_choose_final"] = False
            final_contract = evidence_for_prompt.get("finalization_contract") if isinstance(evidence_for_prompt.get("finalization_contract"), dict) else {}
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = "Real prompt context window continuation is required before final/code-product decision."
            evidence_for_prompt["finalization_contract"] = final_contract
            evidence_for_prompt["required_next_progress"] = continuation_action["reason"]
        tool_shape_examples = _tool_shape_examples_for_prompt()
        payload_local = {
            "job_id": job_id,
            "goal": goal,
            "approval_mode": state.get("approval_mode"),
            "max_steps": state.get("max_steps"),
            "current_step": step,
            "lab_repo": str(LAB_REPO),
            "prompt_pack_contract": {
                "schema": "planner_prompt_pack.v1",
                "num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
                "num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
                "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                "prompt_char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
                "generation_headroom_char_budget": headroom_char_budget,
                "generation_headroom_reserve_chars": max(0, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET - headroom_char_budget),
                "prompt_compaction_threshold_chars": _prompt_compaction_threshold(),
                "prompt_compaction_ratio": AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
                "compact_mode": compact_mode,
                "window_chars": window_chars,
                "native_tools_schema_accounted_in_budget": bool(extra_prompt_sections),
                "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
                "native_history_messages_reserve_chars": native_history_reserve_chars,
                "required_working_set_not_truncated": True,
                "required_working_set_uses_real_sqlite_windows_when_compacted": True,
                "optional_context_may_be_omitted_not_used_as_required_payload": True,
            },
            "terminal_environment_contract": {
                "platform": "windows",
                "shell": "powershell_noninteractive",
                "important": [
                    "For user filesystem work outside LAB_REPO prefer terminal_list_files or terminal_search_files.",
                    "For diagnostic shell commands prefer terminal_run_command_wait, not repo_command.",
                    "Never use Linux commands such as ls -la, find . -type f, grep, cat or pwd on Windows.",
                    "Native Open Terminal run_command may return status=running and exit_code=null; terminal_run_command_wait returns final output.",
                ],
            },
            "available_tools": available_tools_for_payload,
            "tool_shape_examples": tool_shape_examples,
            "required_working_set": required_working_set,
            "optional_context": _optional_context_for_prompt(
                root=root,
                goal=goal,
                history=history,
                planner_memory=planner_memory,
                intrinsic_context=intrinsic_context,
                last_tool_result=last_tool_result,
                compact_mode=compact_mode,
                window_chars=window_chars,
            ),
            "evidence_contract": evidence_for_prompt,
            "required_response_format": (
                {
                    "native_tool_calls_required_for_tools": True,
                    "content_json_only_for": ["final", "block"],
                    "allowed_content_actions": ["final", "block"],
                    "textual_tool_action_allowed": False,
                    "tool_execution": "message.tool_calls",
                    "tool_arguments_rule": (
                        "When choosing a tool, emit a native tool_call using the provided Ollama tools schema. "
                        "Do not emit JSON content with action=tool."
                    ),
                    "final_answer": "required when content JSON action=final or block",
                    "path_rule": (
                        "Choose paths from required_working_set, evidence_contract, "
                        "candidate_next_actions or explicit user input. Do not copy static example paths."
                    ),
                }
                if AGENTIC_PLANNER_NATIVE_TOOLS
                else {
                    "json_only": True,
                    "allowed_actions": ["tool", "final", "block"],
                    "tool": internal_tool_prompt(exclude_vulkan=False),
                    "arguments": {},
                    "reason": "short operational reason",
                    "final_answer": "required when action=final or block",
                    "path_rule": (
                        "Choose paths from required_working_set, evidence_contract, "
                        "candidate_next_actions or explicit user input. Do not copy static example paths."
                    ),
                }
            ),
        }
        if isinstance(evidence_for_prompt.get("required_next_tool_call"), dict):
            payload_local["required_next_tool_call"] = evidence_for_prompt["required_next_tool_call"]
        if isinstance(evidence_for_prompt.get("forbidden_repeated_tool_calls"), list):
            payload_local["forbidden_repeated_tool_calls"] = evidence_for_prompt["forbidden_repeated_tool_calls"]
        report_local = _prompt_budget_report(
            payload_local,
            system_prompt=system_prompt_for_budget,
            extra_prompt_sections=extra_prompt_sections,
        )
        report_local["required_working_set_chars"] = required_chars_local
        report_local["required_working_set_errors"] = required_errors_local
        report_local["compact_mode"] = compact_mode
        report_local["window_chars"] = window_chars
        report_local["native_history_reserve_chars"] = native_history_reserve_chars
        return payload_local, report_local, required_chars_local, required_errors_local

    payload, report, required_chars, required_errors = assemble(
        compact_mode=False,
        window_chars=_prompt_window_chars(False),
    )
    threshold = _prompt_compaction_threshold()
    if threshold and int(report.get("total_prompt_chars") or 0) > threshold:
        for attempt in range(8):
            payload, report, required_chars, required_errors = assemble(
                compact_mode=True,
                window_chars=_prompt_window_chars(True, attempt),
            )
            total_for_compaction = int(report.get("total_prompt_chars") or 0)
            if int(report.get("native_history_reserve_chars") or 0) > 0:
                total_for_compaction = max(
                    0,
                    total_for_compaction - int(report.get("native_history_reserve_chars") or 0),
                )
            if total_for_compaction <= threshold:
                break
    if _report_exceeds_generation_headroom(report, headroom_char_budget):
        optional_for_window = (
            payload.get("optional_context")
            if isinstance(payload.get("optional_context"), dict)
            else {}
        )
        for hard_window_chars in (1000, 700, 500):
            evidence_before_hard_budget = (
                dict(payload.get("evidence_contract"))
                if isinstance(payload.get("evidence_contract"), dict)
                else {}
            )
            payload["optional_context"] = _optional_context_window_pack(
                root,
                goal=goal,
                optional_context=optional_for_window,
                window_chars=hard_window_chars,
                reason="planner_prompt_pack_over_budget_after_compact_mode",
            )
            prompt_contract = payload.get("prompt_pack_contract") if isinstance(payload.get("prompt_pack_contract"), dict) else {}
            prompt_contract["compact_mode"] = True
            prompt_contract["hard_budget_optional_context_windowed"] = True
            prompt_contract["hard_budget_optional_context_window_chars"] = hard_window_chars
            payload["prompt_pack_contract"] = prompt_contract
            payload["evidence_contract"] = _hard_budget_evidence_contract_for_prompt(
                root,
                goal=goal,
                contract=evidence_contract,
                window_chars=hard_window_chars,
                history=history,
                reason="planner_prompt_pack_over_budget_after_compact_mode",
            )
            _preserve_required_next_tool_call_for_prompt(payload, evidence_before_hard_budget)
            payload["tool_shape_examples"] = _tool_shape_examples_for_prompt()
            if isinstance(payload["evidence_contract"].get("required_next_tool_call"), dict):
                payload["required_next_tool_call"] = payload["evidence_contract"]["required_next_tool_call"]
            elif "required_next_tool_call" in payload:
                payload.pop("required_next_tool_call", None)
            if isinstance(payload["evidence_contract"].get("forbidden_repeated_tool_calls"), list):
                payload["forbidden_repeated_tool_calls"] = payload["evidence_contract"]["forbidden_repeated_tool_calls"]
            elif "forbidden_repeated_tool_calls" in payload:
                payload.pop("forbidden_repeated_tool_calls", None)
            report = _prompt_budget_report(
                payload,
                system_prompt=system_prompt_for_budget,
                extra_prompt_sections=extra_prompt_sections,
            )
            report["required_working_set_chars"] = required_chars
            report["required_working_set_errors"] = required_errors
            report["compact_mode"] = True
            report["window_chars"] = hard_window_chars
            report["native_history_reserve_chars"] = native_history_reserve_chars
            if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                break
    if (
        _report_exceeds_generation_headroom(report, headroom_char_budget)
        and int((report.get("sections") or {}).get("available_tools") or 0) > 2500
        and not (
            isinstance(payload.get("available_tools"), dict)
            and payload["available_tools"].get("schema") == "planner_available_tools_window.v1"
        )
    ):
        for hard_window_chars in (700, 500):
            payload["available_tools"] = _available_tools_window_pack(
                root,
                goal=goal,
                available_tools=available_tools_for_payload,
                window_chars=hard_window_chars,
                reason="planner_prompt_pack_over_budget_available_tools_windowed",
            )
            prompt_contract = payload.get("prompt_pack_contract") if isinstance(payload.get("prompt_pack_contract"), dict) else {}
            prompt_contract["compact_mode"] = True
            prompt_contract["available_tools_windowed"] = True
            prompt_contract["available_tools_window_chars"] = hard_window_chars
            payload["prompt_pack_contract"] = prompt_contract
            report = _prompt_budget_report(
                payload,
                system_prompt=system_prompt_for_budget,
                extra_prompt_sections=extra_prompt_sections,
            )
            report["required_working_set_chars"] = required_chars
            report["required_working_set_errors"] = required_errors
            report["compact_mode"] = True
            report["window_chars"] = hard_window_chars
            report["native_history_reserve_chars"] = native_history_reserve_chars
            if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                break
    payload["prompt_budget_report"] = {
        "schema": report.get("schema"),
        "char_budget": report.get("char_budget"),
        "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
        "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
        "total_prompt_chars": report.get("total_prompt_chars"),
        "over_budget": report.get("over_budget"),
        "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
        "extra_prompt_chars": report.get("extra_prompt_chars"),
        "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
        "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
        "required_working_set_chars": report.get("required_working_set_chars"),
        "compact_mode": report.get("compact_mode"),
        "window_chars": report.get("window_chars"),
    }
    for _ in range(6):
        report = _prompt_budget_report(
            payload,
            system_prompt=system_prompt_for_budget,
            extra_prompt_sections=extra_prompt_sections,
        )
        report["required_working_set_chars"] = required_chars
        report["required_working_set_errors"] = required_errors
        report["compact_mode"] = (payload.get("prompt_pack_contract") or {}).get("compact_mode")
        report["window_chars"] = (payload.get("prompt_pack_contract") or {}).get("window_chars")
        report["native_history_reserve_chars"] = native_history_reserve_chars
        payload["prompt_budget_report"] = {
            "schema": report.get("schema"),
            "char_budget": report.get("char_budget"),
            "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
            "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
            "total_prompt_chars": report.get("total_prompt_chars"),
            "over_budget": report.get("over_budget"),
            "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
            "extra_prompt_chars": report.get("extra_prompt_chars"),
            "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
            "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
            "required_working_set_chars": report.get("required_working_set_chars"),
            "compact_mode": report.get("compact_mode"),
            "window_chars": report.get("window_chars"),
        }
        actual_total = (
            len(system_prompt_for_budget)
            + _json_char_len(payload)
            + int(report.get("extra_prompt_chars") or 0)
        )
        if int(report.get("total_prompt_chars") or 0) == actual_total:
            break
    if (
        _report_exceeds_generation_headroom(report, headroom_char_budget)
        and isinstance(payload.get("optional_context"), dict)
        and payload["optional_context"].get("schema") != "planner_optional_context_window_pack.v1"
    ):
        optional_for_window = payload["optional_context"]
        for hard_window_chars in (700, 500):
            evidence_before_hard_budget = (
                dict(payload.get("evidence_contract"))
                if isinstance(payload.get("evidence_contract"), dict)
                else {}
            )
            payload["optional_context"] = _optional_context_window_pack(
                root,
                goal=goal,
                optional_context=optional_for_window,
                window_chars=hard_window_chars,
                reason="planner_prompt_pack_over_budget_after_budget_report",
            )
            prompt_contract = payload.get("prompt_pack_contract") if isinstance(payload.get("prompt_pack_contract"), dict) else {}
            prompt_contract["compact_mode"] = True
            prompt_contract["hard_budget_optional_context_windowed"] = True
            prompt_contract["hard_budget_optional_context_window_chars"] = hard_window_chars
            payload["prompt_pack_contract"] = prompt_contract
            payload["evidence_contract"] = _hard_budget_evidence_contract_for_prompt(
                root,
                goal=goal,
                contract=evidence_contract,
                window_chars=hard_window_chars,
                history=history,
                reason="planner_prompt_pack_over_budget_after_budget_report",
            )
            _preserve_required_next_tool_call_for_prompt(payload, evidence_before_hard_budget)
            payload["tool_shape_examples"] = _tool_shape_examples_for_prompt()
            if isinstance(payload["evidence_contract"].get("required_next_tool_call"), dict):
                payload["required_next_tool_call"] = payload["evidence_contract"]["required_next_tool_call"]
            elif "required_next_tool_call" in payload:
                payload.pop("required_next_tool_call", None)
            if isinstance(payload["evidence_contract"].get("forbidden_repeated_tool_calls"), list):
                payload["forbidden_repeated_tool_calls"] = payload["evidence_contract"]["forbidden_repeated_tool_calls"]
            elif "forbidden_repeated_tool_calls" in payload:
                payload.pop("forbidden_repeated_tool_calls", None)
            for _ in range(6):
                report = _prompt_budget_report(
                    payload,
                    system_prompt=system_prompt_for_budget,
                    extra_prompt_sections=extra_prompt_sections,
                )
                report["required_working_set_chars"] = required_chars
                report["required_working_set_errors"] = required_errors
                report["compact_mode"] = True
                report["window_chars"] = hard_window_chars
                report["native_history_reserve_chars"] = native_history_reserve_chars
                payload["prompt_budget_report"] = {
                    "schema": report.get("schema"),
                    "char_budget": report.get("char_budget"),
                    "generation_headroom_char_budget": report.get("generation_headroom_char_budget"),
                    "generation_headroom_reserve_chars": report.get("generation_headroom_reserve_chars"),
                    "total_prompt_chars": report.get("total_prompt_chars"),
                    "over_budget": report.get("over_budget"),
                    "over_generation_headroom_budget": report.get("over_generation_headroom_budget"),
                    "extra_prompt_chars": report.get("extra_prompt_chars"),
                    "native_tools_schema_chars": extra_prompt_sections.get("native_tools_schema", 0),
                    "native_history_reserve_chars": extra_prompt_sections.get("native_history_messages_reserve", 0),
                    "required_working_set_chars": report.get("required_working_set_chars"),
                    "compact_mode": report.get("compact_mode"),
                    "window_chars": report.get("window_chars"),
                }
                actual_total = (
                    len(system_prompt_for_budget)
                    + _json_char_len(payload)
                    + int(report.get("extra_prompt_chars") or 0)
                )
                if int(report.get("total_prompt_chars") or 0) == actual_total:
                    break
            if not _report_exceeds_generation_headroom(report, headroom_char_budget):
                break
    if native_history_reserve_chars:
        total_without_native_history_reserve = max(
            0,
            int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
        )
        history_message_char_budget = (
            max(0, headroom_char_budget - total_without_native_history_reserve)
            if headroom_char_budget > 0
            else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
        )
        report["native_history_reserve_is_synthetic"] = True
        report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
        report["over_budget_without_native_history_reserve"] = bool(
            AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
            and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        )
        report["over_generation_headroom_without_native_history_reserve"] = bool(
            headroom_char_budget > 0
            and total_without_native_history_reserve > headroom_char_budget
        )
        report["history_message_char_budget"] = history_message_char_budget
        payload_report = payload.get("prompt_budget_report") if isinstance(payload.get("prompt_budget_report"), dict) else {}
        payload_report["native_history_reserve_is_synthetic"] = True
        payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
        payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
        payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
        payload_report["history_message_char_budget"] = history_message_char_budget
        payload["prompt_budget_report"] = payload_report
        if (
            history_message_char_budget < 2500
            and isinstance(payload.get("optional_context"), dict)
            and payload["optional_context"].get("schema") == "planner_optional_context_window_pack.v1"
            and isinstance(payload["optional_context"].get("successful_tool_payload_windows"), list)
            and payload["optional_context"].get("successful_tool_payload_windows")
        ):
            optional_context_copy = dict(payload["optional_context"])
            optional_context_copy.pop("successful_tool_payload_windows", None)
            payload["optional_context"] = optional_context_copy
            prompt_contract = payload.get("prompt_pack_contract") if isinstance(payload.get("prompt_pack_contract"), dict) else {}
            prompt_contract["compact_mode"] = True
            prompt_contract["native_history_headroom_successful_payload_windows_omitted"] = True
            prompt_contract["native_history_headroom_successful_payload_windows_reason"] = (
                "successful tool payload windows are transported through native history messages; "
                "duplicating them in optional_context consumed the history budget."
            )
            payload["prompt_pack_contract"] = prompt_contract
            report = _prompt_budget_report(
                payload,
                system_prompt=system_prompt_for_budget,
                extra_prompt_sections=extra_prompt_sections,
            )
            report["required_working_set_chars"] = required_chars
            report["required_working_set_errors"] = required_errors
            report["compact_mode"] = True
            report["window_chars"] = (prompt_contract or {}).get("window_chars")
            report["native_history_reserve_chars"] = native_history_reserve_chars
            total_without_native_history_reserve = max(
                0,
                int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
            )
            history_message_char_budget = (
                max(0, headroom_char_budget - total_without_native_history_reserve)
                if headroom_char_budget > 0
                else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
            )
            report["native_history_reserve_is_synthetic"] = True
            report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
            report["over_budget_without_native_history_reserve"] = bool(
                AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
            )
            report["over_generation_headroom_without_native_history_reserve"] = bool(
                headroom_char_budget > 0
                and total_without_native_history_reserve > headroom_char_budget
            )
            report["history_message_char_budget"] = history_message_char_budget
            payload_report = payload.get("prompt_budget_report") if isinstance(payload.get("prompt_budget_report"), dict) else {}
            payload_report["schema"] = report.get("schema")
            payload_report["char_budget"] = report.get("char_budget")
            payload_report["generation_headroom_char_budget"] = report.get("generation_headroom_char_budget")
            payload_report["generation_headroom_reserve_chars"] = report.get("generation_headroom_reserve_chars")
            payload_report["total_prompt_chars"] = report.get("total_prompt_chars")
            payload_report["over_budget"] = report.get("over_budget")
            payload_report["over_generation_headroom_budget"] = report.get("over_generation_headroom_budget")
            payload_report["extra_prompt_chars"] = report.get("extra_prompt_chars")
            payload_report["native_tools_schema_chars"] = extra_prompt_sections.get("native_tools_schema", 0)
            payload_report["native_history_reserve_chars"] = extra_prompt_sections.get("native_history_messages_reserve", 0)
            payload_report["required_working_set_chars"] = report.get("required_working_set_chars")
            payload_report["compact_mode"] = True
            payload_report["window_chars"] = report.get("window_chars")
            payload_report["native_history_reserve_is_synthetic"] = True
            payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
            payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
            payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
            payload_report["history_message_char_budget"] = history_message_char_budget
            payload["prompt_budget_report"] = payload_report
        if (
            history_message_char_budget < 2500
            and isinstance(payload.get("optional_context"), dict)
            and payload["optional_context"].get("schema") != "planner_optional_context_window_pack.v1"
        ):
            optional_for_window = payload["optional_context"]
            for hard_window_chars in (500,):
                payload["optional_context"] = _optional_context_window_pack(
                    root,
                    goal=goal,
                    optional_context=optional_for_window,
                    window_chars=hard_window_chars,
                    reason="planner_native_history_message_budget_low",
                )
                prompt_contract = payload.get("prompt_pack_contract") if isinstance(payload.get("prompt_pack_contract"), dict) else {}
                prompt_contract["compact_mode"] = True
                prompt_contract["native_history_headroom_optional_context_windowed"] = True
                prompt_contract["native_history_headroom_optional_context_window_chars"] = hard_window_chars
                payload["prompt_pack_contract"] = prompt_contract
                report = _prompt_budget_report(
                    payload,
                    system_prompt=system_prompt_for_budget,
                    extra_prompt_sections=extra_prompt_sections,
                )
                report["required_working_set_chars"] = required_chars
                report["required_working_set_errors"] = required_errors
                report["compact_mode"] = True
                report["window_chars"] = hard_window_chars
                report["native_history_reserve_chars"] = native_history_reserve_chars
                total_without_native_history_reserve = max(
                    0,
                    int(report.get("total_prompt_chars") or 0) - native_history_reserve_chars,
                )
                history_message_char_budget = (
                    max(0, headroom_char_budget - total_without_native_history_reserve)
                    if headroom_char_budget > 0
                    else max(0, AGENTIC_PLANNER_NUM_CTX * 2)
                )
                report["native_history_reserve_is_synthetic"] = True
                report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                report["over_budget_without_native_history_reserve"] = bool(
                    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
                    and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
                )
                report["over_generation_headroom_without_native_history_reserve"] = bool(
                    headroom_char_budget > 0
                    and total_without_native_history_reserve > headroom_char_budget
                )
                report["history_message_char_budget"] = history_message_char_budget
                payload_report = payload.get("prompt_budget_report") if isinstance(payload.get("prompt_budget_report"), dict) else {}
                payload_report["schema"] = report.get("schema")
                payload_report["char_budget"] = report.get("char_budget")
                payload_report["generation_headroom_char_budget"] = report.get("generation_headroom_char_budget")
                payload_report["generation_headroom_reserve_chars"] = report.get("generation_headroom_reserve_chars")
                payload_report["total_prompt_chars"] = report.get("total_prompt_chars")
                payload_report["over_budget"] = report.get("over_budget")
                payload_report["over_generation_headroom_budget"] = report.get("over_generation_headroom_budget")
                payload_report["extra_prompt_chars"] = report.get("extra_prompt_chars")
                payload_report["native_tools_schema_chars"] = extra_prompt_sections.get("native_tools_schema", 0)
                payload_report["native_history_reserve_chars"] = extra_prompt_sections.get("native_history_messages_reserve", 0)
                payload_report["required_working_set_chars"] = report.get("required_working_set_chars")
                payload_report["compact_mode"] = True
                payload_report["window_chars"] = hard_window_chars
                payload_report["native_history_reserve_is_synthetic"] = True
                payload_report["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
                payload_report["over_budget_without_native_history_reserve"] = report["over_budget_without_native_history_reserve"]
                payload_report["over_generation_headroom_without_native_history_reserve"] = report["over_generation_headroom_without_native_history_reserve"]
                payload_report["history_message_char_budget"] = history_message_char_budget
                payload["prompt_budget_report"] = payload_report
                if history_message_char_budget >= 2500:
                    break
    return payload, report


_OLLAMA_STREAM_META_KEYS = (
    "ollama_done_seen",
    "ollama_done_reason",
    "ollama_load_duration",
    "ollama_total_duration",
    "ollama_eval_count",
    "ollama_prompt_eval_count",
)

_LOCAL_ARTIFACT_KEYS = {
    "artifact",
    "cached_from_artifact",
    "stream_path",
    "events_path",
    "final_path",
    "final_markdown_path",
}

_PUBLIC_LOCAL_REFERENCE_KEYS = {
    "cached_from_artifact",
    "stream_path",
    "events_path",
    "final_path",
    "final_markdown_path",
    "db",
    "workspace",
    "document_id",
    "final_json",
    "final_markdown",
    "events_ndjson",
    "planner_stream",
}


def _drop_empty_dict_values(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if v not in (None, "", [], {})}


def _planner_ollama_turn_from_decision(
    decision: dict[str, Any] | None,
    *,
    step: Any = None,
) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    meta = decision.get("planner_stream_meta") if isinstance(decision.get("planner_stream_meta"), dict) else {}
    if not meta:
        return {}
    turn = {
        "step": step,
        "done_seen": meta.get("ollama_done_seen"),
        "done_reason": meta.get("ollama_done_reason"),
        "load_duration": meta.get("ollama_load_duration"),
        "total_duration": meta.get("ollama_total_duration"),
        "eval_count": meta.get("ollama_eval_count"),
        "prompt_eval_count": meta.get("ollama_prompt_eval_count"),
    }
    return _drop_empty_dict_values(turn)


def _history_item_ollama_turn(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    explicit = item.get("ollama_turn") if isinstance(item.get("ollama_turn"), dict) else {}
    if explicit:
        return explicit
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    result_turn = result.get("ollama_turn") if isinstance(result.get("ollama_turn"), dict) else {}
    if result_turn:
        return result_turn
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    turn = _planner_ollama_turn_from_decision(decision, step=item.get("step"))
    if turn:
        return turn
    for source in (
        decision.get("rejected_decision") if isinstance(decision.get("rejected_decision"), dict) else {},
        result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
    ):
        turn = _planner_ollama_turn_from_decision(source, step=item.get("step"))
        if turn:
            return turn
    return {}


def _history_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    if result:
        return result
    if item.get("tool"):
        return item
    return {}


def _bounded_prompt_context_tool_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if result.get("tool") != "planner_scratchpad_read":
        return {}
    mode = str(result.get("mode") or "")
    if mode not in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
        return {}
    items = result.get("items") if isinstance(result.get("items"), list) else []
    payload: dict[str, Any] = {
        "schema": "planner_bounded_tool_result.v1",
        "tool": "planner_scratchpad_read",
        "ok": result.get("ok"),
        "mode": mode,
        "count": result.get("count", len(items)),
        "items": [
            _compact_prompt_context_window_item(item)
            for item in items
            if isinstance(item, dict)
        ],
    }
    for key in ("kind", "target_file", "status", "complete_payload_ready", "state_parse_error"):
        if result.get(key) not in (None, "", [], {}):
            payload[key] = result.get(key)
    for item in payload.get("items") or []:
        if not isinstance(item, dict) or item.get("has_more_after") is not True:
            continue
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": mode,
                "document_id": item.get("document_id"),
                "offset": item.get("window_end"),
                "max_chars": item.get("window_chars"),
            },
        }
        if mode == CODE_PRODUCT_BUILD_STATE_KIND and payload.get("target_file"):
            payload["planner_can_request_more"]["arguments"]["target_file"] = payload.get("target_file")
        break
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


_PLANNER_HISTORY_NOISE_KEYS = {
    *_LOCAL_ARTIFACT_KEYS,
    *_OLLAMA_STREAM_META_KEYS,
    "cache_key",
    "repair_cache_key",
    "repair_cache_hit",
    "cached_from_step",
    "controller_preseed",
    "preseed_index",
    "dynamic_initial_orientation",
    "duration",
    "duration_ms",
    "elapsed",
    "elapsed_ms",
    "started_at",
    "finished_at",
    "created_at",
    "updated_at",
    "events",
    "raw_events",
}


def _planner_history_summary(value: Any) -> str:
    text = str(value or "").strip()
    for marker in (
        " artifact=",
        " cached_from_artifact=",
        " stream_path=",
        " events_path=",
        " final_path=",
    ):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return _prompt_clip_text(text, 700)


def _clean_planner_history_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in _PLANNER_HISTORY_NOISE_KEYS:
                continue
            if key_text == "store" and str(item).lower() in {"job_local_sqlite", "sqlite", "local_path"}:
                continue
            if key_text == "summary":
                cleaned_summary = _planner_history_summary(item)
                if cleaned_summary:
                    out[key_text] = cleaned_summary
                continue
            out[key_text] = _clean_planner_history_value(item)
        return _drop_empty_dict_values(out)
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _clean_planner_history_value(item)) not in (None, "", [], {})
        ]
    return value


def _planner_history_arguments(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    if arguments:
        return _drop_empty_dict_values(_clean_planner_history_value(arguments))
    derived: dict[str, Any] = {}
    for key in (
        "path",
        "paths",
        "query",
        "target_file",
        "edit_kind",
        "kind",
        "mode",
        "line",
        "before",
        "after",
        "max_chars",
        "limit",
        "max_depth",
        "suffix",
        "document_id",
        "offset",
    ):
        if result.get(key) not in (None, "", [], {}):
            derived[key] = result.get(key)
    return _drop_empty_dict_values(_clean_planner_history_value(derived))


def _planner_history_reason(item: dict[str, Any], result: dict[str, Any]) -> str:
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    for value in (
        decision.get("reason"),
        result.get("preseed_reason"),
        result.get("summary"),
    ):
        reason = _planner_history_summary(value)
        if reason:
            return reason
    return ""


def _planner_controller_guard_history_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    contract = result.get("evidence_contract") if isinstance(result.get("evidence_contract"), dict) else {}
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    content = rejected.get("content")
    payload: dict[str, Any] = {
        "schema": "planner_controller_guard_history.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": "controller_guard",
        "ok": result.get("ok"),
        "guard_type": result.get("guard_type"),
        "violations": result.get("violations"),
        "summary": _planner_history_summary(result.get("summary")),
        "rejected_action": rejected.get("action"),
        "rejected_final_answer_source": rejected.get("final_answer_source"),
        "rejected_content_keys": list(content.keys()) if isinstance(content, dict) else None,
        "required_next_progress": contract.get("required_next_progress"),
        "planner_may_choose_final": contract.get("planner_may_choose_final"),
        "next_instruction": result.get("next_instruction") or operational.get("next_instruction"),
        "successful_repo_read_count": contract.get("successful_repo_read_count"),
        "verified_content_read_count": contract.get("verified_content_read_count"),
    }
    return _drop_empty_dict_values(_clean_planner_history_value(payload))


def _planner_history_evidence_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tool = str(result.get("tool") or (item.get("decision") or {}).get("tool") or "")
    payload: dict[str, Any] = {
        "schema": "planner_tool_history_evidence.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": tool,
        "reason": _planner_history_reason(item, result),
        "arguments": _planner_history_arguments(item, result),
        "result": _clean_planner_history_value(result),
    }
    return _drop_empty_dict_values(payload)


def _planner_tool_result_message_payload(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> dict[str, Any]:
    tool = str(result.get("tool") or (item.get("decision") or {}).get("tool") or "")
    direct_payload = _bounded_prompt_context_tool_result_payload(result)
    if direct_payload:
        direct_payload["step"] = item.get("step")
        if item.get("substep") not in (None, "", [], {}):
            direct_payload["substep"] = item.get("substep")
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if isinstance(decision.get("arguments"), dict):
            direct_payload["arguments"] = decision.get("arguments")
        return direct_payload
    if tool == "controller_guard":
        return _planner_controller_guard_history_payload(item, result)
    raw_payload = _planner_history_evidence_payload(item, result)
    raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
    if len(raw_text) <= max(1200, int(window_chars or 0)):
        return raw_payload
    window = _store_prompt_text_window(
        root,
        section=f"message_tool_result:{item.get('step')}:{tool}",
        text=raw_text,
        query=goal,
        max_chars=window_chars,
        metadata={
            "kind": "planner_message_tool_result_payload",
            "step": item.get("step"),
            "substep": item.get("substep"),
            "tool": tool,
            "format": "json",
        },
    )
    payload: dict[str, Any] = {
        "schema": "planner_tool_history_window.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": tool,
        "reason": raw_payload.get("reason"),
        "arguments": raw_payload.get("arguments"),
        "result_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return {k: v for k, v in payload.items() if v not in (None, "", [], {})}


def _planner_history_item_messages(
    item: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    result = _history_tool_result(item)
    messages: list[dict[str, Any]] = []
    if (
        decision.get("native_tool_call") is True
        and isinstance(decision.get("raw_native_tool_call"), dict)
    ):
        raw_native_call = decision["raw_native_tool_call"]
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [raw_native_call],
        })
        if result:
            tool_message = {
                "role": "tool",
                "tool_name": str(result.get("tool") or decision.get("tool") or ""),
                "content": json.dumps(
                    _planner_tool_result_message_payload(
                        item,
                        result,
                        root=root,
                        goal=goal,
                        window_chars=window_chars,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            }
            if raw_native_call.get("id"):
                tool_message["tool_call_id"] = raw_native_call.get("id")
            messages.append(tool_message)
        return messages
    if result:
        payload = _planner_tool_result_message_payload(
            item,
            result,
            root=root,
            goal=goal,
            window_chars=window_chars,
        )
        messages.append({
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        })
    return messages


def _planner_history_messages_for_ollama(
    history: list[dict[str, Any]],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if max_chars <= 0:
        return [], {
            "schema": "planner_history_messages.v1",
            "enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
            "included_history_items": 0,
            "skipped_history_items": len(history if isinstance(history, list) else []),
            "message_chars": 0,
            "max_chars": max_chars,
        }
    selected_reversed: list[list[dict[str, Any]]] = []
    total_chars = 0
    included = 0
    skipped = 0
    for item in reversed(history if isinstance(history, list) else []):
        item_messages = _planner_history_item_messages(
            item,
            root=root,
            goal=goal,
            window_chars=window_chars,
        )
        if not item_messages:
            continue
        item_chars = _json_char_len(item_messages)
        if selected_reversed and total_chars + item_chars > max_chars:
            skipped += 1
            continue
        if total_chars + item_chars > max_chars:
            skipped += 1
            continue
        selected_reversed.append(item_messages)
        total_chars += item_chars
        included += 1
    messages: list[dict[str, Any]] = []
    for group in reversed(selected_reversed):
        messages.extend(group)
    return messages, {
        "schema": "planner_history_messages.v1",
        "enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
        "included_history_items": included,
        "skipped_history_items": skipped,
        "message_count": len(messages),
        "message_chars": _json_char_len(messages),
        "max_chars": max_chars,
        "window_chars": window_chars,
    }


def _decision_for_turn_memory(decision: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    return _drop_empty_dict_values({
        "action": decision.get("action"),
        "tool": decision.get("tool"),
        "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else None,
        "reason": decision.get("reason"),
        "final_answer": decision.get("final_answer"),
        "native_tool_call": decision.get("native_tool_call"),
        "native_tool_calls_seen": decision.get("native_tool_calls_seen"),
    })


def _strip_public_artifact_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _strip_public_artifact_paths(v)
            for k, v in value.items()
            if str(k) not in _LOCAL_ARTIFACT_KEYS
        }
    if isinstance(value, list):
        return [_strip_public_artifact_paths(item) for item in value]
    return value


def _strip_public_local_references(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "artifact" and isinstance(item, str):
                continue
            if key_text in _PUBLIC_LOCAL_REFERENCE_KEYS:
                continue
            if key_text == "store" and str(item).lower() in {"job_local_sqlite", "sqlite", "local_path"}:
                continue
            out[key_text] = _strip_public_local_references(item)
        return out
    if isinstance(value, list):
        return [_strip_public_local_references(item) for item in value]
    return value


def _same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Load the full JSON only for the same successful tool result."""
    if not isinstance(result, dict) or not result.get("ok"):
        return result if isinstance(result, dict) else {}
    artifact = str(result.get("artifact") or "")
    if not artifact:
        return result
    try:
        artifact_path = Path(artifact)
        if not artifact_path.exists() or not artifact_path.is_file():
            return result
        loaded = json.loads(artifact_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return result
    if not isinstance(loaded, dict):
        return result
    expected_tool = str(result.get("tool") or "")
    loaded_tool = str(loaded.get("tool") or "")
    if expected_tool and loaded_tool and expected_tool != loaded_tool:
        return result
    return loaded


def _public_tool_response(tool_result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_result, dict) or not tool_result.get("ok"):
        return {}
    source = _same_tool_artifact_payload(tool_result)
    tool = str(source.get("tool") or tool_result.get("tool") or "")
    if (
        tool in {"planner_scratchpad_read", "planner_scratchpad_write"}
        and str(source.get("mode") or tool_result.get("mode") or "") == CODE_PRODUCT_BUILD_STATE_KIND
    ):
        return {}

    if tool == "repo_read":
        items: list[dict[str, Any]] = []
        for read_item in source.get("items") or []:
            if not isinstance(read_item, dict) or not read_item.get("ok"):
                continue
            content, _content_meta = _repo_read_item_full_content(read_item)
            if content in (None, ""):
                content = read_item.get("content")
            if content is None:
                content = read_item.get("content_view") or read_item.get("content_preview")
            items.append(_drop_empty_dict_values({
                "repo_path": read_item.get("path"),
                "size_bytes": read_item.get("size_bytes"),
                "line_count": read_item.get("line_count"),
                "truncated": False if content else read_item.get("truncated"),
                "content": content,
            }))
        return _drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "count": len(items),
            "requested_count": source.get("requested_count"),
            "success_count": len(items),
            "max_paths": source.get("max_paths"),
            "items": items,
        })

    if tool == "repo_propose_code_edit":
        response: dict[str, Any] = {
            "tool": tool,
            "ok": source.get("ok"),
            "kind": source.get("kind"),
            "target_file": source.get("target_file"),
            "edit_kind": source.get("edit_kind"),
            "rationale": source.get("rationale"),
            "source_writes_performed": source.get("source_writes_performed"),
            "patch_application_performed": source.get("patch_application_performed"),
            "manual_review_required": source.get("manual_review_required"),
            "validation_commands": source.get("validation_commands"),
            "errors": source.get("errors"),
            "warnings": source.get("warnings"),
            "target_metadata": source.get("target_metadata"),
            "ast_evidence": source.get("ast_evidence"),
        }
        if source.get("edit_kind") == "unified_diff":
            response["unified_diff"] = source.get("unified_diff")
        if source.get("edit_kind") == "structured_edit":
            response["structured_operations"] = source.get("structured_operations")
        return _drop_empty_dict_values(response)

    if tool == "repo_tree":
        entries = source.get("entries") if isinstance(source.get("entries"), list) else []
        return _drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "repo_path": source.get("path"),
            "count": source.get("count", len(entries)),
            "entries_total": source.get("entries_total") or source.get("count") or len(entries),
            "truncated": source.get("truncated"),
            "entries": _strip_public_artifact_paths(entries),
        })

    if tool == "repo_list_files":
        paths = source.get("paths") if isinstance(source.get("paths"), list) else []
        return _drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "repo_path": source.get("path"),
            "suffix": source.get("suffix"),
            "count": source.get("count", len(paths)),
            "total_matches": source.get("total_matches"),
            "limit": source.get("limit"),
            "truncated": source.get("truncated"),
            "paths": paths,
            "files": _strip_public_artifact_paths(source.get("files"))
            if isinstance(source.get("files"), list) else None,
        })

    if tool in {"repo_command", "terminal_run_command_wait"}:
        return _drop_empty_dict_values({
            "tool": tool,
            "ok": source.get("ok"),
            "command": source.get("command"),
            "returncode": source.get("returncode"),
            "stdout": source.get("stdout") or source.get("stdout_text"),
            "stderr": source.get("stderr") or source.get("stderr_text"),
            "stdout_tail": source.get("stdout_tail"),
            "stderr_tail": source.get("stderr_tail"),
        })

    useful: dict[str, Any] = {"tool": tool, "ok": source.get("ok")}
    for key in (
        "summary", "content", "text", "message", "result", "items",
        "matches", "files", "paths", "count", "total_matches", "limit",
        "truncated", "returncode", "stdout", "stderr", "stdout_text",
        "stderr_text", "stdout_tail", "stderr_tail", "diagnostics",
        "diagnostics_total", "anchors", "anchors_total", "symbols",
        "symbols_total", "comments", "parsed_json", "file_count",
        "results", "results_total", "errors", "warnings", "stderr_tail",
    ):
        if source.get(key) not in (None, "", [], {}):
            useful[key] = _strip_public_artifact_paths(source.get(key))
    return _drop_empty_dict_values(useful)


def _successful_tool_turns(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        tool = str(result.get("tool") or "")
        if not tool or tool == "controller_guard" or not result.get("ok"):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        response = _public_tool_response(result)
        if not response:
            continue
        turns.append(_drop_empty_dict_values({
            "step": item.get("step"),
            "substep": item.get("substep"),
            "producer": "controller_preseed"
            if str(decision.get("action") or "") == "controller_preseed"
            else "planner",
            "ollama_done_reason": _history_item_ollama_turn(item).get("done_reason"),
            "ollama_turn": _history_item_ollama_turn(item),
            "tool_call": _decision_for_turn_memory(decision),
            "tool_response": response,
        }))
    return turns


def _public_tool_artifact_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return OpenWebUI-visible artifacts with real payloads, never local paths."""
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        tool = str(result.get("tool") or "")
        if not tool or tool == "controller_guard" or not result.get("ok"):
            continue
        response = _public_tool_response(result)
        if not response:
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        base = {
            "producer_step": item.get("step"),
            "substep": item.get("substep"),
            "tool": tool,
            "arguments": arguments,
            "ok": True,
        }
        if tool == "repo_read":
            for read_item in response.get("items") or []:
                if not isinstance(read_item, dict):
                    continue
                artifact = {"kind": "repo_read", **_strip_public_artifact_paths(read_item)}
                rows.append(_drop_empty_dict_values({**base, "artifact": artifact}))
            continue
        artifact_payload = {
            k: v for k, v in response.items()
            if k not in {"tool", "ok"} and v not in (None, "", [], {})
        }
        artifact_payload = _strip_public_artifact_paths(artifact_payload)
        if tool == "repo_propose_code_edit":
            artifact = {"kind": "code_edit_proposal", **artifact_payload}
        elif tool in {"repo_unidiff_validate", "repo_git_apply_check"}:
            artifact = {"kind": "diff_validation", **artifact_payload}
        elif tool in {"repo_ruff_check", "repo_pyright_check", "repo_pytest_run", "repo_shellcheck", "repo_semgrep_scan"}:
            artifact = {"kind": "validation_result", **artifact_payload}
        elif tool in {"repo_ast_grep_search", "repo_ast_grep_dry_run", "repo_tree_sitter_parse", "repo_ctags_symbols"}:
            artifact = {"kind": "structural_evidence", **artifact_payload}
        elif tool in {"repo_fd_files", "repo_rg_search", "repo_jq_query"}:
            artifact = {"kind": "deterministic_repo_evidence", **artifact_payload}
        elif tool == "repo_tree":
            artifact = {"kind": "repo_tree", **artifact_payload}
        elif tool == "repo_list_files":
            artifact = {"kind": "repo_list_files", **artifact_payload}
        elif tool in {"repo_command", "terminal_run_command_wait"}:
            artifact = {"kind": "command_result", **artifact_payload}
        else:
            artifact = {"kind": artifact_payload.get("kind") or "tool_result", **artifact_payload}
        rows.append(_drop_empty_dict_values({**base, "artifact": artifact}))
    return rows


def _public_tool_context_limits(artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    for row in artifact_rows if isinstance(artifact_rows, list) else []:
        if not isinstance(row, dict):
            continue
        artifact = row.get("artifact") if isinstance(row.get("artifact"), dict) else {}
        if not artifact:
            continue
        base = {
            "step": row.get("producer_step"),
            "tool": row.get("tool"),
            "path": artifact.get("repo_path") or artifact.get("target_file"),
        }
        if artifact.get("truncated") is True:
            limits.append(_drop_empty_dict_values({**base, "kind": "truncated"}))
        if artifact.get("preview_only") is True:
            limits.append(_drop_empty_dict_values({**base, "kind": "preview_only"}))
        total = artifact.get("total_matches") or artifact.get("entries_total")
        visible = artifact.get("count")
        try:
            if total not in (None, "") and visible not in (None, "") and int(total) > int(visible):
                limits.append(_drop_empty_dict_values({
                    **base,
                    "kind": "partial_list",
                    "visible": visible,
                    "total": total,
                }))
        except Exception:
            pass
    return limits


def _ollama_turn_rows(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = _history_tool_result(item)
        turn = _history_item_ollama_turn(item)
        if not turn:
            continue
        row = _drop_empty_dict_values({
            "step": item.get("step"),
            "done_reason": turn.get("done_reason"),
            "done_seen": turn.get("done_seen"),
            "action": decision.get("action"),
            "tool": decision.get("tool") or result.get("tool"),
            "tool_ok": result.get("ok") if result.get("tool") != "controller_guard" else None,
            "guard_type": result.get("guard_type"),
        })
        key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    if isinstance(terminal_decision, dict):
        turn = _planner_ollama_turn_from_decision(terminal_decision, step=terminal_decision.get("step"))
        if turn:
            row = _drop_empty_dict_values({
                "step": terminal_decision.get("step"),
                "done_reason": turn.get("done_reason"),
                "done_seen": turn.get("done_seen"),
                "action": terminal_decision.get("action"),
                "tool": terminal_decision.get("tool"),
                "terminal": True,
            })
            key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
            if key not in seen:
                rows.append(row)
    return rows


def _planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _drop_empty_dict_values({
        "contract": (
            "Ollama done_reason closes one planner response turn only; "
            "3572 validator/finalization still decides job status."
        ),
        "ollama_turns": _ollama_turn_rows(history, terminal_decision),
        "successful_tool_turns": _successful_tool_turns(history),
    })


def _ollama_turn_summary_text(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> str:
    rows = _ollama_turn_rows(history, terminal_decision)
    if not rows:
        return ""
    lines = ["Turni Ollama conclusi:"]
    for row in rows:
        line = f"- step={row.get('step')} done_reason={row.get('done_reason')}"
        if row.get("action"):
            line += f" action={row.get('action')}"
        if row.get("tool"):
            line += f" tool={row.get('tool')}"
        if row.get("tool_ok") is not None:
            line += f" tool_ok={row.get('tool_ok')}"
        if row.get("guard_type"):
            line += f" guard_type={row.get('guard_type')}"
        if row.get("terminal"):
            line += " terminal=true"
        lines.append(line)
    return "\n".join(lines)


def _final_summary_with_ollama_done_reasons(
    status: str,
    final_summary: str,
    result: dict[str, Any],
) -> str:
    summary = str(final_summary or "").strip() or "Job terminale senza final_summary."
    if "Turni Ollama conclusi:" in summary:
        return summary
    history = result.get("history") if isinstance(result.get("history"), list) else []
    terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
    turn_text = _ollama_turn_summary_text(history, terminal_decision)
    if not turn_text:
        return summary
    suffix = turn_text
    if str(status or "") == "max_steps_reached":
        suffix += (
            "\nNota stato: i done_reason chiudono i turni Ollama; "
            "non equivalgono a completed senza final accettato dal validator 3572."
        )
    return summary + "\n\n" + suffix


# ---------------------------------------------------------------------------
# Controller guards / loop integrity helpers
# ---------------------------------------------------------------------------


def _normalize_tool_name(value: str) -> str:
    from .tool_contract import normalize_tool_name  # noqa: PLC0415 (lazy)
    return normalize_tool_name(value)


from .planner_core.cache import (
    _cached_tool_result,
    _tool_cache_hit,
    _tool_cache_key,
    _cached_vulkan_repair_result,
    _repair_cache_key,
    repeated_tool_call_count,
)


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    wanted = str(kind or "").lower()
    count = 0
    for item in history:
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if result.get("tool") != "controller_guard":
            continue
        combined = " ".join(
            str(x or "") for x in (result.get("summary"), decision.get("reason"))
        ).lower()
        if wanted and wanted in combined:
            count += 1
    return count


def _controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    rejected = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments")
        if decision.get(k) not in (None, "", [], {})
    }
    return {
        "violations": [str(v) for v in violations],
        "rejected_decision": rejected,
    }


def _controller_guard_rejection_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    key = _invalid_decision_signature_key(signature)
    if not key:
        return 0
    count = 0
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "controller_guard":
            continue
        existing = result.get("invalid_decision_signature")
        if not isinstance(existing, dict) or not existing:
            existing = _controller_guard_rejection_signature(
                {"violations": result.get("violations") if isinstance(result.get("violations"), list) else []},
                result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
            )
        if _invalid_decision_signature_key(existing) == key:
            count += 1
    return count


def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    combined = " ".join(
        str(decision.get(k) or "").lower()
        for k in ("reason", "final_answer", "raw_planner_text", "raw_planner_text_preview")
    )
    markers = (
        "planner stream degenerate output", "planner forced stream degenerate output",
        "planner emitted non-repairable non-json output", "no_json_object_candidate",
        "dead_or_stop_token_output", "role_boundary_marker", "role-boundary",
        "<|endoftext|>", ".readbyte",
    )
    return any(m in combined for m in markers)


def semantic_goal_classification(goal: str) -> dict[str, Any]:
    return _classify_goal_deliverable(goal, repo_analysis=_repo_analysis_goal(goal))


def goal_requires_code_product_report(goal: str) -> bool:
    classification = semantic_goal_classification(goal)
    return bool(classification.get("must_produce_code_product"))


def goal_has_write_intent(goal: str) -> bool:
    return goal_requests_apply(goal)


def history_has_tool(history: list[dict[str, Any]], tool_name: str) -> bool:
    for item in history:
        if not isinstance(item, dict):
            continue
        for field in ("tool_result", "decision"):
            d = item.get(field)
            if isinstance(d, dict) and d.get("tool") == tool_name:
                return True
    return False


def successful_code_edit_proposals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") == "repo_propose_code_edit" and result.get("ok") is True:
            proposals.append(result)
    return proposals


def _failed_code_edit_proposal_validation_row(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    if result.get("tool") != "repo_propose_code_edit" or result.get("ok") is not False:
        return {}
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    errors = [
        str(error)
        for error in (result.get("errors") or [])
        if str(error).strip()
    ]
    violations: list[str] = []
    if any(error == "unified_diff_missing" for error in errors):
        violations.append("repo_propose_code_edit_missing_unified_diff")
    if any(
        error.startswith("unidiff_parse_")
        or error in {
            "invalid_unified_diff_markers",
            "unified_diff_target_missing",
            "code_product_payload_not_complete",
        }
        for error in errors
    ):
        violations.append("invalid_code_product_candidate")
    if not violations:
        violations.append("code_product_payload_not_complete")
    violations.extend(f"repo_propose_code_edit_tool_error:{error}" for error in errors[:6])
    violations.append("code_product_route_shift_required")
    return {
        "step": item.get("step"),
        "guard_type": "tool_result_validation",
        "summary": "repo_propose_code_edit_failed: " + "; ".join(errors or ["ok_false"]),
        "classification": None,
        "semantic_goal_classification": None,
        "next_instruction": (
            "Previous repo_propose_code_edit returned ok=false. Do not repeat that proposal. "
            "Change decision now: provide a parser-valid complete unified_diff, complete "
            "old_text/new_text, write code_product_build_state with real progress, or typed block."
        ),
        "action_plan_candidate": "",
        "raw_planner_text_preview": "",
        "violations": list(dict.fromkeys(violations)),
        "rejected_decision": decision,
    }


CODE_PRODUCT_BUILD_STATE_KIND = "code_product_build_state"
CODE_PRODUCT_BUILD_STATE_SCHEMA = "code_product_build_state.v1"


def _code_product_build_state_section(target_file: str) -> str:
    target = _repo_rel_token(target_file)
    return f"{CODE_PRODUCT_BUILD_STATE_KIND}:{target}" if target and target != "." else CODE_PRODUCT_BUILD_STATE_KIND


def _code_product_build_state_parse(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return {}
    if not isinstance(parsed, dict) or parsed.get("schema") != CODE_PRODUCT_BUILD_STATE_SCHEMA:
        return {}
    return parsed


def _code_product_build_state_ready_payload(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict) or str(state.get("status") or "") != "ready_for_propose":
        return {}
    target = _repo_rel_token(state.get("target_file") or "")
    if not target or target == ".":
        return {}
    edit_kind = str(state.get("edit_kind") or "").strip()
    args: dict[str, Any] = {
        "target_file": target,
        "edit_kind": edit_kind,
        "rationale": str(state.get("rationale") or "").strip(),
    }
    if isinstance(state.get("validation_commands"), list):
        args["validation_commands"] = [
            str(cmd) for cmd in state.get("validation_commands") or [] if str(cmd).strip()
        ]
    if edit_kind == "unified_diff":
        if isinstance(state.get("unified_diff"), str) and state["unified_diff"].strip():
            args["unified_diff"] = state["unified_diff"]
        elif isinstance(state.get("old_text"), str) and isinstance(state.get("new_text"), str):
            args["old_text"] = state["old_text"]
            args["new_text"] = state["new_text"]
        else:
            return {}
    elif edit_kind == "structured_edit":
        operations = state.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            return {}
        args["structured_operations"] = operations
    elif edit_kind == "no_op":
        if not args["rationale"]:
            return {}
    else:
        return {}
    if not args.get("rationale"):
        return {}
    return args


def _code_product_build_state_has_collecting_progress(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        return False
    source_windows = state.get("source_windows")
    if isinstance(source_windows, list):
        for window in source_windows:
            if not isinstance(window, dict):
                continue
            has_identity = any(
                str(window.get(key) or "").strip()
                for key in ("document_id", "section", "sha256", "window_sha256")
            )
            has_window_marker = any(
                key in window
                for key in ("offset", "window_start", "window_end", "complete", "full_chars")
            )
            if has_identity and has_window_marker:
                return True
    for key in ("old_text", "new_text", "unified_diff"):
        if isinstance(state.get(key), str) and state[key].strip():
            return True
    operations = state.get("structured_operations")
    return isinstance(operations, list) and bool(operations)


def _code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return False
    sha256 = _text_hash(text)
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if (
            result.get("tool") == "planner_scratchpad_write"
            and result.get("ok") is True
            and str(result.get("mode") or "") == CODE_PRODUCT_BUILD_STATE_KIND
            and _repo_rel_token(result.get("target_file") or "") == target
            and str(result.get("sha256") or "") == sha256
        ):
            return True
    return False


def _code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {}
    tool = str(result.get("tool") or "")
    mode = str(result.get("mode") or "")
    if mode != CODE_PRODUCT_BUILD_STATE_KIND or tool not in {"planner_scratchpad_write", "planner_scratchpad_read"}:
        return {}
    base: dict[str, Any] = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "source_tool": tool,
        "document_id": result.get("document_id"),
        "section": result.get("section"),
        "target_file": _repo_rel_token(result.get("target_file") or ""),
        "status": result.get("status"),
        "sha256": result.get("sha256"),
        "complete_payload_ready": bool(result.get("complete_payload_ready")),
        "payload_loaded": False,
    }
    if tool == "planner_scratchpad_read":
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if not items:
            return {}
        for item in reversed(items):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            state = _code_product_build_state_parse(str(item.get("text") or ""))
            if state:
                base.update({
                    "document_id": item.get("document_id") or base.get("document_id"),
                    "section": item.get("section") or base.get("section"),
                    "target_file": _repo_rel_token(metadata.get("target_file") or state.get("target_file") or base.get("target_file") or ""),
                    "status": metadata.get("status") or state.get("status") or base.get("status"),
                    "sha256": item.get("sha256") or base.get("sha256"),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                    "full_chars": item.get("full_chars"),
                    "complete": item.get("complete"),
                    "has_more_after": item.get("has_more_after"),
                })
                ready_args = _code_product_build_state_ready_payload(state)
                base["payload_loaded"] = True
                base["state"] = state
                base["complete_payload_ready"] = bool(ready_args)
                if ready_args:
                    base["ready_arguments"] = ready_args
                return {k: v for k, v in base.items() if v not in (None, "", [], {})}
            if item.get("has_more_after") is True:
                base.update({
                    "document_id": item.get("document_id") or base.get("document_id"),
                    "section": item.get("section") or base.get("section"),
                    "target_file": _repo_rel_token(metadata.get("target_file") or base.get("target_file") or ""),
                    "status": metadata.get("status") or base.get("status"),
                    "sha256": item.get("sha256") or base.get("sha256"),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                    "full_chars": item.get("full_chars"),
                    "complete": item.get("complete"),
                    "has_more_after": item.get("has_more_after"),
                    "window_only": True,
                })
                return {k: v for k, v in base.items() if v not in (None, "", [], {})}
        return {}
    return {k: v for k, v in base.items() if v not in (None, "", [], {})}


def _latest_code_product_build_state(
    history: list[dict[str, Any]],
    target_file: str = "",
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    for item in reversed(history if isinstance(history, list) else []):
        result = _history_tool_result(item)
        state = _code_product_build_state_from_result(result)
        if not state:
            continue
        state_target = _repo_rel_token(state.get("target_file") or "")
        if target and target != "." and state_target and state_target != target:
            continue
        return state
    return {}


def _code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    target = _repo_rel_token(target_file or state.get("target_file") or "")
    args: dict[str, Any] = {
        "kind": CODE_PRODUCT_BUILD_STATE_KIND,
        "max_chars": 8000,
    }
    if state.get("document_id"):
        args["document_id"] = state.get("document_id")
        args["offset"] = int(state.get("window_end") or 0)
    elif target and target != ".":
        args["target_file"] = target
        args["section"] = _code_product_build_state_section(target)
        args["offset"] = 0
    else:
        args["section"] = CODE_PRODUCT_BUILD_STATE_KIND
        args["offset"] = 0
    return {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": args,
        "reason": "Read the internal code_product_build_state SQLite window before proposing a code product.",
    }


def _code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return []
    windows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in reversed(history if isinstance(history, list) else []):
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = _repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = _repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = _text_hash(text)
            if digest in seen:
                continue
            seen.add(digest)
            windows.append({
                "source_tool": "repo_read",
                "target_file": target,
                "section": f"repo_read:{target}",
                "window_start": int(sub.get("window_start") or 0),
                "window_end": int(sub.get("window_end") or len(text)),
                "full_chars": int(sub.get("full_chars") or len(text)),
                "window_chars": len(text),
                "complete": bool(sub.get("complete", sub.get("truncated") is not True)),
                "has_more_before": bool(sub.get("has_more_before", False)),
                "has_more_after": bool(sub.get("has_more_after", False)),
                "sha256": digest,
                "window_sha256": _text_hash(text),
            })
            if len(windows) >= max(1, int(limit or 1)):
                return windows
    return windows


def _code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return {}
    source_windows = _code_product_source_windows_from_reads(history or [], target)
    if not source_windows:
        return {}
    state = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "target_file": target,
        "status": "collecting_source",
        "source_windows": source_windows,
        "rationale": (
            "Verified repo_read source window captured. Continue by producing "
            "ready_for_propose with edit_kind=unified_diff and complete "
            "unified_diff or complete old_text/new_text, or blocked_incomplete "
            "with an explicit blocker."
        ),
    }
    state_text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if _code_product_build_state_duplicate_write(history or [], target_file=target, text=state_text):
        return {}
    return {
        "action": "tool",
        "tool": "planner_scratchpad_write",
        "arguments": {
            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
            "target_file": target,
            "status": "collecting_source",
            "section": _code_product_build_state_section(target),
            "max_chars": 8000,
            "text": state_text,
        },
        "reason": (
            "Persist a valid internal code_product_build_state with real repo_read "
            "source-window progress before attempting repo_propose_code_edit."
        ),
    }


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    args = state.get("ready_arguments") if isinstance(state.get("ready_arguments"), dict) else {}
    if not args:
        loaded_state = state.get("state") if isinstance(state.get("state"), dict) else {}
        args = _code_product_build_state_ready_payload(loaded_state)
    if not args:
        return {}
    return {
        "action": "tool",
        "tool": "repo_propose_code_edit",
        "arguments": args,
        "reason": (
            "Use ready internal code_product_build_state to produce the required report-only code product. "
            "Current violations: " + ", ".join(latest_violations or ["missing_code_product_candidate"])
        ),
    }


def _code_product_has_preview_substitute(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in {
                "content_preview",
                "unified_diff_preview",
                "structured_operations_preview",
                "preview_only",
            }:
                return True
            if _code_product_has_preview_substitute(item):
                return True
    if isinstance(value, list):
        return any(_code_product_has_preview_substitute(item) for item in value)
    if isinstance(value, str):
        low = value.lower()
        return "<truncated" in low or "[truncated" in low
    return False


def _code_product_payload_violations(proposal: dict[str, Any], read_paths: set[str]) -> list[str]:
    violations: list[str] = []
    if not isinstance(proposal, dict) or proposal.get("tool") != "repo_propose_code_edit" or proposal.get("ok") is not True:
        return ["missing_code_product_candidate"]
    if _code_product_has_preview_substitute(proposal):
        violations.append("code_product_payload_not_complete")
    if proposal.get("kind") != "code_edit_proposal":
        violations.append("invalid_code_product_candidate")
    target = _repo_rel_token(proposal.get("target_file") or proposal.get("path") or "")
    if not target or target == ".":
        violations.append("invalid_code_product_candidate")
    elif target not in read_paths:
        violations.append("code_product_target_not_read")
    if proposal.get("source_writes_performed") is not False:
        violations.append("invalid_code_product_candidate")
    if proposal.get("patch_application_performed") is not False:
        violations.append("invalid_code_product_candidate")
    if proposal.get("manual_review_required") is not True:
        violations.append("invalid_code_product_candidate")
    errors = proposal.get("errors")
    if isinstance(errors, list) and errors:
        violations.append("invalid_code_product_candidate")

    edit_kind = str(proposal.get("edit_kind") or "")
    if edit_kind == "unified_diff":
        diff_text = proposal.get("unified_diff")
        if not isinstance(diff_text, str) or not diff_text.strip():
            violations.append("code_product_payload_not_complete")
        else:
            if not all(marker in diff_text for marker in ("---", "+++", "@@")):
                violations.append("invalid_code_product_candidate")
            normalized = diff_text.replace("\\", "/")
            if (
                target
                and target != "."
                and target not in normalized
                and f"a/{target}" not in normalized
                and f"b/{target}" not in normalized
            ):
                violations.append("invalid_code_product_candidate")
    elif edit_kind == "structured_edit":
        operations = proposal.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            violations.append("code_product_payload_not_complete")
    elif edit_kind == "no_op":
        if not str(proposal.get("rationale") or "").strip():
            violations.append("invalid_code_product_candidate")
        if proposal.get("unified_diff") or proposal.get("structured_operations"):
            violations.append("invalid_code_product_candidate")
    else:
        violations.append("invalid_code_product_candidate")
    return list(dict.fromkeys(violations))


def _code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    old_text = _goal_exact_text_block(goal, "old_text")
    new_text = _goal_exact_text_block(goal, "new_text")
    if not (old_text and new_text):
        return {}
    args: dict[str, Any] = {
        "target_file": target,
        "edit_kind": "unified_diff",
        "rationale": (
            "Report-only unified diff from exact old_text/new_text supplied by the user."
        ),
        "old_text": old_text,
        "new_text": new_text,
        "validation_commands": ["git apply --check <complete-unified-diff-from-tool-payload>"],
    }
    return {
        "action": "tool",
        "tool": "repo_propose_code_edit",
        "arguments": args,
        "reason": (
            "Code-product final is blocked until repo_propose_code_edit returns ok=true "
            f"with a complete inline payload for {target}. Current violations: "
            + ", ".join(latest_violations or ["missing_code_product_candidate"])
        ),
    }


_CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS = {
    "repo_propose_code_edit_missing_unified_diff",
    "repo_propose_code_edit_missing_structured_operations",
    "code_product_payload_not_complete",
    "invalid_code_product_candidate",
}

_REPO_READ_WINDOW_SIGNATURE_KEYS = (
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


def _window_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _window_signature_value(sub)
            for key, sub in sorted(value.items(), key=lambda pair: str(pair[0]))
            if sub not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_window_signature_value(sub) for sub in value]
    try:
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
    except Exception:
        pass
    return value


def _repo_read_window_signature(args: dict[str, Any]) -> str:
    args = args if isinstance(args, dict) else {}
    if not any(key in args and args.get(key) not in (None, "", [], {}) for key in _REPO_READ_WINDOW_SIGNATURE_KEYS):
        return ""
    paths = [_repo_rel_token(path) for path in _decision_paths(args)]
    payload = {
        "paths": paths,
        "window": {
            key: _window_signature_value(args.get(key))
            for key in _REPO_READ_WINDOW_SIGNATURE_KEYS
            if key in args and args.get(key) not in (None, "", [], {})
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _planner_scratchpad_window_signature(args: dict[str, Any]) -> str:
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
        "target_file": _repo_rel_token(args.get("target_file") or "") if args.get("target_file") else "",
        "offset": _window_signature_value(args.get("offset") or 0),
        "max_chars": _window_signature_value(args.get("max_chars") or 3000),
        "limit": _window_signature_value(args.get("limit") or 3),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _successful_window_signatures(history: list[dict[str, Any]], tool: str) -> set[str]:
    wanted_tool = _normalize_tool_name(tool)
    signatures: set[str] = set()
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        result = _history_tool_result(row)
        if _normalize_tool_name(str(result.get("tool") or "")) != wanted_tool or result.get("ok") is not True:
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        if wanted_tool == "repo_read":
            signature = _repo_read_window_signature(args)
        elif wanted_tool == "planner_scratchpad_read":
            signature = _planner_scratchpad_window_signature(args)
        else:
            signature = ""
        if signature:
            signatures.add(signature)
    return signatures


def _repo_read_window_range_for_target(args: dict[str, Any], target_file: str) -> tuple[int, int] | None:
    args = args if isinstance(args, dict) else {}
    target = _repo_rel_token(target_file)
    if target not in {_repo_rel_token(path) for path in _decision_paths(args)}:
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


def _successful_repo_read_window_ranges(history: list[dict[str, Any]], target_file: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        result = _history_tool_result(row)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        item_range = _repo_read_window_range_for_target(args, target_file)
        if item_range and item_range not in ranges:
            ranges.append(item_range)
    return ranges


def _code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    target = _repo_rel_token(target_file)
    count = 0
    for item in validation_rejections if isinstance(validation_rejections, list) else []:
        if not isinstance(item, dict):
            continue
        violations = {str(v) for v in (item.get("violations") or [])}
        if not violations.intersection(_CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS):
            continue
        rejected = item.get("rejected_decision") if isinstance(item.get("rejected_decision"), dict) else {}
        if str(rejected.get("tool") or "") != "repo_propose_code_edit":
            continue
        args = rejected.get("arguments") if isinstance(rejected.get("arguments"), dict) else {}
        rejected_target = _repo_rel_token(args.get("target_file") or args.get("path") or "")
        if target and target != "." and rejected_target != target:
            continue
        count += 1
    return count


def _code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return {}
    try:
        total_lines = max(0, int(line_count or 0))
    except (TypeError, ValueError):
        total_lines = 0
    ranges = _successful_repo_read_window_ranges(history or [], target)
    next_line = 1
    if ranges:
        next_line = max(end for _, end in ranges) + 1
    if total_lines and next_line > total_lines:
        return {}
    after = max(120, min(360, int(total_lines or 240)))
    if total_lines:
        after = max(0, min(after, total_lines - next_line))
    args = {
        "path": target,
        "line": next_line,
        "before": 0,
        "after": after,
        "max_chars": _single_file_prompt_read_chars(),
    }
    if _repo_read_window_signature(args) in _successful_window_signatures(history or [], "repo_read"):
        return {}
    return {
        "action": "tool",
        "tool": "repo_read",
        "arguments": args,
        "reason": (
            "Route shift after invalid code-product payload: read a concrete source window "
            f"from {target} before proposing another complete inline diff."
        ),
    }


def _strip_duplicate_window_candidate(
    actions: list[dict[str, Any]],
    *,
    tool: str,
    signature: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    wanted_tool = _normalize_tool_name(tool)
    for item in actions if isinstance(actions, list) else []:
        if not isinstance(item, dict) or _normalize_tool_name(str(item.get("tool") or "")) != wanted_tool:
            out.append(item)
            continue
        args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        if wanted_tool == "repo_read":
            item_signature = _repo_read_window_signature(args)
        elif wanted_tool == "planner_scratchpad_read":
            item_signature = _planner_scratchpad_window_signature(args)
        else:
            item_signature = ""
        if item_signature and item_signature == signature:
            continue
        out.append(item)
    return out


def _apply_duplicate_window_replan_contract(
    contract: dict[str, Any],
    *,
    violation: str,
    tool: str,
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    signature = (
        _repo_read_window_signature(args)
        if tool == "repo_read"
        else _planner_scratchpad_window_signature(args)
        if tool == "planner_scratchpad_read"
        else ""
    )
    existing = _strip_duplicate_window_candidate(
        contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else [],
        tool=tool,
        signature=signature,
    )
    next_actions: list[dict[str, Any]] = []
    if tool == "planner_scratchpad_read":
        next_window = _planner_scratchpad_next_window_action_from_history(args, history)
        if next_window:
            next_actions.append(next_window)
        contract["required_next_progress"] = (
            "The requested SQLite window was already consumed. Replan now: read the next "
            "unconsumed SQLite window if candidate_next_actions provides one; otherwise use "
            "the already-read window evidence to produce a complete payload, write real "
            "code_product_build_state progress, or return a typed block. Do not repeat the "
            "same planner_scratchpad_read arguments."
        )
    elif tool == "repo_read":
        target_paths = _decision_paths(args)
        target = _repo_rel_token(target_paths[0]) if target_paths else ""
        line_count = 0
        for row in contract.get("verified_content_reads") or []:
            if isinstance(row, dict) and _repo_rel_token(row.get("path") or "") == target:
                try:
                    line_count = int(row.get("line_count") or 0)
                except (TypeError, ValueError):
                    line_count = 0
                break
        route_candidate = _code_product_source_window_candidate(target, line_count=line_count, history=history)
        if route_candidate:
            next_actions.append(route_candidate)
        if target:
            build_state_action = _code_product_build_state_write_action(target, history)
            if build_state_action:
                next_actions.append(build_state_action)
        contract["required_next_progress"] = (
            "The requested repo_read window already succeeded and a cache hit would not be progress. "
            "Replan now: read a different unconsumed source window if candidate_next_actions provides "
            "one; otherwise use verified_content_reads/required_working_set for the target and call "
            "repo_propose_code_edit only with a complete unified_diff or old_text/new_text, write "
            "code_product_build_state with real progress, or return a typed block."
        )
    merged: list[dict[str, Any]] = []
    for item in [*next_actions, *existing]:
        if not isinstance(item, dict):
            continue
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if any(json.dumps(prev, ensure_ascii=False, sort_keys=True, default=str) == key for prev in merged):
            continue
        merged.append(item)
    contract["candidate_next_actions"] = merged[:16]
    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    code_contract["duplicate_window_replan_required"] = True
    code_contract["duplicate_window_violation"] = violation
    contract["code_product_contract"] = code_contract
    return contract


def _code_product_action_has_complete_payload(action: dict[str, Any]) -> bool:
    if not isinstance(action, dict) or action.get("tool") != "repo_propose_code_edit":
        return True
    args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    edit_kind = str(args.get("edit_kind") or "")
    if edit_kind == "unified_diff":
        return bool(str(args.get("unified_diff") or "").strip()) or (
            isinstance(args.get("old_text"), str)
            and isinstance(args.get("new_text"), str)
            and not _copyable_example_text(args.get("old_text"))
            and not _copyable_example_text(args.get("new_text"))
        )
    if edit_kind == "structured_edit":
        return isinstance(args.get("structured_operations"), list) and bool(args.get("structured_operations"))
    if edit_kind == "no_op":
        return bool(str(args.get("rationale") or "").strip())
    return False


def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    target = _repo_rel_token(path)
    if target.endswith("__init__.py") or target.endswith("__main__.py"):
        return True
    rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
    for row in rows:
        if not isinstance(row, dict) or _repo_rel_token(row.get("path") or "") != target:
            continue
        try:
            return int(row.get("line_count") or 0) < 20
        except Exception:
            return True
    return False


def _goal_exact_text_block(goal: str, name: str) -> str:
    label = f"exact {name}:"
    lines = str(goal or "").splitlines()
    start = -1
    inline = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith(label):
            start = idx
            inline = stripped[len(label):]
            break
    if start < 0:
        return ""

    boundary_prefixes = (
        "exact old_text:",
        "exact new_text:",
        "required behavior:",
        "required behaviour:",
        "target file:",
    )
    block: list[str] = []
    if inline.strip():
        block.append(inline.lstrip())
    for line in lines[start + 1:]:
        low = line.strip().lower()
        if any(low.startswith(prefix) for prefix in boundary_prefixes):
            break
        block.append(line.rstrip("\r"))
    while block and not block[0].strip():
        block.pop(0)
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(block)


def _canonical_invalid_code_product_decision_signature(
    decision: dict[str, Any],
    violations: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "tool").strip().lower() != "tool":
        return {}
    tool = _normalize_tool_name(str(decision.get("tool") or ""))
    if tool != "repo_propose_code_edit":
        return {}
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    target = _repo_rel_token(args.get("target_file") or args.get("path") or "")
    edit_kind = str(args.get("edit_kind") or "").strip()
    violation_set = {str(v) for v in (violations or []) if str(v)}
    payload_class = ""
    if "repo_propose_code_edit_placeholder_text" in violation_set:
        payload_class = "placeholder_old_new"
    elif "repo_propose_code_edit_missing_unified_diff" in violation_set:
        payload_class = "missing_diff"
    elif "repo_propose_code_edit_old_text_not_from_verified_read" in violation_set:
        payload_class = "old_text_not_verified"
    elif "repo_propose_code_edit_missing_structured_operations" in violation_set:
        payload_class = "missing_structured_operations"
    elif "invalid_code_product_candidate" in violation_set or any(
        str(v).startswith("repo_propose_code_edit_unified_diff_error:")
        for v in violation_set
    ):
        payload_class = "invalid_unified_diff"
    elif edit_kind == "unified_diff":
        old_value = args.get("old_text")
        new_value = args.get("new_text")
        diff_text = args.get("unified_diff")
        if _copyable_example_text(old_value) or _copyable_example_text(new_value):
            payload_class = "placeholder_old_new"
        elif not isinstance(diff_text, str) or not diff_text.strip():
            payload_class = "missing_diff"
    if not (target and edit_kind and payload_class):
        return {}

    normalized_args = {
        "target_file": target,
        "edit_kind": edit_kind,
        "payload_class": payload_class,
        "old_text": _prompt_clip_text(args.get("old_text"), 500),
        "new_text": _prompt_clip_text(args.get("new_text"), 500),
        "unified_diff_sha256": _text_hash(str(args.get("unified_diff") or "")) if args.get("unified_diff") else "",
        "structured_operations_sha256": (
            _text_hash(json.dumps(args.get("structured_operations"), ensure_ascii=False, sort_keys=True, default=str))
            if args.get("structured_operations") is not None else ""
        ),
        "rationale": _prompt_clip_text(args.get("rationale"), 500),
    }
    args_sha256 = _text_hash(json.dumps(normalized_args, ensure_ascii=False, sort_keys=True, default=str))
    return {
        "tool": "repo_propose_code_edit",
        "target_file": target,
        "edit_kind": edit_kind,
        "payload_class": payload_class,
        "args_sha256": args_sha256,
    }


def _invalid_decision_signature_key(signature: dict[str, Any]) -> str:
    if not isinstance(signature, dict) or not signature:
        return ""
    return json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)


def _invalid_code_product_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    existing = result.get("invalid_decision_signature")
    if isinstance(existing, dict) and existing:
        return existing
    violations = result.get("violations") if isinstance(result.get("violations"), list) else []
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    if not rejected:
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if decision.get("action") == "tool":
            rejected = decision
    return _canonical_invalid_code_product_decision_signature(rejected, violations)


def _invalid_code_product_decision_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    key = _invalid_decision_signature_key(signature)
    if not key:
        return 0
    count = 0
    for item in history if isinstance(history, list) else []:
        item_key = _invalid_decision_signature_key(
            _invalid_code_product_decision_signature_from_history_item(item)
        )
        if item_key == key:
            count += 1
    return count


def _disallowed_invalid_code_product_signatures(
    validation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for row in validation_rejections if isinstance(validation_rejections, list) else []:
        if not isinstance(row, dict):
            continue
        existing = row.get("invalid_decision_signature")
        signature = existing if isinstance(existing, dict) else _canonical_invalid_code_product_decision_signature(
            row.get("rejected_decision") if isinstance(row.get("rejected_decision"), dict) else {},
            row.get("violations") if isinstance(row.get("violations"), list) else [],
        )
        key = _invalid_decision_signature_key(signature)
        if not key:
            continue
        if key not in counts:
            counts[key] = {"signature": signature, "count": 0}
        counts[key]["count"] = int(counts[key]["count"] or 0) + 1
    out = []
    for item in counts.values():
        if int(item.get("count") or 0) >= 2:
            out.append({
                **item["signature"],
                "repeat_count": int(item.get("count") or 0),
                "rule": "do_not_repeat_invalid_code_product_decision",
            })
    return out


def _compact_validation_rejections_tail(
    validation_rejections: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    index_by_signature: dict[str, int] = {}
    for item in validation_rejections:
        if not isinstance(item, dict):
            continue
        rejected = item.get("rejected_decision") if isinstance(item.get("rejected_decision"), dict) else {}
        args = rejected.get("arguments") if isinstance(rejected.get("arguments"), dict) else {}
        compact_args: dict[str, Any] = {}
        for key in (
            "target_file",
            "path",
            "edit_kind",
            "old_text",
            "new_text",
            "unified_diff",
            "structured_operations",
            "rationale",
        ):
            if key in args:
                value = args.get(key)
                if isinstance(value, str):
                    compact_args[key] = value if len(value) <= 700 else value[:700] + "...[truncated in rejection digest]"
                else:
                    compact_args[key] = value
        compact_rejected = {
            "action": rejected.get("action"),
            "tool": rejected.get("tool"),
            "arguments": compact_args,
            "reason": str(rejected.get("reason") or "")[:700],
        }
        row = {
            "step": item.get("step"),
            "guard_type": item.get("guard_type"),
            "summary": item.get("summary"),
            "classification": item.get("classification"),
            "semantic_goal_classification": item.get("semantic_goal_classification"),
            "next_instruction": item.get("next_instruction"),
            "action_plan_candidate": _prompt_clip_text(item.get("action_plan_candidate"), 4000),
            "raw_planner_text_preview": str(item.get("raw_planner_text_preview") or "")[:700],
            "violations": item.get("violations") or [],
            "rejected_decision": {
                k: v for k, v in compact_rejected.items() if v not in (None, "", [], {})
            },
            "invalid_decision_signature": (
                item.get("invalid_decision_signature")
                if isinstance(item.get("invalid_decision_signature"), dict)
                else _canonical_invalid_code_product_decision_signature(
                    compact_rejected,
                    item.get("violations") if isinstance(item.get("violations"), list) else [],
                )
            ),
            "repeat_count": 1,
        }
        if not row["invalid_decision_signature"]:
            row.pop("invalid_decision_signature", None)
        signature = json.dumps(
            {
                "guard_type": row.get("guard_type"),
                "violations": row.get("violations"),
                "invalid_decision_signature": row.get("invalid_decision_signature"),
                "rejected_decision": row.get("rejected_decision"),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        existing = index_by_signature.get(signature)
        if existing is not None:
            compacted[existing]["repeat_count"] = int(compacted[existing].get("repeat_count") or 1) + 1
            compacted[existing]["last_step"] = row.get("step")
            continue
        index_by_signature[signature] = len(compacted)
        compacted.append(row)
    return compacted[-limit:]


def summarize_history_artifacts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        r = item.get("tool_result")
        if not isinstance(r, dict):
            continue
        if r.get("artifact") or r.get("tool"):
            out.append({
                "step": item.get("step"), "tool": r.get("tool"),
                "ok": r.get("ok"), "artifact": r.get("artifact"), "path": r.get("path"),
            })
    return out[-10:]


def planner_done_token(raw_text: str) -> bool:
    text = str(raw_text or "").strip().strip("` \r\n\t.。").lower()
    return text in {
        "done", "completed", "complete", "finished",
        "terminato", "completato", "fatto", "eseguito", "выполнено",
    }


def extract_existing_goal_path(goal: str) -> str:
    for candidate in re.findall(
        r"([A-Za-z0-9_./\\-]+?\.(?:py|ps1|md|json|toml|yml|yaml|txt))", str(goal or "")
    ):
        normalized = _repo_rel_token(candidate)
        try:
            rel = safe_rel_path(normalized)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue
        if full.exists() and full.is_file():
            return rel
    return ""



# ---------------------------------------------------------------------------
# Planner evidence contract / validation gate
# ---------------------------------------------------------------------------


def requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    text = _semantic_goal_low(goal)
    patterns = (
        r"(?:first|primi|prime|top|limit|limite)\D{0,24}(\d{1,4})",
        r"(\d{1,4})\D{0,24}(?:file|files|py|python)",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return max(1, min(int(m.group(1)), 1000))
            except Exception:
                pass
    return default


def goal_requested_repo_scope(goal: str) -> str:
    """Resolve an explicit repo subdirectory mentioned by the user.

    `ai_carmine` is accepted as a spelling alias only when the repository has
    `ia_carmine` and no exact `ai_carmine` directory. The validator reports this
    alias in the evidence contract; it does not silently change a planner step.
    """
    low = _semantic_goal_low(goal).replace("\\", "/")
    candidates: list[str] = []
    for match in re.findall(r"(?:dentro|in|under|sotto)\s+([A-Za-z0-9_./-]+)", low):
        candidates.append(_repo_rel_token(match))
    if "ai_carmine" in low:
        candidates.append("ai_carmine")
    if "ia_carmine" in low:
        candidates.append("ia_carmine")
    for raw in candidates:
        if not raw:
            continue
        normalized = _repo_rel_token(raw)
        if normalized == "ai_carmine" and not (LAB_REPO / normalized).exists() and (LAB_REPO / "ia_carmine").is_dir():
            return "ia_carmine"
        try:
            rel = safe_rel_path(normalized)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
        except Exception:
            continue
        if full.exists() and full.is_dir():
            return rel
    return ""


def goal_requests_python_file_review(goal: str) -> bool:
    low = _semantic_goal_low(goal)
    wants_python_files = _has_any(low, ("python", ".py", "file py", "files py", "file python"))
    wants_read = _has_any(low, ("leggi", "read", "analizza", "analizzare", "descrivi", "dimmi", "serve", "servono"))
    wants_explain = _has_any(low, ("comportamento", "funzionamento", "cosa serv", "miglior", "improvement", "describe", "purpose"))
    return wants_python_files and wants_read and wants_explain


def _decision_paths(args: dict[str, Any]) -> list[str]:
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
        n = _repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def _paths_from_result(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    raw_paths = result.get("paths_preview") or result.get("paths")
    if isinstance(raw_paths, list):
        paths.extend(str(x) for x in raw_paths if str(x).strip())
    files = result.get("files_preview") or result.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
    entries = result.get("entries_preview") or result.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
            elif isinstance(item, str) and item.strip():
                paths.append(item)
    items = result.get("items") if isinstance(result.get("items"), list) else []
    for item in items:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item.get("path")))
    out: list[str] = []
    for path in paths:
        n = _repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def _paths_from_list_rows(list_rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in list_rows if isinstance(list_rows, list) else []:
        if not isinstance(row, dict):
            continue
        for raw in row.get("paths_preview") or []:
            p = _repo_rel_token(raw)
            if p and p not in out:
                out.append(p)
    return out


def latest_file_list_result(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history):
        result = _history_tool_result(item)
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok"):
            return result
    return {}


def successful_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in history:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read":
            continue
        for sub in result.get("items") or []:
            if isinstance(sub, dict) and sub.get("ok") and sub.get("path"):
                path = _repo_rel_token(sub.get("path"))
                if path not in out:
                    out.append(path)
    return out


def _verified_repo_read_content_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repo reads whose real content is present in the same successful result.

    Compact history may contain only path metadata or content_preview. The final
    gate must count only read evidence that can be transported to OpenWebUI as a
    real tool result: either the row already has ``content`` or the same
    successful repo_read result's artifact reloads to rows with ``content``.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = _repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if not path or path == ".":
                continue
            text, content_meta = _repo_read_item_full_content(sub)
            if text in (None, ""):
                content = sub.get("content")
                text = str(content or "")
            if not text:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(_drop_empty_dict_values({
                "path": path,
                "line_count": sub.get("line_count"),
                "truncated": sub.get("truncated"),
                "content_chars": len(text),
                "source": content_meta.get("source") or "repo_read_tool_result",
            }))
    return out


def failed_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in history:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read":
            continue
        for sub in result.get("items") or []:
            if isinstance(sub, dict) and sub.get("ok") is False and sub.get("path"):
                path = str(sub.get("path"))
                if path not in out:
                    out.append(path)
    return out


def _repo_reference_mentioned(low: str) -> bool:
    return any(term in low for term in ("repo", "repository", "progetto", "project"))


def _repo_analysis_intent_mentioned(low: str) -> bool:
    return any(term in low for term in (
        "analizza", "anlizza", "analisi", "analyze", "analyse", "analysis",
        "inspect", "inspection", "esplora", "scansiona", "struttura", "structure",
        "overview", "mappa",
    ))


def _repo_analysis_goal(goal: str) -> bool:
    low = _semantic_goal_low(goal)
    repo_terms = (
        "analyze the repository", "analizza la repo", "analizza il repo",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "repository structure", "repo structure", "struttura repo",
        "analyze repo", "analisi repo", "structure and content",
        "project inspection", "local project evidence",
        "documentation", "documentazione", "docs", "examples", "diagrams",
        "gpu coordination", "heap pointer", "recovery turns",
        "deferred evidence", "packet_review_only", "gpu1", "gpu0",
        "npu sidecar",
    )
    scoped_terms = (
        "analyze the ", "analyse the ", "analizza ", "analisi ",
        "directory", "cartella", "folder", "path",
    )
    write_terms = ("patch", "fix", "modifica", "correggi", "apply", "write", "edit")
    if any(t in low for t in write_terms):
        return False
    if _input_error_goal(goal):
        return False
    if any(t in low for t in repo_terms):
        return True
    if _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low):
        return True
    # Scoped inspection requests such as "analyze the ai_carmine directory" are
    # repository-analysis goals even if they do not say "repository".  Without
    # this, final_allowed falls through to the generic default after one root
    # repo_tree and produces the repeated template answer.
    if goal_requested_repo_scope(goal) and any(t in low for t in scoped_terms):
        return True
    return False


def _should_preseed_root_surface(goal: str, original_args: dict[str, Any]) -> bool:
    """Decide whether the controller should expose root surface evidence first.

    This is deterministic evidence collection for clear, sparse repo-analysis
    goals. It does not choose the next planner action and does not finalize.
    """
    args = original_args if isinstance(original_args, dict) else {}
    requested_function = str(args.get("function") or "").strip()
    if requested_function == "repo_tree":
        return True
    if _input_error_goal(goal) or goal_has_write_intent(goal):
        return False
    low = _semantic_goal_low(goal)
    generic_repo_terms = (
        "analizza la repo", "analizza il repo", "analizza la repository",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "analisi repo", "analisi della repo", "analisi della repository",
        "analyze repo", "analyze the repo", "analyze the repository",
        "repository analysis", "repo analysis", "repo structure",
        "repository structure", "struttura repo", "struttura della repo",
        "struttura della repository", "project structure", "surface project",
        "suggerimenti implementativi", "implementation suggestions",
        "dai suggerimenti", "find problems", "trova problemi",
    )
    return any(term in low for term in generic_repo_terms) or (
        _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low)
    )


def _goal_target_file(goal: str) -> str:
    return extract_existing_goal_path(goal)


def _goal_target_scope(goal: str) -> str:
    if _goal_target_file(goal):
        return ""
    return _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)


def _goal_target_kind(goal: str) -> str:
    if _goal_target_file(goal):
        return "file"
    if _goal_target_scope(goal):
        return "directory"
    if _repo_analysis_goal(goal):
        return "repository"
    return "other"


def _controller_memory_target_key(goal: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    target_file = str(contract.get("resolved_goal_file") or _goal_target_file(goal) or "")
    if target_file:
        return "file:" + _repo_rel_token(target_file)
    target_scope = str(contract.get("resolved_goal_scope") or _goal_target_scope(goal) or "")
    if target_scope:
        return "scope:" + _repo_rel_token(target_scope)
    return "repo:root" if _repo_analysis_goal(goal) else "goal:general"


def _single_file_prompt_read_chars() -> int:
    return max(2000, min(10000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000) // 2))


def _multi_file_prompt_read_chars() -> int:
    return max(2000, min(6000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000) // 4))


def _controller_preseed_plan(goal: str, original_args: dict[str, Any]) -> dict[str, Any] | None:
    target_file = _goal_target_file(goal)
    if target_file:
        return {
            "event": "controller_preseed_file_surface",
            "result_event": "controller_preseed_file_surface_result",
            "tool": "repo_read",
            "arguments": {"path": target_file, "max_chars": _single_file_prompt_read_chars()},
            "reason": "explicit_file_request_needs_file_surface",
            "artifact_suffix": "file_surface-repo_read",
        }
    target_scope = _goal_target_scope(goal)
    if target_scope:
        return {
            "event": "controller_preseed_scope_surface",
            "result_event": "controller_preseed_scope_surface_result",
            "tool": "repo_list_files",
            "arguments": {"path": target_scope, "limit": 120},
            "reason": "explicit_directory_request_needs_scope_surface",
            "artifact_suffix": "scope_surface-repo_list_files",
        }
    if _should_preseed_root_surface(goal, original_args):
        return {
            "event": "controller_preseed_root_surface",
            "result_event": "controller_preseed_root_surface_result",
            "tool": "repo_tree",
            "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
            "reason": "generic_repo_request_needs_root_surface",
            "artifact_suffix": "root_surface-repo_tree",
            "dynamic_initial_orientation": True,
        }
    return None


def _controller_file_code_product_orientation_preseed_plan(goal: str) -> dict[str, Any] | None:
    if not _goal_target_file(goal) or not goal_requires_code_product_report(goal):
        return None
    return {
        "event": "controller_preseed_file_code_product_orientation",
        "result_event": "controller_preseed_file_code_product_orientation_result",
        "tool": "repo_tree",
        "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
        "reason": "file_code_product_request_needs_dynamic_repo_orientation",
        "artifact_suffix": "file_code_product_orientation-repo_tree",
        "dynamic_initial_orientation": True,
    }


SCOPED_CONCRETE_READ_TARGET = 10
REPO_CONCRETE_READ_TARGET = 20

_NAMED_READ_PRIORITY = {
    "agents.md": 0,
    "readme.md": 1,
}

_INITIAL_DOC_NAME_PRIORITY = {
    "AGENTS.md": 0,
    "README.md": 1,
}

_GENERIC_READABLE_SUFFIXES = (
    ".bat", ".c", ".cfg", ".cmd", ".cpp", ".cs", ".csv", ".go", ".h",
    ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".md", ".ps1", ".py",
    ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
)


def _repo_existing_file(path: str) -> bool:
    try:
        rel = safe_rel_path(_repo_rel_token(path))
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists() and full.is_file()
    except Exception:
        return False


def _repo_existing_dir(path: str) -> bool:
    try:
        rel = safe_rel_path(_repo_rel_token(path))
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists() and full.is_dir()
    except Exception:
        return False


def _root_surface_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("entries", "entries_preview", "files", "files_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if not isinstance(value, list):
            continue
        for raw in value:
            if isinstance(raw, dict):
                path = _repo_rel_token(raw.get("path") or "")
                kind = str(raw.get("kind") or "")
            else:
                path = _repo_rel_token(raw)
                kind = ""
            if not path or path == ".":
                continue
            if not kind:
                kind = _repo_path_kind(path)
            row = {"path": path, "kind": kind}
            if row not in entries:
                entries.append(row)
    return entries


def _root_surface_file_paths(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for entry in _root_surface_entries(result):
        path = str(entry.get("path") or "")
        if entry.get("kind") == "file" and _repo_existing_file(path) and path not in paths:
            paths.append(path)
    return paths


def _root_surface_dir_paths(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for entry in _root_surface_entries(result):
        path = str(entry.get("path") or "")
        if entry.get("kind") == "dir" and _repo_existing_dir(path) and path not in paths:
            paths.append(path)
    return paths


def _initial_doc_sort_key(path: str) -> tuple[int, int, str]:
    p = _repo_rel_token(path)
    name = p.rsplit("/", 1)[-1].lower()
    priority = _NAMED_READ_PRIORITY.get(name, len(_NAMED_READ_PRIORITY))
    depth = p.count("/")
    return (priority, depth, p.lower())


def _controller_initial_doc_preseed_plan(root_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    files = _root_surface_file_paths(root_result)
    docs = [path for path in files if _repo_doc_or_config(path)]
    docs = sorted(docs, key=_initial_doc_sort_key)
    selected = docs[:SCOPED_CONCRETE_READ_TARGET]

    skipped: list[dict[str, Any]] = []
    seen_names = {p.rsplit("/", 1)[-1] for p in files}
    for name in _INITIAL_DOC_NAME_PRIORITY:
        if name not in seen_names:
            skipped.append({
                "candidate": name,
                "reason": "not_seen_in_root_surface",
                "stage": "initial_doc_read",
            })
    if docs and not selected:
        skipped.append({
            "candidate_count": len(docs),
            "reason": "doc_candidate_budget_exhausted",
            "stage": "initial_doc_read",
        })
    if not selected:
        return None, skipped

    return {
        "event": "controller_preseed_initial_docs",
        "result_event": "controller_preseed_initial_docs_result",
        "tool": "repo_read",
        "arguments": {"paths": selected, "max_chars": _multi_file_prompt_read_chars()},
        "reason": "generic_repo_request_needs_existing_initial_docs_from_root_surface",
        "artifact_suffix": "initial_docs-repo_read",
        "dynamic_initial_orientation": True,
    }, skipped


def _initial_area_sort_key(path: str) -> tuple[int, str]:
    top = _top_dir(path)
    return (top.count("/"), top.lower())


def _controller_initial_area_list_plans(root_result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dirs: list[str] = []
    for path in _root_surface_dir_paths(root_result):
        top = _top_dir(path)
        if (
            top
            and top not in dirs
            and not _low_signal_top_dir(top)
            and _repo_existing_dir(top)
        ):
            dirs.append(top)

    selected = sorted(dirs, key=_initial_area_sort_key)[:3]
    skipped: list[dict[str, Any]] = []

    plans = [
        {
            "event": "controller_preseed_initial_area_list",
            "result_event": "controller_preseed_initial_area_list_result",
            "tool": "repo_list_files",
            "arguments": {"path": area, "limit": 120, "max_depth": 3},
            "reason": "generic_repo_request_needs_existing_useful_area_file_surface",
            "artifact_suffix": f"initial_area_{safe_rel_path(area).replace('/', '__')}-repo_list_files",
            "dynamic_initial_orientation": True,
        }
        for area in selected
    ]
    return plans, skipped


def _list_result_file_paths(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("paths", "paths_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if isinstance(value, list):
            for raw in value:
                path = _repo_rel_token(raw)
                if _repo_existing_file(path) and path not in paths:
                    paths.append(path)
    for key in ("files", "files_preview"):
        value = result.get(key) if isinstance(result, dict) else None
        if isinstance(value, list):
            for raw in value:
                path = _repo_rel_token(raw.get("path") if isinstance(raw, dict) else raw)
                if _repo_existing_file(path) and path not in paths:
                    paths.append(path)
    return paths


def _initial_area_file_sort_key(path: str) -> tuple[int, int, str]:
    p = _repo_rel_token(path)
    name = p.rsplit("/", 1)[-1].lower()
    priority = _NAMED_READ_PRIORITY.get(name, len(_NAMED_READ_PRIORITY))
    if _repo_doc_or_config(p):
        kind_rank = 0
    elif _repo_code_file(p):
        kind_rank = 1
    else:
        kind_rank = 2
    return (priority, kind_rank, p.lower())


def _controller_initial_area_read_plan(list_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    area = _repo_rel_token(list_result.get("path") or "")
    candidates = [
        path for path in _list_result_file_paths(list_result)
        if (_repo_doc_or_config(path) or _repo_code_file(path))
    ]
    candidates = sorted(candidates, key=_initial_area_file_sort_key)
    if not candidates:
        return None, [{
            "candidate": area,
            "reason": "no_existing_doc_or_code_file_in_area_list_result",
            "stage": "initial_area_read",
        }]
    selected = candidates[0]
    return {
        "event": "controller_preseed_initial_area_read",
        "result_event": "controller_preseed_initial_area_read_result",
        "tool": "repo_read",
        "arguments": {"path": selected, "max_chars": _single_file_prompt_read_chars()},
        "reason": "generic_repo_request_needs_concrete_file_read_inside_useful_area",
        "artifact_suffix": f"initial_area_{safe_rel_path(selected).replace('/', '__')}-repo_read",
        "dynamic_initial_orientation": True,
    }, []


def _repo_path_kind(path: str) -> str:
    p = _repo_rel_token(path)
    try:
        full = (LAB_REPO / p).resolve(strict=False)
        full.relative_to(LAB_REPO)
        if full.exists() and full.is_file():
            return "file"
        if full.exists() and full.is_dir():
            return "dir"
    except Exception:
        pass
    name = p.rsplit("/", 1)[-1].lower()
    if "." in name and not p.endswith("/"):
        return "file"
    return "dir"


def _repo_doc_or_config(path: str) -> bool:
    p = _repo_rel_token(path)
    if not p or p == "." or _repo_path_kind(p) == "dir":
        return False
    name = p.rsplit("/", 1)[-1].lower()
    return (
        p.lower().endswith(".md")
        or name in {"pyproject.toml", "package.json", "requirements.txt", "setup.py", "setup.cfg", "tox.ini"}
        or name.startswith("modelfile")
        or name in {"makefile", "dockerfile"}
    )


def _repo_code_file(path: str) -> bool:
    p = _repo_rel_token(path).lower()
    return p.endswith((
        ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".cpp", ".c",
        ".h", ".cs", ".java", ".kt", ".swift", ".sh", ".bat", ".cmd"
    ))


def _repo_readable_evidence_file(path: str) -> bool:
    p = _repo_rel_token(path)
    if not p or p == "." or _repo_path_kind(p) == "dir":
        return False
    return _repo_doc_or_config(p) or _repo_code_file(p) or p.lower().endswith(_GENERIC_READABLE_SUFFIXES)


def _read_candidate_sort_key(path: str) -> tuple[int, int, int, int, str]:
    p = _repo_rel_token(path)
    low = p.lower()
    name = low.rsplit("/", 1)[-1]
    if name in _NAMED_READ_PRIORITY:
        return (_NAMED_READ_PRIORITY[name], 0, p.count("/"), 0, low)
    package_marker = name in {"__init__.py", "__main__.py"}
    fixture = "/fixtures/" in low or low.endswith("_fixture.json") or "/tests/fixtures/" in low
    if _repo_code_file(p):
        kind_rank = 0
    elif _repo_doc_or_config(p):
        kind_rank = 1
    else:
        kind_rank = 2
    area_rank = 0
    if "/_shared/" in low or low.startswith("ia_carmine/_shared/"):
        area_rank = 0
    elif low.startswith("ia_carmine/context/"):
        area_rank = 1
    elif low.startswith("ia_carmine/"):
        area_rank = 2
    penalty = 0
    if package_marker:
        penalty += 50
    if fixture:
        penalty += 40
    if low.endswith(".json") and not _repo_doc_or_config(p):
        penalty += 10
    return (len(_NAMED_READ_PRIORITY) + kind_rank, penalty, area_rank, p.count("/"), low)


def _dynamic_read_candidate_paths(
    paths: list[str],
    *,
    read_ok: set[str] | None = None,
    target_scope: str = "",
) -> list[str]:
    already = read_ok or set()
    target_scope = _repo_rel_token(target_scope)
    priority: list[str] = []
    regular: list[str] = []
    seen: set[str] = set()

    for raw in paths:
        p = _repo_rel_token(raw)
        if not p or p in seen or p in already:
            continue
        if target_scope and not _path_under_scope(p, target_scope):
            continue
        if not _repo_readable_evidence_file(p):
            continue
        seen.add(p)
        name = p.rsplit("/", 1)[-1].lower()
        if name in _NAMED_READ_PRIORITY:
            priority.append(p)
            continue
        regular.append(p)

    priority.sort(key=lambda p: (_NAMED_READ_PRIORITY[p.rsplit("/", 1)[-1].lower()], p.count("/"), p.lower()))
    regular.sort(key=_read_candidate_sort_key)
    return priority + regular


def _scope_candidate_source_paths(list_rows: list[dict[str, Any]], target_scope: str) -> list[str]:
    target_scope = _repo_rel_token(target_scope)
    paths: list[str] = []
    if not target_scope:
        return paths
    for row in list_rows:
        for raw in row.get("paths_preview") or []:
            p = _repo_rel_token(raw)
            if p and _path_under_scope(p, target_scope) and p not in paths:
                paths.append(p)
    return paths


def _scope_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    target_scope: str,
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    already = set(read_ok or [])
    return _dynamic_read_candidate_paths(
        _scope_candidate_source_paths(list_rows, target_scope),
        read_ok=already,
        target_scope=target_scope,
    )


def _meaningful_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    already = set(read_ok or [])
    out: list[str] = []
    for row in list_rows:
        area = _repo_rel_token(row.get("path") or "")
        if area in ("", ".") or _low_signal_top_dir(area):
            continue
        row_paths = [
            _repo_rel_token(p)
            for p in (row.get("paths_preview") or [])
            if _path_under_scope(_repo_rel_token(p), area)
        ]
        for p in _dynamic_read_candidate_paths(row_paths, read_ok=already, target_scope=area):
            if p not in out:
                out.append(p)
    return out


def _scoped_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(SCOPED_CONCRETE_READ_TARGET, len(available_candidates))


def _repo_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(REPO_CONCRETE_READ_TARGET, len(available_candidates))


def _top_dir(path: str) -> str:
    p = _repo_rel_token(path).strip("/")
    return p.split("/", 1)[0] if "/" in p else p


def _low_signal_top_dir(path: str) -> bool:
    top = _top_dir(path).lower()
    return (
        not top
        or top in {".git", ".github", ".vscode", ".codex", "__pycache__", ".pytest_cache"}
        or top in {"assets", "docs", "chatgpt", "examples", "patch_specs"}
        or top.endswith(".md")
    )


def _append_unique(seq: list[Any], value: Any) -> None:
    if value in (None, "", [], {}):
        return
    item = _repo_rel_token(value) if isinstance(value, str) else value
    if item not in seq:
        seq.append(item)


def _read_items_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in history if isinstance(history, list) else []:
        result = _history_tool_result(row)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        source = _same_tool_artifact_payload(result)
        source_items = source.get("items") if isinstance(source.get("items"), list) else result.get("items")
        for read_item in result.get("items") or []:
            if isinstance(read_item, dict) and read_item.get("ok"):
                item = dict(read_item)
                for source_item in source_items or []:
                    if (
                        isinstance(source_item, dict)
                        and _repo_rel_token(source_item.get("path") or "") == _repo_rel_token(item.get("path") or "")
                    ):
                        item.setdefault("artifact", source_item.get("artifact"))
                        if source_item.get("content") not in (None, ""):
                            item.setdefault("content", source_item.get("content"))
                        break
                item.setdefault("step", row.get("step"))
                item["path"] = _repo_rel_token(item.get("path") or "")
                items.append(item)
    return items


def _extract_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in str(content or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
            if heading and heading not in headings:
                headings.append(heading)
        if len(headings) >= 12:
            break
    return headings


def _extract_key_lines(content: str) -> list[str]:
    key_lines: list[str] = []
    needles = (
        "entrypoint", "entry point", "canonical", "workflow", "runtime", "heap",
        "provider", "tool", "problem", "issue", "fix", "expected", "must ",
        "non-negotiable", "limitation", "core", "memory", "context", "chunk",
    )
    for line in str(content or "").splitlines():
        s = line.strip()
        if not s or len(s) > 240:
            continue
        low = s.lower()
        if s.startswith("#") or any(n in low for n in needles) or "/" in s:
            if s not in key_lines:
                key_lines.append(s)
        if len(key_lines) >= 16:
            break
    return key_lines


def _extract_mentioned_paths(content: str) -> list[str]:
    paths: list[str] = []
    pattern = r'(?<![\w.-])(?:[A-Za-z0-9_.@+-]+/){1,}[A-Za-z0-9_.@+ -]+(?:\.[A-Za-z0-9_+-]+)?'
    for match in re.finditer(pattern, str(content or "")):
        p = _repo_rel_token(match.group(0).strip("`\"'.,);:"))
        if p and p != "." and p not in paths:
            paths.append(p)
        if len(paths) >= 24:
            break
    return paths


def _file_memory_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    memory: list[dict[str, Any]] = []
    for item in _read_items_from_history(history):
        content = str(item.get("content") or item.get("content_preview") or "")
        path = _repo_rel_token(item.get("path") or "")
        if not path:
            continue
        memory.append({
            "path": path,
            "line_count": item.get("line_count"),
            "truncated": item.get("truncated"),
            "headings": _extract_headings(content),
            "key_lines": _extract_key_lines(content),
            "mentioned_paths": _extract_mentioned_paths(content),
            "content_excerpt": content[:1800],
        })
    return memory


def _repo_list_evidence(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        tool = str(result.get("tool") or "")
        if tool not in {"repo_list_files", "repo_tree"} or not result.get("ok"):
            continue

        paths: list[str] = []
        keys = ("paths", "paths_preview") if tool == "repo_list_files" else ("entries", "entries_preview", "files", "files_preview")
        sources = [result]
        raw_payload = _same_tool_artifact_payload(result)
        if isinstance(raw_payload, dict):
            sources.append(raw_payload)
        for source in sources:
            for key in keys:
                value = source.get(key)
                if not isinstance(value, list):
                    continue
                for raw in value:
                    p = raw.get("path") if isinstance(raw, dict) else raw
                    p = _repo_rel_token(p or "")
                    if p and p not in paths:
                        paths.append(p)

        rows.append({
            "step": item.get("step"),
            "tool": tool,
            "path": _repo_rel_token(result.get("path") or "."),
            "total_matches": result.get("total_matches") if tool == "repo_list_files" else result.get("entries_total") or result.get("count"),
            "limit": result.get("limit"),
            "truncated": result.get("truncated"),
            "paths_preview": paths[:80],
        })
    return rows


def failed_repo_list_files_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in history if isinstance(history, list) else []:
        result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") != "repo_list_files" or result.get("ok") is not False:
            continue
        path = _repo_rel_token(result.get("path") or "")
        if path and path not in paths:
            paths.append(path)
    return paths


def _rank_core_candidates(file_memory: list[dict[str, Any]], list_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}

    def add(path: str, score: int, reason: str) -> None:
        top = _top_dir(path)
        if not top or _low_signal_top_dir(top):
            return
        # Mentioned paths can come from prose such as "GPU0/NPU sidecar completion".
        # Do not promote prose fragments into repo_list_files candidates unless the
        # top-level directory actually exists in the checked repository.
        try:
            full = (LAB_REPO / safe_rel_path(top)).resolve(strict=False)
            full.relative_to(LAB_REPO)
            if not full.exists() or not full.is_dir():
                return
        except Exception:
            return
        scores[top] = scores.get(top, 0) + score
        reasons.setdefault(top, [])
        if reason not in reasons[top]:
            reasons[top].append(reason)

    for row in list_rows:
        p = _repo_rel_token(row.get("path") or "")
        if p and p != ".":
            add(p, 25, "listed non-root directory")
        for sub in row.get("paths_preview") or []:
            add(sub, 20 if _repo_code_file(sub) else 8, "listed code/file evidence" if _repo_code_file(sub) else "listed path evidence")

    for item in file_memory:
        for p in item.get("mentioned_paths") or []:
            add(p, 18 if _repo_code_file(p) else 6, "mentioned by read documentation")
        for line in item.get("key_lines") or []:
            for p in _extract_mentioned_paths(line):
                add(p, 18 if _repo_code_file(p) else 6, "mentioned by key evidence line")

    ranked = sorted(scores, key=lambda k: (-scores[k], k.lower()))
    return [{"path": p, "score": scores[p], "reasons": reasons.get(p, [])[:6]} for p in ranked[:12]]


def _normalize_scope_claim_text(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("\\", "/")
        .replace("è", "e")
        .replace("é", "e")
        .replace("'", " ")
    )


def _claim_area_from_user_token(raw_area: str, target_scope: str = "") -> str:
    area = _repo_rel_token(raw_area)
    if area.lower() == "shared":
        area = "_shared"
    scope = _repo_rel_token(target_scope)
    if area == "_shared" and scope and scope != ".":
        if scope.endswith("/_shared") or scope == "_shared":
            return scope
        scoped_area = f"{scope.rstrip('/')}/_shared"
        if _path_exists_repo_relative(scoped_area):
            return scoped_area
    if area == "_shared" and _path_exists_repo_relative("ia_carmine/_shared"):
        return "ia_carmine/_shared"
    return area


def _user_scope_claims(goal: str, target_scope: str = "") -> list[dict[str, Any]]:
    """Extract user scope claims as evidence, not as a static blacklist."""
    text = str(goal or "")
    low = _normalize_scope_claim_text(text)
    patterns = (
        r"(?P<area>(?:[\w.+-]+/)*_shared|shared)\b.{0,180}\b(?:non\s+(?:e\s+)?(?:il\s+|la\s+)?core|not\s+(?:the\s+)?core)\b",
        r"(?P<area>(?:[\w.+-]+/)*_shared|shared)\b.{0,180}\b(?:solo|only)\b.{0,120}\b(?:script|util|utility)\b",
    )
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, low, flags=re.IGNORECASE | re.DOTALL):
            area = _claim_area_from_user_token(match.group("area"), target_scope)
            if not area or area == ".":
                continue
            key = (area, "not_core")
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            claims.append({
                "area": area,
                "claim": "not_core",
                "source": "user_request",
                "text": text[start:end].strip(),
                "validator_effect": "requires_read_evidence_for_conflicting_patch_target",
            })
    return claims


def _scope_claim_conflict_for_path(path: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    p = _repo_rel_token(path).strip("/")
    low = p.lower()
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or str(claim.get("claim") or "") != "not_core":
            continue
        area = _repo_rel_token(claim.get("area") or "").strip("/").lower()
        if not area:
            continue
        if area in {"_shared", "shared"}:
            if low.startswith("_shared/") or "/_shared/" in f"/{low}/":
                return claim
            continue
        if low == area or low.startswith(area + "/"):
            return claim
    return {}


def _add_core_discovery_candidate(
    out: list[dict[str, Any]],
    seen: set[str],
    *,
    path: str,
    source: str,
    rank: int,
    reason: str,
    read_ok: set[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
    score: Any = None,
    ranking_source: str = "",
) -> bool:
    p = _repo_rel_token(path)
    if not p or p == "." or p in seen or p in read_ok:
        return False
    if target_scope and not _path_under_scope(p, target_scope):
        return False
    if not _path_exists_repo_relative(p) or not _repo_readable_evidence_file(p):
        return False
    seen.add(p)
    conflict = _scope_claim_conflict_for_path(p, user_scope_claims)
    candidate = {
        "path": p,
        "next_tool": "repo_read",
        "source": source,
        "rank": rank,
        "reason": reason,
        "lab_repo": str(LAB_REPO),
        "claim_conflict": bool(conflict),
    }
    if ranking_source:
        candidate["ranking_source"] = ranking_source
    if score is not None:
        candidate["score"] = score
    if conflict:
        candidate["conflicting_user_scope_claim"] = conflict
        candidate["required_after_read"] = (
            "If patching this target, rationale must explain why read content proves it is core."
        )
    out.append(candidate)
    return True


def _core_discovery_candidates_from_intrinsic(
    *,
    intrinsic_context: dict[str, Any] | None,
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    already = {_repo_rel_token(path) for path in read_ok}
    status: dict[str, Any] = {
        "schema": "core_discovery_status.v1",
        "lab_repo": str(LAB_REPO),
        "discovery_only": True,
        "patch_authorized_by_ranking": False,
        "source": "none",
        "rebuild_performed": False,
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    rag = (
        intrinsic_context.get("retrieved_rag_chunks")
        if isinstance(intrinsic_context, dict)
        and isinstance(intrinsic_context.get("retrieved_rag_chunks"), dict)
        else {}
    )
    rag_items = rag.get("items") if isinstance(rag.get("items"), list) else []
    ranking_source = str(rag.get("ranking_source") or "")
    stale_or_unusable = 0
    status.update({
        "rag_status": rag.get("status") if rag else None,
        "rag_ranking_source": ranking_source or None,
        "rag_item_count": len(rag_items),
    })
    for rank, item in enumerate(rag_items, start=1):
        if not isinstance(item, dict):
            continue
        path = _repo_rel_token(item.get("path") or item.get("source_path") or "")
        before_count = len(candidates)
        added = _add_core_discovery_candidate(
            candidates,
            seen,
            path=path,
            source="retrieved_rag_chunks",
            rank=rank,
            reason="RAG/FTS/rerank candidate under current LAB_REPO; read before deciding patch target.",
            read_ok=already,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
            score=item.get("rerank_score", item.get("score")),
            ranking_source=ranking_source,
        )
        if not added and path and len(candidates) == before_count:
            stale_or_unusable += 1
    if candidates:
        status["source"] = "rag_current_lab_repo"
        status["rag_stale_or_unusable_count"] = stale_or_unusable
        return candidates[:16], status

    rebuilt_paths = (
        _scope_read_candidates_from_evidence(list_rows, target_scope, read_ok=already)
        if target_scope else
        _meaningful_read_candidates_from_evidence(list_rows, read_ok=already)
    )
    for rank, path in enumerate(rebuilt_paths[:16], start=1):
        _add_core_discovery_candidate(
            candidates,
            seen,
            path=path,
            source="lab_repo_evidence_rebuild",
            rank=rank,
            reason="Runtime ranking rebuilt from current LAB_REPO list evidence.",
            read_ok=already,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
            ranking_source="current_lab_repo_evidence",
        )
    if candidates:
        status["source"] = "ranking_rebuilt_from_lab_repo_evidence"
        status["rebuild_performed"] = bool(rag_items or stale_or_unusable or (rag and rag.get("status") != "ready"))
        status["rag_stale_or_unusable_count"] = stale_or_unusable
        status["reason"] = (
            "RAG ranking was missing or did not yield usable files under current LAB_REPO; "
            "candidate ranking rebuilt from current repo evidence."
        )
    else:
        status["source"] = "no_current_lab_repo_candidates"
        status["rag_stale_or_unusable_count"] = stale_or_unusable
    return candidates[:16], status


def _core_discovery_read_paths(
    candidates: list[dict[str, Any]] | None,
    *,
    read_ok: set[str],
    target_scope: str,
    limit: int,
) -> list[str]:
    out: list[str] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        p = _repo_rel_token(item.get("path") or "")
        if not p or p in read_ok or p in out:
            continue
        if target_scope and not _path_under_scope(p, target_scope):
            continue
        if not _path_exists_repo_relative(p) or not _repo_readable_evidence_file(p):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


_SCOPE_CONFLICT_RATIONALE_TERMS = (
    "core", "runtime", "entrypoint", "entry point", "planner", "validator",
    "controller", "broker", "dispatch", "orchestrat", "loop", "contract",
    "tool", "schema", "evidence", "repo_read", "contenuto", "letto",
    "nucleo", "flusso", "contratto", "strumento",
)


def _target_scope_conflict_resolved(path: str, args: dict[str, Any], contract: dict[str, Any]) -> bool:
    target = _repo_rel_token(path)
    verified_rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
    verified_paths = {
        _repo_rel_token(row.get("path") or "")
        for row in verified_rows
        if isinstance(row, dict) and row.get("path")
    }
    if target not in verified_paths:
        return False
    if not _code_product_action_has_complete_payload({"tool": "repo_propose_code_edit", "arguments": args}):
        return False
    rationale = str(args.get("rationale") or "").strip()
    low = _normalize_scope_claim_text(rationale)
    if len(re.findall(r"\w+", low)) < 8:
        return False
    if not any(term in low for term in _SCOPE_CONFLICT_RATIONALE_TERMS):
        return False
    file_memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    anchors: set[str] = set()
    for item in file_memory:
        if not isinstance(item, dict) or _repo_rel_token(item.get("path") or "") != target:
            continue
        chunks: list[str] = []
        for key in ("headings", "key_lines", "mentioned_paths"):
            value = item.get(key)
            if isinstance(value, list):
                chunks.extend(str(part) for part in value)
        chunks.append(str(item.get("content_excerpt") or ""))
        for chunk in chunks:
            for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", _normalize_scope_claim_text(chunk)):
                if word in {
                    "from", "import", "return", "self", "true", "false", "none",
                    "path", "file", "line", "with", "that", "this", "sono",
                    "solo", "core",
                }:
                    continue
                anchors.add(word)
        break
    if anchors:
        return any(anchor in low for anchor in sorted(anchors)[:120])
    return True


def _candidate_actions_from_evidence(
    goal: str,
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    final_allowed: bool,
    failed_list_paths: list[str] | None = None,
    core_discovery_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    already = set(read_ok)
    failed_lists = set(_repo_rel_token(p) for p in (failed_list_paths or []))
    repo_goal = _repo_analysis_goal(goal)
    doc_reads = [p for p in read_ok if _repo_doc_or_config(p)]

    def add(action: dict[str, Any]) -> None:
        key = json.dumps(action, sort_keys=True, default=str)
        for existing in candidates:
            if json.dumps(existing, sort_keys=True, default=str) == key:
                return
        candidates.append(action)

    listed = []
    for row in list_rows:
        for p in row.get("paths_preview") or []:
            if p not in listed:
                listed.append(p)

    meaningful_rows = [
        row for row in list_rows
        if row.get("path") not in (None, "", ".")
        and not _low_signal_top_dir(str(row.get("path")))
    ]

    def add_core_list_candidates(limit: int = 5) -> None:
        ranked_core = sorted(
            _rank_core_candidates(file_memory, list_rows),
            key=lambda item: (
                -int(item.get("score") or 0),
                str(item.get("path") or "").lower(),
            ),
        )
        for core in ranked_core[:limit]:
            p = core.get("path")
            if (
                p
                and p not in failed_lists
                and _path_exists_repo_relative(p)
                and all((row.get("path") != p) for row in list_rows)
            ):
                add({
                    "action": "tool",
                    "tool": "repo_list_files",
                    "arguments": {"path": p, "limit": 120},
                    "reason": "Evidence-derived non-infra candidate directory: " + ", ".join(core.get("reasons") or []),
                })

    # Do not keep navigating when final evidence is already sufficient.
    if final_allowed:
        return candidates

    target_scope = _goal_target_scope(goal)
    discovery_selected = _core_discovery_read_paths(
        core_discovery_candidates,
        read_ok=already,
        target_scope=target_scope,
        limit=SCOPED_CONCRETE_READ_TARGET if target_scope else REPO_CONCRETE_READ_TARGET,
    )
    if discovery_selected:
        add({
            "action": "tool",
            "tool": "repo_read",
            "arguments": {"paths": discovery_selected, "max_chars": _multi_file_prompt_read_chars()},
            "reason": (
                "Read core_discovery_candidates from RAG/rerank or rebuilt LAB_REPO ranking; "
                "ranking is discovery-only and does not authorize a patch."
            ),
        })

    if target_scope and not _input_error_goal(goal):
        scoped_rows = [
            row for row in list_rows
            if _path_under_scope(str(row.get("path") or ""), target_scope)
            and str(row.get("path") or ".") not in ("", ".")
        ]
        if not scoped_rows:
            add({
                "action": "tool",
                "tool": "repo_list_files",
                "arguments": {"path": target_scope, "limit": 120},
                "reason": f"Inspect requested scope {target_scope}; root tree alone is not enough evidence.",
            })
        else:
            selected = _scope_read_candidates_from_evidence(
                list_rows,
                target_scope,
                read_ok=already,
            )[:SCOPED_CONCRETE_READ_TARGET]
            if selected:
                add({
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"paths": selected, "max_chars": _multi_file_prompt_read_chars()},
                    "reason": (
                        f"Read up to {SCOPED_CONCRETE_READ_TARGET} dynamically discovered "
                        f"readable files inside requested scope {target_scope} before finalizing."
                    ),
                })
        if candidates:
            return candidates[:16]

    # If a meaningful non-root area has already been listed, read from that area
    # before falling back to more root documentation.  Otherwise the planner can
    # spend many turns reading low-signal root docs and still final with only a
    # directory-name summary.
    if repo_goal and meaningful_rows:
        selected = _meaningful_read_candidates_from_evidence(
            list_rows,
            read_ok=already,
        )[:REPO_CONCRETE_READ_TARGET]
        if selected:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"paths": selected, "max_chars": _multi_file_prompt_read_chars()},
                "reason": (
                    f"Read up to {REPO_CONCRETE_READ_TARGET} dynamically discovered "
                    "readable files from already listed meaningful non-root areas before finalizing."
                ),
            })
            for p in selected[:REPO_CONCRETE_READ_TARGET]:
                add({
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": p, "max_chars": _single_file_prompt_read_chars()},
                    "reason": "Read concrete readable file from meaningful non-root area before finalizing.",
                })

    # Once enough root docs exist, prefer opening a real core directory instead
    # of continuing a root-doc crawl.  This remains a candidate list for the
    # planner, not a controller-executed script.
    if repo_goal and len(doc_reads) >= 3 and not meaningful_rows:
        add_core_list_candidates(limit=5)

    docs = [p for p in listed if _repo_doc_or_config(p) and p not in already]
    # Generic repo analysis needs representative docs, not every support/template
    # document.  After a small baseline, spend budget on core directories/files.
    if not (repo_goal and len(doc_reads) >= 6):
        if docs:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"paths": docs[:SCOPED_CONCRETE_READ_TARGET], "max_chars": _multi_file_prompt_read_chars()},
                "reason": "Read repository documentation/config already discovered in evidence before finalizing.",
            })

        for p in docs[:SCOPED_CONCRETE_READ_TARGET]:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": p, "max_chars": _single_file_prompt_read_chars()},
                "reason": "Unread repository documentation/config candidate from prior evidence.",
            })

    for p in listed:
        if _repo_code_file(p) and p not in already:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": p, "max_chars": _single_file_prompt_read_chars()},
                "reason": "Unread readable file discovered from evidence.",
            })
            if len(candidates) >= 12:
                break

    add_core_list_candidates(limit=5)

    return candidates[:16]



def _final_answer_too_shallow(final_answer: str, contract: dict[str, Any]) -> bool:
    text = str(final_answer or "")
    low = text.lower()
    if not text.strip():
        return True
    memory = contract.get("file_memory") if isinstance(contract, dict) else []
    notebook = contract.get("operational_notes") if isinstance(contract, dict) else {}
    if not isinstance(memory, list) or not memory:
        return len(text.strip()) < 500

    required_words = ("workflow", "entrypoint", "core", "proble", "limit")
    if any(w not in low for w in required_words):
        return True

    evidence_paths: list[str] = []
    for item in memory:
        if not isinstance(item, dict):
            continue
        _append_unique(evidence_paths, item.get("path"))
        for p in item.get("mentioned_paths") or []:
            _append_unique(evidence_paths, p)
    concrete_hits = sum(1 for p in evidence_paths if p and p in text)
    read_hit = any((item.get("path") in text) for item in memory if isinstance(item, dict))
    generic_loop = (
        "core directories are" in low
        and low.count("strong candidate") >= 2
        and concrete_hits < 4
    )
    return generic_loop or concrete_hits < 4 or not read_hit or len(text.strip()) < 1000


def _build_operational_notebook(goal: str, contract: dict[str, Any]) -> dict[str, Any]:
    memory = contract.get("file_memory") if isinstance(contract, dict) else []
    list_rows = contract.get("repo_list_files_evidence") if isinstance(contract, dict) else []
    core = contract.get("ranked_core_candidate_dirs") or []
    final_allowed = bool((contract.get("finalization_contract") or {}).get("final_allowed")) if isinstance(contract, dict) else False
    return {
        "schema": "agentic_loop_operational_notes.v1",
        "goal": goal,
        "final_allowed": final_allowed,
        "next_instruction": (
            "Quality gate is satisfied. Stop navigation/listing and produce final from read_notes, "
            "mentioned_paths, core_candidates, workflow/problems evidence, and limits."
            if final_allowed else
            "Continue only with one evidence-bound unread doc/code candidate. Do not repeat prior tool calls."
        ),
        "read_notes": [
            {
                "path": item.get("path"),
                "headings": (item.get("headings") or [])[:8],
                "key_lines": (item.get("key_lines") or [])[:10],
                "mentioned_paths": (item.get("mentioned_paths") or [])[:14],
                "excerpt": str(item.get("content_excerpt") or "")[:700],
            }
            for item in memory[:18] if isinstance(item, dict)
        ],
        "list_notes": list_rows[-8:] if isinstance(list_rows, list) else [],
        "core_candidates": core[:8] if isinstance(core, list) else [],
        "candidate_next_actions": contract.get("candidate_next_actions") or [],
        "recent_rejections": (contract.get("validation_rejections_tail") or [])[-8:] if isinstance(contract.get("validation_rejections_tail"), list) else [],
        "known_problem": (
            "Do not reduce this job to path counters or directory names. Use read_notes as the working scratchpad "
            "and cite concrete evidence from them."
        ),
    }


def _initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "schema": "agentic_loop_initial_orientation_surface.v1",
        "controller_preseed_read_only": True,
        "planner_decides_after_preseed": True,
        "root_tree": {},
        "docs_read": [],
        "areas_listed": [],
        "files_read": [],
        "skipped_candidates": list(skipped or []),
        "preseed_steps": [],
    }

    docs_read: list[str] = []
    files_read: list[str] = []
    areas_listed: list[str] = []

    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
        if not result.get("controller_preseed") and decision.get("action") != "controller_preseed":
            continue
        tool = str(result.get("tool") or decision.get("tool") or "")
        reason = str(result.get("preseed_reason") or decision.get("reason") or "")
        step_info = {
            "step": row.get("step"),
            "preseed_index": result.get("preseed_index") or row.get("preseed_index"),
            "tool": tool,
            "ok": result.get("ok"),
            "reason": reason,
            "artifact": result.get("artifact"),
        }
        surface["preseed_steps"].append({k: v for k, v in step_info.items() if v not in (None, "", [], {})})

        if tool == "repo_tree" and str(result.get("path") or ".") in {"", "."}:
            surface["root_tree"] = {
                "ok": result.get("ok"),
                "path": result.get("path") or ".",
                "count": result.get("entries_total") or result.get("count"),
                "truncated": result.get("truncated"),
                "artifact": result.get("artifact"),
            }
        elif tool == "repo_list_files":
            path = _repo_rel_token(result.get("path") or "")
            if path and path not in areas_listed:
                areas_listed.append(path)
        elif tool == "repo_read":
            for item in result.get("items") or []:
                if not isinstance(item, dict) or not item.get("ok") or not item.get("path"):
                    continue
                path = _repo_rel_token(item.get("path"))
                if _repo_doc_or_config(path) and path not in docs_read:
                    docs_read.append(path)
                if path not in files_read:
                    files_read.append(path)

    surface["docs_read"] = docs_read[:80]
    surface["areas_listed"] = areas_listed[:40]
    surface["files_read"] = files_read[:120]
    surface["doc_read_count"] = len(docs_read)
    surface["area_list_count"] = len(areas_listed)
    surface["file_read_count"] = len(files_read)
    surface["useful_area_list_count"] = len([
        path for path in areas_listed
        if path not in {"", "."} and not _low_signal_top_dir(path)
    ])
    surface["concrete_useful_file_read_count"] = len([
        path for path in files_read
        if any(_path_under_scope(path, area) and not _low_signal_top_dir(area) for area in areas_listed)
    ])
    return surface


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_classification = semantic_goal_classification(goal)
    latest_list = latest_file_list_result(history)
    known_paths = _paths_from_result(latest_list) if latest_list else []
    requested_limit = requested_file_limit_from_goal(goal, 0)
    target_file = _goal_target_file(goal)
    target_scope = "" if target_file else (_agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal))
    target_kind = _goal_target_kind(goal)
    read_ok = successful_repo_read_paths(history)
    verified_read_rows = _verified_repo_read_content_rows(history)
    verified_read_paths = [str(row.get("path")) for row in verified_read_rows if row.get("path")]
    verified_read_path_set = set(verified_read_paths)
    missing_full_content_reads = [
        p for p in read_ok
        if p not in verified_read_path_set and _repo_readable_evidence_file(p)
    ]
    read_failed = failed_repo_read_paths(history)
    list_failed = failed_repo_list_files_paths(history)
    list_rows = _repo_list_evidence(history)
    file_memory = _file_memory_from_history(history)
    doc_reads = [p for p in verified_read_paths if _repo_doc_or_config(p)]
    code_reads = [p for p in verified_read_paths if _repo_code_file(p)]
    root_surface_done = any(
        row.get("path") in ("", ".") for row in list_rows
    ) or any(
        isinstance(item, dict)
        and (item.get("tool_result") or {}).get("tool") == "repo_tree"
        and (item.get("tool_result") or {}).get("ok")
        for item in history if isinstance(item, dict)
    )
    meaningful_lists = [
        row.get("path") for row in list_rows
        if row.get("path") not in (None, "", ".") and not _low_signal_top_dir(str(row.get("path")))
    ]
    meaningful_content_reads = [
        p for p in verified_read_paths
        if any(_path_under_scope(p, str(area)) for area in meaningful_lists)
        and _repo_readable_evidence_file(p)
    ]
    repo_available_read_candidates = _meaningful_read_candidates_from_evidence(list_rows)
    repo_required_read_count = _repo_required_read_count(repo_available_read_candidates)
    repo_goal = _repo_analysis_goal(goal)
    repo_goal_class = str(semantic_classification.get("class") or "")
    analysis_only_repo_goal = (
        repo_goal
        and repo_goal_class == "analysis_only"
        and not bool(semantic_classification.get("must_produce_code_product"))
        and not goal_requests_apply(goal)
    )
    orientative_repo_final_goal = (
        repo_goal
        and repo_goal_class in {"analysis_only", "action_plan_only"}
        and not bool(semantic_classification.get("must_produce_code_product"))
        and not goal_requests_apply(goal)
    )
    repo_final_required_read_count = (
        min(repo_required_read_count, 10)
        if orientative_repo_final_goal
        else repo_required_read_count
    )
    scoped_inspection = bool(target_scope)
    file_read_done = bool(target_file and target_file in verified_read_path_set)
    scope_listed = bool(target_scope and any(_path_under_scope(str(row.get("path") or ""), target_scope) and str(row.get("path") or ".") not in ("", ".") for row in list_rows))
    scope_content_reads = [
        p for p in verified_read_paths
        if target_scope
        and _path_under_scope(p, target_scope)
        and _repo_readable_evidence_file(p)
    ]
    scope_available_read_candidates = _scope_read_candidates_from_evidence(list_rows, target_scope) if target_scope else []
    scope_required_read_count = _scoped_required_read_count(scope_available_read_candidates) if target_scope else 0
    user_scope_claims = _user_scope_claims(goal, target_scope)
    core_discovery_candidates, core_discovery_status = _core_discovery_candidates_from_intrinsic(
        intrinsic_context=intrinsic_context,
        list_rows=list_rows,
        read_ok=read_ok,
        target_scope=target_scope,
        user_scope_claims=user_scope_claims,
    )
    all_listed_paths = _paths_from_list_rows(list_rows)
    validator_admissible_read_paths: list[str] = []
    for path in (
        known_paths
        + all_listed_paths
        + repo_available_read_candidates
        + scope_available_read_candidates
        + [
            str(item.get("path") or "")
            for item in core_discovery_candidates
            if isinstance(item, dict)
        ]
        + read_ok
    ):
        p = _repo_rel_token(path)
        if p and p not in validator_admissible_read_paths:
            validator_admissible_read_paths.append(p)
    final_allowed = False
    final_reason = "No generic final fallback. Final requires explicit evidence for the actual goal."
    if _input_error_goal(goal):
        final_allowed = False
        final_reason = "Bridge/input error: missing natural-language user request. Do not invent a repository-analysis goal."
    elif target_kind == "file":
        final_allowed = file_read_done
        final_reason = (
            f"File evidence exists for {target_file}: direct repo_read succeeded."
            if final_allowed else
            f"Need direct repo_read evidence for requested file {target_file}."
        )
    elif scoped_inspection:
        final_allowed = bool(scope_listed and len(scope_content_reads) >= scope_required_read_count)
        final_reason = (
            f"Scoped evidence exists for {target_scope}: in-scope tree/list and "
            f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads."
            if final_allowed else
            f"Need scoped evidence for {target_scope}: repo_tree/list under scope and "
            f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads "
            f"(up to {SCOPED_CONCRETE_READ_TARGET}, bounded by discovered candidates)."
        )
    elif repo_goal:
        strict_repo_evidence_sufficient = bool(
            root_surface_done
            and len(doc_reads) >= 3
            and len(meaningful_lists) >= 1
            and len(meaningful_content_reads) >= repo_required_read_count
        )
        analysis_repo_evidence_sufficient = bool(
            orientative_repo_final_goal
            and root_surface_done
            and len(doc_reads) >= 3
            and len(meaningful_lists) >= 1
            and len(meaningful_content_reads) >= 1
            and len(verified_read_rows) >= repo_final_required_read_count
        )
        final_allowed = bool(strict_repo_evidence_sufficient or analysis_repo_evidence_sufficient)
        final_reason = (
            (
                "Analysis/action-plan repository evidence exists: root surface, multiple docs/config reads, "
                f"one meaningful non-infra/code area, {len(meaningful_content_reads)} verified reads "
                f"inside meaningful areas, and {len(verified_read_rows)}/{repo_final_required_read_count} "
                "total verified content reads. The 20-read target remains orientative, not a hard final gate."
            )
            if analysis_repo_evidence_sufficient and not strict_repo_evidence_sufficient else
            (
                "Codex-quality repository evidence exists: root surface, multiple docs/config reads, "
                f"one meaningful non-infra/code area, and {len(meaningful_content_reads)}/"
                f"{repo_required_read_count} verified concrete readable reads inside meaningful areas."
            )
            if final_allowed else
            (
                "Need root surface + at least 3 markdown/config reads + one meaningful non-infra/code area "
                f"+ {len(meaningful_content_reads)}/{repo_final_required_read_count} verified concrete readable reads "
                "for analysis/action-plan finalization "
                f"(target {REPO_CONCRETE_READ_TARGET} remains orientative and bounded by discovered candidates)."
            )
        )
    else:
        # Non-repository goals may still finish only after a planner final with
        # evidence. Do not use this branch to auto-legitimize a one-step repo_tree.
        final_allowed = bool(read_ok or meaningful_lists)
        final_reason = (
            "Non-repository goal has some executed evidence." if final_allowed
            else "Need at least one relevant tool result; no generic final fallback."
        )
    if goal_requests_apply(goal) and not history_has_tool(history, "repo_apply_patch"):
        final_allowed = False
        final_reason = "Apply/edit/write goal requires repo_apply_patch after verified repo_read old_text evidence."

    core_candidates = _rank_core_candidates(file_memory, list_rows)
    candidates = _candidate_actions_from_evidence(
        goal,
        file_memory,
        list_rows,
        read_ok,
        final_allowed,
        list_failed,
        core_discovery_candidates,
    )
    code_product_required = bool(semantic_classification.get("must_produce_code_product")) and not goal_requests_apply(goal)
    code_product_proposals = successful_code_edit_proposals(history)
    latest_code_product = code_product_proposals[-1] if code_product_proposals else {}
    latest_code_product_violations = (
        _code_product_payload_violations(latest_code_product, verified_read_path_set)
        if latest_code_product else ["missing_code_product_candidate"]
    )
    code_product_blocks_final = code_product_required and bool(latest_code_product_violations)
    code_product_candidate_target = ""
    code_product_candidate_line_count = 0
    if code_product_blocks_final:
        candidate_paths = [target_file]
        ranked_code_reads = sorted(
            [
                row for row in verified_read_rows
                if _repo_code_file(str(row.get("path") or ""))
                and (
                    target_file
                    or (
                        not str(row.get("path") or "").endswith("__init__.py")
                        and not str(row.get("path") or "").endswith("__main__.py")
                        and int(row.get("line_count") or 0) >= 20
                    )
                )
            ],
            key=lambda row: (
                str(row.get("path") or "").endswith("__init__.py"),
                str(row.get("path") or "").endswith("__main__.py"),
                -int(row.get("line_count") or 0),
                str(row.get("path") or ""),
            ),
        )
        candidate_paths.extend(str(row.get("path") or "") for row in ranked_code_reads)
        if target_file:
            candidate_paths.extend([*code_reads, *scope_content_reads, *verified_read_paths])
        for candidate_path in candidate_paths:
            p = _repo_rel_token(candidate_path)
            if p and p != "." and p in verified_read_path_set:
                code_product_candidate_target = p
                for row in verified_read_rows:
                    if _repo_rel_token(row.get("path") or "") == p:
                        try:
                            code_product_candidate_line_count = int(row.get("line_count") or 0)
                        except Exception:
                            code_product_candidate_line_count = 0
                        break
                break
    code_product_build_state = _latest_code_product_build_state(
        history,
        code_product_candidate_target or target_file,
    )
    if (
        code_product_blocks_final
        and not code_product_candidate_target
        and _repo_rel_token(code_product_build_state.get("target_file") or "") in verified_read_path_set
    ):
        code_product_candidate_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
    if code_product_blocks_final:
        final_allowed = False
        final_reason = (
            "Code-product goal requires repo_propose_code_edit ok=true before final. "
            "Latest code-product violations: "
            + ", ".join(str(v) for v in latest_code_product_violations)
        )
        if code_product_candidate_target:
            code_candidate = _code_product_candidate_action(
                target_file=code_product_candidate_target,
                latest_violations=latest_code_product_violations,
                goal=goal,
            )
            if code_candidate and not any(
                item.get("tool") == "repo_propose_code_edit"
                and (item.get("arguments") or {}).get("target_file") == code_product_candidate_target
                for item in candidates
                if isinstance(item, dict)
            ):
                candidates.insert(0, code_candidate)

    validation_rejections: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") == "controller_guard" or result.get("violations"):
            validation_rejections.append({
                "step": item.get("step"),
                "guard_type": result.get("guard_type"),
                "summary": result.get("summary"),
                "classification": result.get("classification"),
                "semantic_goal_classification": result.get("semantic_goal_classification"),
                "next_instruction": result.get("next_instruction"),
                "action_plan_candidate": result.get("action_plan_candidate"),
                "raw_planner_text_preview": result.get("raw_planner_text_preview"),
                "violations": result.get("violations") or [],
                "rejected_decision": result.get("rejected_decision") or {},
                "invalid_decision_signature": (
                    result.get("invalid_decision_signature")
                    if isinstance(result.get("invalid_decision_signature"), dict)
                    else _canonical_invalid_code_product_decision_signature(
                        result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
                        result.get("violations") if isinstance(result.get("violations"), list) else [],
                    )
                ),
            })
        else:
            failed_code_edit_row = _failed_code_edit_proposal_validation_row(item)
            if failed_code_edit_row:
                failed_code_edit_row["invalid_decision_signature"] = (
                    failed_code_edit_row.get("invalid_decision_signature")
                    if isinstance(failed_code_edit_row.get("invalid_decision_signature"), dict)
                    else _canonical_invalid_code_product_decision_signature(
                        failed_code_edit_row.get("rejected_decision")
                        if isinstance(failed_code_edit_row.get("rejected_decision"), dict) else {},
                        failed_code_edit_row.get("violations")
                        if isinstance(failed_code_edit_row.get("violations"), list) else [],
                    )
                )
                validation_rejections.append(failed_code_edit_row)
    action_plan_candidate = ""
    for row in reversed(validation_rejections):
        candidate = str(row.get("action_plan_candidate") or "").strip()
        if candidate:
            action_plan_candidate = candidate
            break
    disallowed_invalid_decision_signatures = _disallowed_invalid_code_product_signatures(
        validation_rejections
    )

    contract = {
        "contract_type": "planner_decides_controller_validates",
        "planner_must_decide_next_action": True,
        "controller_may_reject_but_must_not_replace_planner_reasoning": True,
        "controller_must_not_auto_read_or_auto_final": True,
        "semantic_goal_classification": semantic_classification,
        "goal_requests_python_file_review": goal_requests_python_file_review(goal),
        "goal_requests_code_product": goal_requests_code_product(goal),
        "goal_requires_code_product_report": code_product_required,
        "goal_requests_apply": goal_requests_apply(goal),
        "action_plan_candidate": action_plan_candidate or None,
        "requested_file_limit": requested_limit or None,
        "target_kind": target_kind,
        "resolved_goal_file": target_file or None,
        "resolved_goal_scope": target_scope or None,
        "known_paths_from_latest_repo_list_files": known_paths[:120],
        "known_paths_total_in_latest_digest": len(known_paths),
        "successful_repo_read_paths": read_ok[:160],
        "successful_repo_read_count": len(read_ok),
        "verified_content_read_count": len(verified_read_rows),
        "verified_content_reads": verified_read_rows[:160],
        "missing_full_content_reads": missing_full_content_reads[:160],
        "user_scope_claims": user_scope_claims[:12],
        "core_discovery_status": core_discovery_status,
        "core_discovery_candidates": core_discovery_candidates[:16],
        "scoped_concrete_read_target": SCOPED_CONCRETE_READ_TARGET if target_scope else None,
        "scoped_concrete_read_required": scope_required_read_count or None,
        "scoped_available_read_candidates": scope_available_read_candidates[:120],
        "scoped_concrete_read_count": len(scope_content_reads),
        "repo_concrete_read_target": REPO_CONCRETE_READ_TARGET if repo_goal else None,
        "repo_concrete_read_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
        "repo_concrete_read_required": repo_final_required_read_count if repo_goal else None,
        "repo_concrete_read_strict_required": repo_required_read_count if repo_goal else None,
        "repo_available_read_candidates": repo_available_read_candidates[:160] if repo_goal else [],
        "repo_concrete_read_count": len(meaningful_content_reads) if repo_goal else None,
        "repo_goal_final_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
        "failed_repo_read_paths": read_failed[:120],
        "failed_repo_list_files_paths": list_failed[:120],
        "repo_list_files_evidence": list_rows[-10:],
        "file_memory": file_memory[:32],
        "ranked_core_candidate_dirs": core_candidates,
        "candidate_next_actions": candidates,
        "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
        "planner_may_choose_final": final_allowed,
        "read_admissible_paths": validator_admissible_read_paths[:400],
        "validator_admissible_repo_read_paths": validator_admissible_read_paths[:400],
        "code_product_contract": {
            "required": code_product_required,
            "required_tool": "repo_propose_code_edit" if code_product_required else None,
            "successful_proposal_count": len(code_product_proposals),
            "latest_target_file": latest_code_product.get("target_file") if latest_code_product else None,
            "candidate_target_file": code_product_candidate_target or None,
            "candidate_target_line_count": code_product_candidate_line_count or None,
            "candidate_payload_must_be_generated_from_required_working_set": bool(
                code_product_candidate_target
                and not (_goal_exact_text_block(goal, "old_text") and _goal_exact_text_block(goal, "new_text"))
                and code_product_blocks_final
            ),
            "action_plan_candidate_available": bool(action_plan_candidate),
            "latest_edit_kind": latest_code_product.get("edit_kind") if latest_code_product else None,
            "latest_payload_complete": bool(latest_code_product and not latest_code_product_violations),
            "latest_violations": latest_code_product_violations if code_product_required else [],
            "build_state": {
                k: v for k, v in code_product_build_state.items()
                if k not in {"state", "ready_arguments"} and v not in (None, "", [], {})
            } if code_product_build_state else {},
            "build_state_status": code_product_build_state.get("status") if code_product_build_state else None,
            "build_state_payload_loaded": bool(code_product_build_state.get("payload_loaded")) if code_product_build_state else False,
            "build_state_complete_payload_ready": bool(code_product_build_state.get("complete_payload_ready")) if code_product_build_state else False,
            "inline_payload_required": True,
            "artifact_path_is_not_payload": True,
            "full_payload_fields": [
                "unified_diff",
                "structured_operations",
                "validation_commands",
                "target_file",
                "edit_kind",
            ],
            "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
        },
        "validation_rejections_tail": _compact_validation_rejections_tail(validation_rejections, limit=5),
        "project_powershell_access": {
            "tool": "terminal_run_command_wait",
            "cwd": str(LAB_REPO),
            "privilege_boundary": "current 3572 Python process user; not UAC elevation",
            "dangerous_commands_require_user_consent": True,
            "use_for": "rg/select-string, dir/tree, git status/diff, python -m compileall, targeted diagnostics under the project folder",
        },
        "finalization_contract": {
            "final_allowed": final_allowed,
            "reason": final_reason,
            "planner_may_choose_final": final_allowed,
            "controller_must_not_auto_final": True,
            "final_is_not_required": True,
            "verified_content_read_count": len(verified_read_rows),
            "verified_content_reads": verified_read_rows[:160],
            "missing_full_content_reads": missing_full_content_reads[:160],
            "code_product_required": code_product_required,
            "code_product_required_tool": "repo_propose_code_edit" if code_product_required else None,
            "code_product_latest_violations": latest_code_product_violations if code_product_required else [],
            "minimum_evidence_for_this_goal_kind": (
                "For code diff/refactoring proposals: read the target with repo_read, then call repo_propose_code_edit with a complete unified_diff, structured_operations, or explicit no_op rationale."
                if code_product_required else
                "For explicit file inspection: direct repo_read of the requested file."
                if target_kind == "file" else
                f"For explicit directory inspection: list/tree the requested directory and read up to "
                f"{SCOPED_CONCRETE_READ_TARGET} verified concrete readable files discovered under it; "
                "if fewer are discovered, read all discovered candidates."
                if target_kind == "directory" else
                "For generic repository structure/content analysis: root surface, at least 3 markdown/config reads, "
                "one evidence-derived meaningful non-infra/code area, and enough verified content reads for the "
                f"current goal. For analysis/action-plan goals the {REPO_CONCRETE_READ_TARGET}-read target is orientative; "
                f"{repo_final_required_read_count} verified reads can satisfy finalization when concrete evidence is present."
            ),
        },
        "agentic_codex_quality": {
            "enabled": True,
            "repo_goal": repo_goal,
            "deep_repo_goal": repo_goal,
            "target_kind": target_kind,
            "target_file": target_file or None,
            "target_scope": target_scope or None,
            "root_surface_done": root_surface_done,
            "doc_read_count": len(doc_reads),
            "doc_reads": doc_reads[:80],
            "code_read_count": len(code_reads),
            "code_reads": code_reads[:80],
            "meaningful_non_root_list_count": len(meaningful_lists),
            "meaningful_non_root_lists": meaningful_lists[:20],
            "meaningful_content_read_count": len(meaningful_content_reads),
            "meaningful_content_reads": meaningful_content_reads[:40],
            "verified_content_read_count": len(verified_read_rows),
            "verified_content_reads": verified_read_rows[:80],
            "missing_full_content_reads": missing_full_content_reads[:80],
            "ranked_core_candidate_dirs": core_candidates,
            "core_discovery_candidates": core_discovery_candidates[:12],
            "top_core_seen": bool(core_candidates),
            "quality_gate": (
                "direct file read"
                if target_kind == "file" else
                f"in-scope list/tree + {scope_required_read_count} in-scope verified concrete readable reads"
                if target_kind == "directory" else
                f"root_surface + >=3 docs/config reads + one evidence-derived non-infra/code area "
                f"+ {repo_final_required_read_count} verified concrete readable reads"
            ),
            "hardcoded_core_path": False,
        },
        "initial_orientation_surface": _initial_orientation_surface_from_history(history),
    }
    contract = _agentic_v2_enrich_evidence_contract(contract, goal, history)
    contract["operational_notes"] = _build_operational_notebook(goal, contract)
    if code_product_blocks_final:
        payload_rejection_count = _code_product_payload_rejection_count(
            validation_rejections,
            code_product_candidate_target,
        )
        successful_read_path_set = {
            _repo_rel_token(path)
            for path in [*read_ok, *verified_read_paths, *list(verified_read_path_set)]
            if _repo_rel_token(path)
        }
        code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        code_contract["payload_rejection_count"] = payload_rejection_count
        code_contract["route_shift_after_payload_rejection"] = bool(payload_rejection_count and code_product_candidate_target)
        contract["code_product_contract"] = code_contract
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = final_reason
        contract["finalization_contract"] = final_contract
        contract["planner_may_choose_final"] = False
        build_state_ready_action = _code_product_build_state_propose_action(
            code_product_build_state,
            latest_code_product_violations,
        )
        complete_existing_code_action = next(
            (
                item for item in (contract.get("candidate_next_actions") or [])
                if isinstance(item, dict)
                and item.get("tool") == "repo_propose_code_edit"
                and _code_product_action_has_complete_payload(item)
            ),
            {},
        )
        if not build_state_ready_action and complete_existing_code_action:
            build_state_ready_action = complete_existing_code_action
        build_state_status = str(code_product_build_state.get("status") or "")
        build_state_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
        build_state_needs_read = bool(
            code_product_build_state
            and not build_state_ready_action
            and (
                code_product_build_state.get("complete_payload_ready")
                or code_product_build_state.get("has_more_after") is True
                or code_product_build_state.get("payload_loaded") is not True
            )
        )
        build_state_progress_handled = False
        if build_state_ready_action:
            build_state_progress_handled = True
            ready_progress = (
                "Internal code_product_build_state is ready_for_propose. "
                "Call repo_propose_code_edit with the complete payload from candidate_next_actions."
                if code_product_build_state else
                "A complete repo_propose_code_edit candidate is available. "
                "Call repo_propose_code_edit with that complete payload."
            )
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
            ]
            contract["candidate_next_actions"] = [build_state_ready_action] + existing_candidates[:15]
            contract["required_next_progress"] = ready_progress
        elif build_state_status == "blocked_incomplete":
            build_state_progress_handled = True
            code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
            code_contract["build_state_block_allows_typed_block"] = True
            code_contract["build_state_blocker"] = (
                code_product_build_state.get("blocker")
                or (code_product_build_state.get("state") or {}).get("blocker")
            )
            contract["code_product_contract"] = code_contract
            contract["candidate_next_actions"] = []
            contract["required_next_progress"] = (
                "Internal code_product_build_state is blocked_incomplete. "
                "Return action=block with final_answer starting with code_product_build_state_blocked_incomplete "
                "and cite the blocker; do not loop on repo_read or incomplete repo_propose_code_edit."
            )
        elif build_state_needs_read:
            build_state_progress_handled = True
            read_state_action = _code_product_build_state_read_action(
                code_product_build_state,
                build_state_target or code_product_candidate_target,
            )
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
            ]
            contract["candidate_next_actions"] = [read_state_action] + existing_candidates[:15]
            contract["required_next_progress"] = (
                "Read the internal code_product_build_state SQLite window before deciding whether "
                "repo_propose_code_edit has a complete payload."
            )
        elif payload_rejection_count and code_product_candidate_target:
            build_state_progress_handled = True
            route_candidate = _code_product_source_window_candidate(
                code_product_candidate_target,
                line_count=code_product_candidate_line_count,
                history=history,
            )
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
                and not (
                    isinstance(item, dict)
                    and item.get("tool") == "planner_scratchpad_write"
                    and (item.get("arguments") or {}).get("kind") == CODE_PRODUCT_BUILD_STATE_KIND
                    and not str((item.get("arguments") or {}).get("text") or (item.get("arguments") or {}).get("content") or "").strip()
                )
            ]
            if route_candidate:
                contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Route shift required after invalid repo_propose_code_edit payload. Change decision now: "
                    "read a different concrete source window from the target via candidate_next_actions[0], then call "
                    "repo_propose_code_edit only with complete unified_diff or complete old_text/new_text. "
                    "Do not repeat the rejected incomplete repo_propose_code_edit and do not write an empty "
                    "code_product_build_state."
                )
            else:
                contract["candidate_next_actions"] = existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Route shift required after invalid repo_propose_code_edit payload, but no new source "
                    "window is available for this target. Change decision now: use verified_content_reads / "
                    "required_working_set to call repo_propose_code_edit with a complete unified_diff or "
                    "complete old_text/new_text, write code_product_build_state with real progress only, "
                    "or return a typed block if the diff cannot be built. Do not repeat repo_read."
                )
        elif build_state_status == "collecting_source" and code_product_build_state.get("payload_loaded") is True:
            build_state_progress_handled = True
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
                and not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and (build_state_target or code_product_candidate_target) in {
                        _repo_rel_token(path)
                        for path in _agentic_v2_decision_paths(
                            str(item.get("tool") or ""),
                            item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                        )
                    }
                )
            ]
            progress_write_action = _code_product_build_state_write_action(
                build_state_target or code_product_candidate_target,
                history,
            )
            contract["candidate_next_actions"] = (
                ([progress_write_action] if progress_write_action else []) + existing_candidates[:15]
            )
            contract["required_next_progress"] = (
                "Internal code_product_build_state is collecting_source but not ready and has no remaining "
                "state window to read. Advance with one real step only: call repo_propose_code_edit with a "
                "complete unified_diff or complete old_text/new_text, write code_product_build_state with "
                "new real progress, or return a typed block if the diff cannot be built. Empty "
                "collecting_source writes are rejected."
            )
        elif code_product_candidate_target and code_product_candidate_target in successful_read_path_set:
            build_state_progress_handled = True
            write_state_action = _code_product_build_state_write_action(code_product_candidate_target, history)
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
                and not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and code_product_candidate_target in {
                        _repo_rel_token(path)
                        for path in _agentic_v2_decision_paths(
                            str(item.get("tool") or ""),
                            item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                        )
                    }
                )
            ]
            contract["candidate_next_actions"] = (
                ([write_state_action] if write_state_action else []) + existing_candidates[:15]
            )
            contract["required_next_progress"] = (
                "Target is already read and no ready code product exists. Persist an internal "
                "code_product_build_state with real progress only; do not repeat repo_read "
                "for that target and do not call repo_propose_code_edit until payload is complete. "
                "Empty collecting_source writes are rejected."
            )
        if not build_state_progress_handled and payload_rejection_count and code_product_candidate_target:
            route_candidate = _code_product_source_window_candidate(
                code_product_candidate_target,
                line_count=code_product_candidate_line_count,
                history=history,
            )
            route_target_has_truncated_read = any(
                _repo_rel_token(row.get("path") or "") == code_product_candidate_target
                and row.get("truncated") is True
                for row in verified_read_rows
                if isinstance(row, dict)
            )
            existing_candidates = [
                item for item in (contract.get("candidate_next_actions") or [])
                if not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not _code_product_action_has_complete_payload(item)
                )
                and not (
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and code_product_candidate_target in {
                        _repo_rel_token(path)
                        for path in _agentic_v2_decision_paths(
                            str(item.get("tool") or ""),
                            item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                        )
                    }
                )
            ]
            if code_product_candidate_target in successful_read_path_set and not route_target_has_truncated_read:
                code_contract["route_shift_target_already_read"] = True
                code_contract["route_shift_blocker"] = (
                    "code_product_route_shift_target_already_read_but_no_valid_candidate"
                )
                code_contract["forbidden_repeated_repo_read_target"] = code_product_candidate_target
                contract["code_product_contract"] = code_contract
                contract["candidate_next_actions"] = existing_candidates[:15]
                contract["forbidden_next_actions"] = [
                    {
                        "action": "tool",
                        "tool": "repo_read",
                        "arguments": route_candidate.get("arguments"),
                        "reason": (
                            "The code-product route-shift target is already in "
                            "successful_repo_read_paths; repeating this read loops."
                        ),
                    }
                ]
                contract["required_next_progress"] = (
                    "Route shift required after invalid repo_propose_code_edit payload, but "
                    f"{code_product_candidate_target} is already read. Do not call repo_read for "
                    "that target again. Use required_working_set.repo_reads / verified_content_reads "
                    "for that target and call repo_propose_code_edit only with a complete inline "
                    "unified_diff or complete structured_operations. If a complete code product "
                    "cannot be produced from the available source evidence, return action=block with "
                    "final_answer starting with "
                    "code_product_route_shift_target_already_read_but_no_valid_candidate."
                )
            elif route_candidate:
                contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Route shift required after invalid repo_propose_code_edit payload. "
                    f"Do not repeat the same repo_propose_code_edit arguments for {code_product_candidate_target}. "
                    "Next action must inspect a concrete source window of that target with repo_read, then produce "
                    "repo_propose_code_edit only when the unified_diff or structured_operations payload is complete inline."
                )
            else:
                contract["candidate_next_actions"] = existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Route shift required after invalid repo_propose_code_edit payload, but no unread source "
                    "window remains for the target. Do not call repo_read for that target again. Use the "
                    "existing source evidence to produce a complete inline repo_propose_code_edit payload, "
                    "write code_product_build_state with real progress, or return a typed block."
                )
        elif not build_state_progress_handled and code_product_candidate_target:
            contract["required_next_progress"] = (
                "Use required_working_set.repo_reads for the previously read target "
                f"{code_product_candidate_target}; then call repo_propose_code_edit only with a complete "
                "unified_diff or complete structured_operations inline. "
                "Do not final with prose-only output."
            )
        elif not build_state_progress_handled:
            contract["required_next_progress"] = (
                "read the target with repo_read, then call repo_propose_code_edit with a complete inline code product. "
                "Do not final with prose-only output."
            )
    elif final_allowed:
        contract["required_next_progress"] = (
            "Quality gate is satisfied. Planner must produce action=final using operational_notes.read_notes, "
            "workflow/problems/core evidence, cited concrete paths, and explicit limits. Do not call repo_tree/list/read again "
            "unless a brand-new evidence gap is named."
        )
    elif candidates:
        contract["required_next_progress"] = (
            "candidate_next_actions contains admissible examples, not a controller script. "
            "Planner must choose the next evidence-bound tool or final; do not repeat rejected decisions. "
            "Controller validates only; no hidden fallback final."
        )
    else:
        contract["required_next_progress"] = (
            "Use prior evidence. If enough, final with concrete cited paths; otherwise choose a new evidence-bound tool."
        )
    contract = _apply_turn_surface_policy(contract)
    return contract

def _path_exists_repo_relative(path: str) -> bool:
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists()
    except Exception:
        return False


def _path_under_scope(path: str, scope: str) -> bool:
    if not scope:
        return True
    p = _repo_rel_token(path)
    s = _repo_rel_token(scope).strip("/")
    if not s or s == ".":
        return True
    return p == s or p.startswith(s + "/")

# --- agentic-loop-v2 progress/scope helpers ---
def _agentic_v2_alias_repo_path(path: Any) -> str:
    # Normalize repo-relative paths and map the user's ai_carmine alias.
    # The repository directory visible in evidence is ia_carmine. Users and the
    # outer model often say ai_carmine. Do not silently execute a different tool
    # path; use this only for validation/evidence guidance so the planner is told
    # which real path exists.
    p = _repo_rel_token(path)
    try:
        if (p == "ai_carmine" or p.startswith("ai_carmine/")) and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine" + p[len("ai_carmine"):]
    except Exception:
        pass
    return p


def _agentic_v2_goal_scope(goal: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    scope = _repo_rel_token(contract.get("resolved_goal_scope") or "")
    if scope and scope != ".":
        return scope
    low = _semantic_goal_low(goal).replace("\\", "/")
    try:
        if "ai_carmine" in low and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine"
        if "ia_carmine" in low:
            return "ia_carmine"
    except Exception:
        if "ai_carmine" in low or "ia_carmine" in low:
            return "ia_carmine"
    return ""


def _agentic_v2_decision_paths(tool: str, args: dict[str, Any]) -> list[str]:
    args = args if isinstance(args, dict) else {}
    paths: list[str] = []

    def add(value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for key in ("path", "file", "filename", "target_file", "target_path"):
                if value.get(key):
                    add(value.get(key))
            return
        p = _agentic_v2_alias_repo_path(value)
        if p and p not in paths:
            paths.append(p)

    if tool in {"repo_list_files", "repo_tree", "repo_search"}:
        add(args.get("path") or ".")
    elif tool == "repo_read":
        add(args.get("path"))
        add(args.get("paths"))
        add(args.get("file"))
        add(args.get("files"))
        add(args.get("item"))
        add(args.get("items"))
    elif tool in {"repo_write_file", "repo_apply_patch", "repo_propose_code_edit"}:
        add(args.get("path"))
        add(args.get("paths"))
        add(args.get("target_file"))
        add(args.get("target_path"))
    return paths


def _agentic_v2_read_has_window(args: dict[str, Any]) -> bool:
    args = args if isinstance(args, dict) else {}
    return any(k in args for k in (
        "start", "start_line", "end", "end_line", "offset", "limit",
        "line", "line_start", "line_count", "before", "after",
        "max_chars", "window", "chunk", "range",
    ))


def _agentic_v2_repo_list_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        if result.get("tool") != "repo_list_files" or not result.get("ok"):
            continue
        paths: list[str] = []
        for key in ("paths", "paths_preview"):
            value = result.get(key)
            if isinstance(value, list):
                for raw in value:
                    if isinstance(raw, dict):
                        raw = raw.get("path")
                    p = _agentic_v2_alias_repo_path(raw)
                    if p and p not in paths:
                        paths.append(p)
        rows.append({
            "step": item.get("step"),
            "path": _agentic_v2_alias_repo_path(result.get("path") or "."),
            "total_matches": result.get("total_matches"),
            "limit": result.get("limit"),
            "truncated": result.get("truncated"),
            "paths": paths,
        })
    return rows


def _agentic_v2_successful_read_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    try:
        for p in _extract_successful_repo_read_paths(history):
            n = _agentic_v2_alias_repo_path(p)
            if n and n not in paths:
                paths.append(n)
    except Exception:
        pass
    if paths:
        return paths
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        for value in (result.get("paths"), result.get("path")):
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                for raw in value:
                    if raw in (None, "", [], {}):
                        continue
                    n = _agentic_v2_alias_repo_path(raw)
                    if n and n not in paths:
                        paths.append(n)
            else:
                n = _agentic_v2_alias_repo_path(value)
                if n and n not in paths:
                    paths.append(n)
        for read_item in result.get("items") or []:
            if isinstance(read_item, dict) and read_item.get("ok") and read_item.get("path") not in (None, "", [], {}):
                n = _agentic_v2_alias_repo_path(read_item.get("path"))
                if n and n not in paths:
                    paths.append(n)
    return paths


def _agentic_v2_enrich_evidence_contract(contract: dict[str, Any], goal: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        contract = {}
    history = history if isinstance(history, list) else []
    scope = _agentic_v2_goal_scope(goal, contract)
    list_rows = _agentic_v2_repo_list_rows(history)
    successful_reads = _agentic_v2_successful_read_paths(history)

    known_all: list[str] = []
    for row in list_rows:
        for p in row.get("paths") or []:
            if p not in known_all:
                known_all.append(p)

    in_scope: list[str] = []
    if scope:
        for p in known_all:
            if _path_under_scope(p, scope) and p not in in_scope:
                in_scope.append(p)

    latest_in_scope = next((row for row in reversed(list_rows) if scope and _path_under_scope(row.get("path") or ".", scope)), None)
    latest_any = list_rows[-1] if list_rows else None
    already_read = set(successful_reads)
    unread_in_scope = _dynamic_read_candidate_paths(in_scope, read_ok=already_read, target_scope=scope)

    contract["resolved_goal_scope"] = scope or contract.get("resolved_goal_scope")
    contract["path_aliases"] = {"ai_carmine": "ia_carmine"} if scope == "ia_carmine" else contract.get("path_aliases", {})
    contract["repo_list_files_evidence"] = [
        {k: v for k, v in {
            "step": row.get("step"),
            "path": row.get("path"),
            "total_matches": row.get("total_matches"),
            "limit": row.get("limit"),
            "truncated": row.get("truncated"),
            "paths_preview": (row.get("paths") or [])[:20],
        }.items() if v not in (None, "", [], {})}
        for row in list_rows[-8:]
    ]
    if scope:
        scoped_latest_paths = list((latest_in_scope or {}).get("paths") or in_scope)
        if scoped_latest_paths:
            # Keep the legacy field useful for the existing validator/prompt:
            # prefer the latest in-scope list over a later accidental root list.
            contract["known_paths_from_latest_repo_list_files"] = scoped_latest_paths[:80]
            contract["known_paths_total_in_latest_digest"] = len(scoped_latest_paths)
    contract["known_in_scope_paths_from_repo_list_files"] = in_scope[:80]
    contract["known_in_scope_paths_total"] = len(in_scope)
    contract["latest_in_scope_repo_list_path"] = latest_in_scope.get("path") if latest_in_scope else None
    contract["latest_repo_list_path"] = latest_any.get("path") if latest_any else None
    contract["successful_repo_read_paths"] = successful_reads
    contract["forbidden_repeated_repo_read_paths"] = successful_reads[:40]
    contract["unread_in_scope_candidate_paths"] = unread_in_scope[:40]

    guidance: list[str] = []
    if scope:
        guidance.append(f"Stay under resolved_goal_scope={scope}; do not call repo_list_files with path='.' or omitted path.")
    if successful_reads:
        guidance.append("Do not repo_read already successful paths: " + ", ".join(successful_reads[:8]))
    if unread_in_scope:
        guidance.append("Next valid progress can be repo_read one unread in-scope candidate or repo_list_files a new subdirectory under scope: " + ", ".join(unread_in_scope[:8]))
    elif latest_in_scope:
        guidance.append("If current in-scope evidence is enough, choose final and cite the read/list evidence already in history.")
    guidance.append("Controller validates only; planner must decide the next tool or final from these evidence-bound candidates.")
    contract["required_next_progress"] = " ".join(guidance)
    return contract



def _argument_value_present(args: dict[str, Any], key: str) -> bool:
    value = (args if isinstance(args, dict) else {}).get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _argument_group_present(args: dict[str, Any], keys: list[str] | tuple[str, ...]) -> bool:
    return all(_argument_value_present(args, str(key)) for key in keys)


def _any_argument_group_present(args: dict[str, Any], groups: list[list[str]] | tuple[tuple[str, ...], ...]) -> bool:
    return any(_argument_group_present(args, [str(key) for key in group]) for group in groups)


def _planner_scratchpad_read_selector_present(args: dict[str, Any]) -> bool:
    args = args if isinstance(args, dict) else {}
    kind = str(args.get("kind") or "")
    if kind in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
        return _any_argument_group_present(
            args,
            [["document_id"], ["section"], ["tag"], ["query"], ["target_file"]],
        )
    return _any_argument_group_present(
        args,
        [["document_id"], ["section"], ["tag"], ["query"], ["kind"]],
    )


def _repo_read_selector_present(args: dict[str, Any]) -> bool:
    return _any_argument_group_present(
        args if isinstance(args, dict) else {},
        [["path"], ["paths"], ["item"], ["items"]],
    )


def _native_required_tool_decision_has_transport_provenance(decision: dict[str, Any]) -> bool:
    if decision.get("native_tool_call") is not True:
        return False
    return isinstance(decision.get("raw_native_tool_call"), dict)


def _native_required_repaired_tool_decision_disallowed(decision: dict[str, Any]) -> bool:
    action = str((decision if isinstance(decision, dict) else {}).get("action") or "").strip().lower()
    return bool(
        AGENTIC_PLANNER_NATIVE_TOOLS
        and action == "tool"
    )


def _copyable_example_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    low = re.sub(r"\s+", " ", text.lower()).strip()
    if "<insert" in low or "insert old text" in low or "insert new text" in low:
        return True
    if "example_only" in low or "do_not_copy" in low:
        return True
    if low in {
        "old",
        "new",
        "old phrase",
        "new phrase",
        "old text",
        "new text",
        "example old text",
        "example new text",
        "placeholder",
    }:
        return True
    return bool(re.fullmatch(r"<[^<>]{1,120}>", text))


def _verified_repo_read_contents_for_path(history: list[dict[str, Any]], target_file: str) -> list[str]:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return []
    out: list[str] = []
    seen_hashes: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = _repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = _repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = _text_hash(text)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            out.append(text)
    return out


def _old_text_verified_by_repo_read(history: list[dict[str, Any]], target_file: str, old_text: Any) -> bool:
    if not isinstance(old_text, str) or not old_text:
        return False
    return any(old_text in content for content in _verified_repo_read_contents_for_path(history, target_file))


def _apply_unverified_old_text_replan_contract(
    contract: dict[str, Any],
    *,
    target_file: str,
    violation: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    def admissible_replan_candidate(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        tool_name = str(item.get("tool") or "")
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        if tool_name == "planner_scratchpad_read":
            return True
        if tool_name == "repo_read":
            return target in {
                _repo_rel_token(path)
                for path in _agentic_v2_decision_paths(tool_name, arguments)
            }
        if tool_name == "planner_scratchpad_write" and arguments.get("kind") == CODE_PRODUCT_BUILD_STATE_KIND:
            text = str(arguments.get("text") or arguments.get("content") or "")
            state = _code_product_build_state_parse(text)
            return bool(
                state
                and (
                    _code_product_build_state_has_collecting_progress(state)
                    or _code_product_build_state_ready_payload(state)
                    or (
                        str(state.get("status") or "") == "blocked_incomplete"
                        and str(state.get("blocker") or "").strip()
                    )
                )
            )
        if item.get("action") == "block":
            return True
        return False

    existing = [
        item for item in (contract.get("candidate_next_actions") or [])
        if admissible_replan_candidate(item)
    ]
    preferred: list[dict[str, Any]] = []
    for item in existing:
        tool_name = str(item.get("tool") or "")
        if tool_name == "planner_scratchpad_read":
            preferred.append(item)
        elif tool_name == "repo_read" and target in {
            _repo_rel_token(path)
            for path in _agentic_v2_decision_paths(
                tool_name,
                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
            )
        }:
            preferred.append(item)
    route_candidate = _code_product_source_window_candidate(target, history=history)
    if route_candidate:
        preferred.insert(0, route_candidate)
    if not preferred:
        preferred.append(
            {
                "action": "block",
                "reason": "code_product_old_text_not_verifiable",
                "final_answer": (
                    f"{violation}: old_text is not verified in repo_read content for {target}. "
                    "No further source window is available; cannot build a valid diff."
                ),
            }
        )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*preferred, *existing]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    contract["candidate_next_actions"] = merged[:15]
    contract["required_next_progress"] = (
        f"{violation}. Change decision now: use a real planner_scratchpad_read window from "
        "required_working_set/candidate_next_actions if available, otherwise read a useful target "
        "window or return a typed block. Do not repeat placeholder old_text/new_text."
    )
    return contract


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validator-only gate. It rejects invalid planner decisions but does not execute a substitute tool."""
    decision = _normalize_terminal_planner_decision(decision if isinstance(decision, dict) else {})
    action = str(decision.get("action") or "tool").strip().lower()
    tool = _normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    contract = planner_evidence_contract(goal, history)
    violations: list[str] = []
    internal_inconsistencies: list[str] = []
    prompt_context_continuation_required = (
        decision.get("prompt_context_continuation_required")
        if isinstance(decision.get("prompt_context_continuation_required"), dict)
        else {}
    )
    tracking_errors = _prompt_window_tracking_metadata_errors(history)
    if tracking_errors:
        return {
            "ok": False,
            "violations": ["prompt_context_window_tracking_metadata_missing"],
            "evidence_contract": contract,
            "prompt_window_tracking_errors": tracking_errors,
        }
    if (
        AGENTIC_PLANNER_NATIVE_TOOLS
        and action == "tool"
        and not _native_required_tool_decision_has_transport_provenance(decision)
    ):
        violations.append("planner_text_tool_call_disallowed_in_native_mode")
        contract["required_next_progress"] = (
            "Native tool mode is required. Tool execution must arrive as "
            "message.tool_calls with native_tool_call=true; JSON-text action=tool "
            "is not executable. Choose a native tool_call, or return final/block JSON."
        )
        return {"ok": False, "violations": violations, "evidence_contract": contract}
    allowed_tool_names_source = (
        decision.get("allowed_tool_names")
        if isinstance(decision.get("allowed_tool_names"), list)
        else decision.get("allowed_native_tool_names")
    )
    if action == "tool" and isinstance(allowed_tool_names_source, list):
        allowed_tool_names = {
            _normalize_tool_name(str(name or ""))
            for name in allowed_tool_names_source
            if str(name or "").strip()
        }
        if tool not in allowed_tool_names:
            violations.append("tool_not_in_turn_surface")
            if (
                AGENTIC_PLANNER_NATIVE_TOOLS
                and _native_required_tool_decision_has_transport_provenance(decision)
            ):
                violations.append("native_tool_not_in_turn_surface")
            contract["required_next_progress"] = (
                "The tool call was not in the planner tool surface for this turn. "
                "Use only the current turn tool surface; if the quality gate is satisfied, "
                "produce action=final instead of calling another tool."
            )
    if action == "tool" and tool == "planner_scratchpad_read":
        requested_kind = str(args.get("kind") or "").strip()
        requested_doc_id = str(args.get("document_id") or args.get("id") or "").strip()
        if requested_kind in {"prompt_context", "prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND} and requested_doc_id:
            try:
                requested_offset = int(args.get("offset") or 0)
            except (TypeError, ValueError):
                requested_offset = 0
            consumed_offset = _prompt_window_consumed_offsets(history).get(requested_doc_id, 0)
            if consumed_offset > 0 and requested_offset < consumed_offset:
                violation = "planner_scratchpad_window_already_successful_without_progress"
                contract = _apply_duplicate_window_replan_contract(
                    contract,
                    violation=violation,
                    tool=tool,
                    args=args,
                    history=history,
                )
                return {
                    "ok": False,
                    "violations": [violation],
                    "evidence_contract": contract,
                    "document_id": requested_doc_id,
                    "requested_offset": requested_offset,
                    "expected_next_offset": consumed_offset,
                }
    if prompt_context_continuation_required and not _decision_matches_prompt_context_continuation(
        decision,
        prompt_context_continuation_required,
    ):
        violations.append("prompt_context_continuation_required")
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "required_prompt_context_continuation": prompt_context_continuation_required,
        }

    requested_limit = int(contract.get("requested_file_limit") or 0)
    target_scope = str(contract.get("resolved_goal_scope") or "")
    target_file = str(contract.get("resolved_goal_file") or "")
    target_kind = str(contract.get("target_kind") or "")
    review_goal = bool(contract.get("goal_requests_python_file_review"))
    known_paths = [str(x) for x in contract.get("known_paths_from_latest_repo_list_files") or []]
    admissible_reads = set(str(x) for x in (contract.get("validator_admissible_repo_read_paths") or []))
    read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]
    user_scope_claims = contract.get("user_scope_claims") if isinstance(contract.get("user_scope_claims"), list) else []

    if action in {"final", "done", "complete", "completed"}:
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        if final_contract and final_contract.get("final_allowed") is False:
            violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))
        final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "")
        code_product_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        action_plan_candidate = ""
        if code_product_contract.get("required"):
            if _final_answer_is_action_plan_without_code_product(final_answer):
                violations.append("final_action_plan_without_code_product")
                action_plan_candidate = final_answer
            verified_rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
            verified_paths = {
                _repo_rel_token(row.get("path"))
                for row in verified_rows
                if isinstance(row, dict) and row.get("path")
            }
            proposals = successful_code_edit_proposals(history)
            if not proposals:
                violations.append("missing_code_product_candidate")
            else:
                violations.extend(_code_product_payload_violations(proposals[-1], verified_paths))
        if target_kind == "file" and target_file:
            if target_file not in read_ok:
                violations.append(f"final_without_requested_file_read:{target_file}")
        if target_scope:
            listed_rows = contract.get("repo_list_files_evidence") if isinstance(contract.get("repo_list_files_evidence"), list) else []
            scope_listed = bool(contract.get("latest_in_scope_repo_list_path")) or any(
                _path_under_scope(str(row.get("path") or ""), target_scope)
                and str(row.get("path") or ".") not in ("", ".")
                for row in listed_rows if isinstance(row, dict)
            )
            scope_reads = [
                p for p in read_ok
                if _path_under_scope(p, target_scope)
                and _repo_readable_evidence_file(p)
            ]
            final_allowed = bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False
            if final_allowed and not scope_listed:
                internal_inconsistencies.append(f"quality_gate_internal_inconsistency:scope_listed_missing:{target_scope}")
            if final_allowed and not scope_reads:
                internal_inconsistencies.append(f"quality_gate_internal_inconsistency:scope_reads_missing:{target_scope}")
            if not scope_listed and not final_allowed:
                violations.append(f"final_without_in_scope_tree_or_list:{target_scope}")
            if not scope_reads and not final_allowed:
                violations.append(f"final_without_in_scope_concrete_read:{target_scope}")
        # Validator-only boundary: for generic repository analysis, once the
        # evidence gate says final_allowed=true, the controller must not keep
        # rejecting the planner's final only because its prose is not ideal.
        # Empty finals are still invalid; content quality is exposed as evidence
        # to the outer model, not turned into another hidden controller loop.
        if _repo_analysis_goal(goal) and not final_answer.strip():
            violations.append("final_empty_answer")
        if review_goal and not read_ok:
            violations.append("final_without_successful_repo_read_for_python_review")
        if review_goal and target_scope and any(not _path_under_scope(p, target_scope) for p in read_ok):
            violations.append(f"final_uses_read_paths_outside_requested_scope:{target_scope}")
        if review_goal and requested_limit:
            expected = requested_limit
            latest_list = latest_file_list_result(history)
            total_matches = latest_list.get("total_matches") if isinstance(latest_list, dict) else None
            if isinstance(total_matches, int) and total_matches > 0:
                expected = min(expected, total_matches)
            if len(read_ok) < expected:
                violations.append(f"final_before_required_read_count:{len(read_ok)}/{expected}")
        result = {
            "ok": not violations,
            "violations": violations,
            "evidence_contract": contract,
            "quality_gate_internal_inconsistency": internal_inconsistencies,
        }
        if action_plan_candidate:
            result["action_plan_candidate"] = action_plan_candidate
            result["semantic_goal_classification"] = contract.get("semantic_goal_classification")
        return result

    if action in {"block", "blocked", "need_user", "needs_user"}:
        # Planner-format failures are not accepted as a final loop result before
        # the controller classifies them. Plain text goes back to the planner;
        # malformed JSON/tool-shaped output may go to explicit Vulkan/GPU0
        # repair. The controller still does not invent a substitute action.
        reason = str(decision.get("reason") or "")
        reason_low = reason.lower()
        if reason == "planner_final_required_empty_output":
            violations.append("planner_final_required_empty_output")
            contract["required_next_progress"] = (
                "Quality gate is satisfied and no tool surface was provided. "
                "Return one strict JSON final object with final_answer. Do not call tools."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        if reason == "planner_native_tool_call_required":
            violations.append("planner_native_tool_call_required")
            contract["required_next_progress"] = (
                "Native tool mode is active and the planner emitted no message.tool_calls. "
                "Retry with one native tool_call from candidate_next_actions or return a real "
                "final/block JSON only if the evidence contract allows it."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        raw_planner_text = str(
            decision.get("raw_planner_text")
            or decision.get("raw_planner_text_preview")
            or decision.get("partial_content")
            or ""
        )
        if raw_planner_text and (
            "invalid_planner_output_non_json" in reason_low
            or "non-json" in reason_low
            or "no_json" in reason_low
            or "degenerate" in reason_low
            or "timeout" in reason_low
            or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        ):
            violations.append("planner_block_requires_controller_classification:" + reason[:160])
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        return {"ok": True, "violations": [], "evidence_contract": contract}

    if action != "tool":
        violations.append(f"invalid_action:{action or '<empty>'}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if not tool:
        violations.append("missing_tool")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool not in VALID_INTERNAL_TOOLS:
        violations.append(f"invalid_tool:{tool}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if _contract_final_required_now(contract):
        final_composition_tools = _final_composition_tool_names_from_candidates(contract)
        if tool not in final_composition_tools:
            violations.append("final_required_tool_call_disallowed")
            contract["required_next_progress"] = (
                "Quality gate is satisfied. The required next action is action=final. "
                "Do not call repo tools, memory tools or prompt windows unless a concrete "
                "answer_chunk composition tool is explicitly listed in candidate_next_actions."
            )

    if tool == "repo_search" and not _any_argument_group_present(args, [["query"], ["pattern"], ["symbol"]]):
        violations.append("repo_search_missing_query_pattern_or_symbol")
    elif tool == "repo_rg_search" and not _any_argument_group_present(args, [["query"], ["pattern"]]):
        violations.append("repo_rg_search_missing_pattern")
    elif tool == "repo_jq_query" and not _any_argument_group_present(args, [["query"], ["filter"]]):
        violations.append("repo_jq_query_missing_query")
    elif tool == "repo_ast_grep_search" and not _any_argument_group_present(args, [["pattern"], ["kind"]]):
        violations.append("repo_ast_grep_search_missing_pattern_or_kind")
    elif tool == "repo_ast_grep_dry_run" and not _any_argument_group_present(args, [["pattern", "rewrite"]]):
        violations.append("repo_ast_grep_dry_run_missing_pattern_or_rewrite")
    elif tool == "repo_tree_sitter_parse" and not _argument_value_present(args, "path"):
        violations.append("repo_tree_sitter_parse_missing_path")
    elif tool == "repo_unidiff_validate" and not _any_argument_group_present(args, [["unified_diff"], ["diff"]]):
        violations.append("repo_unidiff_validate_missing_diff")
    elif tool == "repo_git_apply_check" and not _any_argument_group_present(args, [["unified_diff"], ["diff"], ["patch"]]):
        violations.append("repo_git_apply_check_missing_diff")
    elif tool == "repo_shellcheck" and not _any_argument_group_present(args, [["path"], ["paths"]]):
        violations.append("repo_shellcheck_missing_path")
    elif tool == "repo_semgrep_scan" and not _any_argument_group_present(args, [["pattern"], ["config"]]):
        violations.append("repo_semgrep_scan_missing_pattern_or_config")
    elif tool == "repo_hyperfine_benchmark" and not _argument_value_present(args, "commands"):
        violations.append("repo_hyperfine_benchmark_missing_commands")
    elif tool == "repo_read" and not _repo_read_selector_present(args):
        violations.append("repo_read_missing_path_or_paths_items")
    elif tool == "planner_scratchpad_write" and not _any_argument_group_present(args, [["text"], ["content"]]):
        violations.append("planner_scratchpad_write_missing_text")
    elif tool == "planner_scratchpad_read" and not _planner_scratchpad_read_selector_present(args):
        violations.append("planner_scratchpad_read_missing_selector")
    elif tool == "runtime_sqlite_memory_search" and not _any_argument_group_present(args, [["query"], ["tag"], ["kind"]]):
        violations.append("runtime_sqlite_memory_search_missing_query_tag_or_kind")
    elif tool == "runtime_sqlite_memory_write" and not _any_argument_group_present(args, [["text"], ["content"]]):
        violations.append("runtime_sqlite_memory_write_missing_text")
    elif tool == "terminal_search_files" and not _argument_value_present(args, "query"):
        violations.append("terminal_search_files_missing_query")
    elif tool == "terminal_run_command_wait" and not _argument_value_present(args, "command"):
        violations.append("terminal_run_command_wait_missing_command")
    elif tool == "repo_command" and not _argument_value_present(args, "command"):
        violations.append("repo_command_missing_command")
    if violations:
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "planner_scratchpad_write" and str(args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
        state_text = str(args.get("text") or args.get("content") or "")
        state = _code_product_build_state_parse(state_text)
        if not state:
            violations.append("code_product_build_state_invalid_payload")
        else:
            state_target = _repo_rel_token(args.get("target_file") or args.get("path") or state.get("target_file") or "")
            if not state_target or state_target == ".":
                violations.append("code_product_build_state_missing_target")
            elif state_target not in set(read_ok):
                violations.append(f"code_product_build_state_target_not_read:{state_target}")
            status = str(state.get("status") or "")
            if status not in {"collecting_source", "ready_for_propose", "blocked_incomplete"}:
                violations.append("code_product_build_state_invalid_status")
            if status == "collecting_source" and not _code_product_build_state_has_collecting_progress(state):
                violations.append("code_product_build_state_collecting_source_without_progress")
            if _code_product_build_state_duplicate_write(history, target_file=state_target, text=state_text):
                violations.append("code_product_build_state_duplicate_without_progress")
            if status == "ready_for_propose" and not _code_product_build_state_ready_payload(state):
                violations.append("code_product_build_state_ready_without_complete_payload")
            if status == "blocked_incomplete" and not str(state.get("blocker") or "").strip():
                violations.append("code_product_build_state_blocked_without_blocker")
        if violations:
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    target_scope = _agentic_v2_goal_scope(str(goal or ""), contract)
    if target_scope and tool in {
        "repo_list_files",
        "repo_fd_files",
        "repo_rg_search",
        "repo_ast_grep_search",
        "repo_ast_grep_dry_run",
        "repo_tree_sitter_parse",
        "repo_ctags_symbols",
        "repo_semgrep_scan",
        "repo_shellcheck",
        "repo_ruff_check",
        "repo_pyright_check",
        "repo_pytest_run",
        "repo_read",
        "repo_search",
        "repo_write_file",
        "repo_apply_patch",
        "repo_propose_code_edit",
    }:
        out_of_scope = [
            p for p in _agentic_v2_decision_paths(tool, args)
            if p and not _path_under_scope(p, target_scope)
        ]
        if out_of_scope:
            for p in out_of_scope[:5]:
                violations.append(f"{tool}_scope_mismatch:path={p}:expected_under={target_scope}")
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_read":
        window_signature = _repo_read_window_signature(args)
        if window_signature and window_signature in _successful_window_signatures(history, "repo_read"):
            violation = "repo_read_window_already_successful_without_progress"
            violations.append(violation)
            contract = _apply_duplicate_window_replan_contract(
                contract,
                violation=violation,
                tool=tool,
                args=args,
                history=history,
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "planner_scratchpad_read":
        window_signature = _planner_scratchpad_window_signature(args)
        if window_signature and window_signature in _successful_window_signatures(history, "planner_scratchpad_read"):
            violation = "planner_scratchpad_window_already_successful_without_progress"
            violations.append(violation)
            contract = _apply_duplicate_window_replan_contract(
                contract,
                violation=violation,
                tool=tool,
                args=args,
                history=history,
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_read" and not _agentic_v2_read_has_window(args):
        already_read = set(_agentic_v2_successful_read_paths(history))
        repeated_reads = [p for p in _agentic_v2_decision_paths(tool, args) if p in already_read]
        if repeated_reads:
            violations.append("repo_read_already_successful:" + ",".join(repeated_reads[:5]))
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_list_files":
        path = _repo_rel_token(args.get("path") or ".")
        suffix = str(args.get("suffix") or args.get("glob") or "")
        if not _path_exists_repo_relative(path):
            violations.append(f"non_existing_path:{path}")
        if _repo_path_kind(path) == "file":
            violations.append(f"repo_list_files_on_file_path_use_repo_read:{path}")
        if target_scope and not _path_under_scope(path, target_scope):
            violations.append(f"repo_list_files_scope_mismatch:path={path}:expected_under={target_scope}")
        if review_goal and requested_limit:
            try:
                limit = int(args.get("limit") or args.get("max_files") or 0)
            except Exception:
                limit = 0
            if limit != requested_limit:
                violations.append(f"repo_list_files_limit_mismatch:got={limit or '<missing>'}:expected={requested_limit}")
        if review_goal and suffix and ".py" not in suffix and "*.py" not in suffix:
            violations.append(f"repo_list_files_suffix_not_python:{suffix}")
        if repeated_tool_call_count(history, tool, args) >= 1 and known_paths:
            violations.append("repeated_repo_list_files_after_useful_file_list")

    if tool == "repo_tree" and repeated_tool_call_count(history, tool, args) >= 1:
        violations.append("repeated_same_tool_arguments_without_progress")

    if tool in {"repo_read", "repo_apply_patch", "repo_write_file", "repo_propose_code_edit"}:
        paths = _decision_paths(args)
        if tool == "repo_apply_patch" and args.get("path"):
            paths = [str(args.get("path"))]
        if tool == "repo_propose_code_edit" and (args.get("target_file") or args.get("path")):
            paths = [_repo_rel_token(args.get("target_file") or args.get("path"))]
        if not paths:
            if tool == "repo_read":
                violations.append("repo_read_missing_path_or_paths_items")
            else:
                violations.append(f"{tool}_missing_path_or_paths")
        for path in paths:
            path = _repo_rel_token(path)
            if target_scope and tool == "repo_read" and not _path_under_scope(path, target_scope):
                violations.append(f"repo_read_path_outside_requested_scope:{path}:expected_under={target_scope}")
            if tool == "repo_read" and known_paths and path not in known_paths and path not in admissible_reads:
                # Existing files are valid only if they have been discovered in tree/list evidence.
                violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")
            if tool in {"repo_read", "repo_apply_patch", "repo_propose_code_edit"} and not _path_exists_repo_relative(path):
                violations.append(f"non_existing_path:{path}")
            if tool == "repo_apply_patch":
                old_value = args.get("old_text")
                new_value = args.get("new_text")
                if _copyable_example_text(old_value) or _copyable_example_text(new_value):
                    violations.append("repo_apply_patch_placeholder_text")
                    contract = _apply_unverified_old_text_replan_contract(
                        contract,
                        target_file=path,
                        violation="repo_apply_patch_placeholder_text",
                        history=history,
                    )
                elif isinstance(old_value, str) and old_value and not _old_text_verified_by_repo_read(history, path, old_value):
                    violations.append("repo_apply_patch_old_text_not_from_verified_read")
                    contract = _apply_unverified_old_text_replan_contract(
                        contract,
                        target_file=path,
                        violation="repo_apply_patch_old_text_not_from_verified_read",
                        history=history,
                    )
            if tool == "repo_propose_code_edit" and path not in set(read_ok):
                violations.append(f"code_product_target_not_read:{path}")
            if tool == "repo_propose_code_edit":
                claim_conflict = _scope_claim_conflict_for_path(path, user_scope_claims)
                if claim_conflict and not _target_scope_conflict_resolved(path, args, contract):
                    if "target_scope_conflict_unresolved" not in violations:
                        violations.append("target_scope_conflict_unresolved")
            if (
                tool == "repo_propose_code_edit"
                and not target_file
                and goal_requires_code_product_report(goal)
                and _code_product_low_signal_target(path, contract)
            ):
                violations.append(f"code_product_low_signal_target:{path}")
        if tool == "repo_propose_code_edit":
            edit_kind = str(args.get("edit_kind") or "")
            if edit_kind not in {"unified_diff", "structured_edit", "no_op"}:
                violations.append("repo_propose_code_edit_invalid_edit_kind")
            if not str(args.get("rationale") or "").strip():
                violations.append("repo_propose_code_edit_missing_rationale")
            if edit_kind == "unified_diff":
                diff_text = args.get("unified_diff")
                if not isinstance(diff_text, str) or not diff_text.strip():
                    old_value = args.get("old_text")
                    new_value = args.get("new_text")
                    if not (isinstance(old_value, str) and isinstance(new_value, str)):
                        violations.append("repo_propose_code_edit_missing_unified_diff")
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                    elif _copyable_example_text(old_value) or _copyable_example_text(new_value):
                        violations.append("repo_propose_code_edit_placeholder_text")
                        if paths:
                            contract = _apply_unverified_old_text_replan_contract(
                                contract,
                                target_file=paths[0],
                                violation="repo_propose_code_edit_placeholder_text",
                                history=history,
                            )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                    elif paths and not _old_text_verified_by_repo_read(history, paths[0], old_value):
                        violations.append("repo_propose_code_edit_old_text_not_from_verified_read")
                        contract = _apply_unverified_old_text_replan_contract(
                            contract,
                            target_file=paths[0],
                            violation="repo_propose_code_edit_old_text_not_from_verified_read",
                            history=history,
                        )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                else:
                    diff_errors = validate_unified_diff_text(
                        unified_diff=diff_text,
                        target_file=paths[0] if paths else str(args.get("target_file") or args.get("path") or ""),
                        require_unidiff=True,
                    )
                    blocking_diff_errors = [
                        str(error)
                        for error in diff_errors
                        if str(error) != "unidiff_dependency_missing"
                    ]
                    if blocking_diff_errors:
                        violations.append("invalid_code_product_candidate")
                        violations.extend(
                            f"repo_propose_code_edit_unified_diff_error:{error}"
                            for error in blocking_diff_errors[:6]
                        )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
            if edit_kind == "structured_edit" and not isinstance(args.get("structured_operations"), list):
                violations.append("repo_propose_code_edit_missing_structured_operations")
                if repeated_tool_call_count(history, tool, args) >= 1:
                    violations.append("code_product_route_shift_required")
            if edit_kind == "no_op" and (
                args.get("unified_diff")
                or args.get("structured_operations")
                or args.get("old_text")
                or args.get("new_text")
            ):
                violations.append("repo_propose_code_edit_no_op_has_patch_payload")

    if repeated_tool_call_count(history, tool, args) >= 2:
        violations.append("repeated_same_tool_arguments_without_progress")

    invalid_signature = _canonical_invalid_code_product_decision_signature(decision, violations)
    invalid_repeat_count = _invalid_code_product_decision_signature_count(history, invalid_signature)
    if invalid_signature:
        code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        code_contract["latest_invalid_decision_signature"] = invalid_signature
        code_contract["latest_invalid_decision_repeat_count"] = invalid_repeat_count + 1
        if invalid_repeat_count >= 1:
            raw_disallowed = contract.get("disallowed_next_decision_signatures")
            disallowed = [
                item for item in (raw_disallowed if isinstance(raw_disallowed, list) else [])
                if isinstance(item, dict)
            ]
            disallowed_entry = {
                **invalid_signature,
                "repeat_count": invalid_repeat_count + 1,
                "rule": "do_not_repeat_invalid_code_product_decision",
            }
            if _invalid_decision_signature_key(invalid_signature) not in {
                _invalid_decision_signature_key(item) for item in disallowed
            }:
                disallowed.append(disallowed_entry)
            contract["disallowed_next_decision_signatures"] = disallowed
            code_contract["disallowed_next_decision_signatures"] = disallowed
        if invalid_repeat_count >= 2 and "planner_repeated_invalid_code_product_decision" not in violations:
            violations.append("planner_repeated_invalid_code_product_decision")
            code_contract["terminal_blocker"] = "planner_repeated_invalid_code_product_decision"
        contract["code_product_contract"] = code_contract

    response = {"ok": not violations, "violations": violations, "evidence_contract": contract}
    if invalid_signature:
        response["invalid_decision_signature"] = invalid_signature
        response["invalid_decision_repeat_count"] = invalid_repeat_count + 1
    return response



def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
    if not isinstance(decision, dict):
        return ""
    return str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )


def _vulkan_repair_seen(history: list[dict[str, Any]]) -> int:
    """Count explicit Vulkan/GPU0 repair attempts already surfaced in history."""
    count = 0
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("guard_type") == "vulkan_decision_repair":
            count += 1
        elif isinstance(result.get("vulkan_repair"), dict):
            count += 1
    return count


def _planner_incomprehensible_retry_count(history: list[dict[str, Any]]) -> int:
    """Count the current consecutive planner-repeat streak.

    The retry budget is for the active bad-output streak, not for the whole job.
    A successful tool result, cached evidence delivery, validation guard of a
    different kind, or any other progress starts a new agentic segment and must
    not consume retry budget for later planner emissions.
    """
    count = 0
    for item in reversed(history if isinstance(history, list) else []):
        if not isinstance(item, dict):
            break
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") == "controller_guard" and result.get("guard_type") in {
            "planner_retry_required",
            "planner_memory_false_unavailable_claim",
        }:
            count += 1
            continue
        break
    return count


def _planner_memory_false_unavailable_claim(raw_text: str, planner_memory: dict[str, Any]) -> bool:
    if not isinstance(planner_memory, dict) or planner_memory.get("available") is not True:
        return False
    raw = str(raw_text or "").lower()
    if not raw.strip():
        return False
    patterns = (
        "long-term memory is not available",
        "long term memory is not available",
        "long-term memory unavailable",
        "long term memory unavailable",
        "persistent memory is not available",
        "memory_long term not aviable",
        "memory_long term not available",
    )
    return any(pattern in raw for pattern in patterns)


def _decision_memory_claim_text(decision: dict[str, Any]) -> str:
    decision = decision if isinstance(decision, dict) else {}
    parts = [
        decision.get("raw_planner_text"),
        decision.get("raw_planner_text_preview"),
        decision.get("partial_content"),
        decision.get("final_answer"),
        decision.get("reason"),
    ]
    return "\n".join(str(part) for part in parts if part not in (None, "", [], {}))


def _raw_planner_text_classification(text: str) -> str:
    """Classify raw planner output for planner retry vs GPU0 repair.

    ``plain_text_non_json`` and ``mixed_prose_with_embedded_json`` are handled by
    asking the planner to repeat a pure JSON decision. Vulkan/GPU0 repair is
    reserved for JSON-shaped or tool-call shaped emissions that are broken but
    still structurally related to the loop protocol.
    """
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return "empty"
    if _raw_planner_text_has_many_json_examples(stripped):
        return "long_mixed_json_examples"
    if _raw_planner_text_has_valid_embedded_json_with_prose(stripped):
        return "mixed_prose_with_embedded_json"
    if re.fullmatch(r"```(?:json|JSON)?\s*\r?\n.*?\r?\n```", stripped, re.S):
        return "markdown_fenced_json_non_json"
    low = raw.lower()
    if _raw_planner_text_has_explicit_tool_alias_invocation(raw):
        return "tool_like_malformed"
    if re.search(r"</?JupyterNotebookCell\b", raw, re.I):
        return "native_notebook_cell_output"
    if stripped.startswith("{") or stripped.startswith("["):
        return "corrupt_json"
    if re.search(r"```(?:json|JSON)?\s*[\r\n{]", raw):
        return "corrupt_json"
    if "{" in raw or "}" in raw:
        if re.search(r'["\']?(?:action|tool|arguments|final_answer|reason)["\']?\s*[:=]', raw, re.I):
            return "corrupt_json"
    if re.search(r'["\']?(?:action|tool|arguments)["\']?\s*[:=]', raw, re.I):
        return "tool_like_malformed"
    for tool in VALID_INTERNAL_TOOLS:
        tool_low = tool.lower()
        if re.search(
            rf"(?<![\w.-]){re.escape(tool_low)}(?![\w.-])\s*(?:[:=(]|\{{|\[)",
            low,
        ):
            return "tool_like_malformed"
    return "plain_text_non_json"


def _raw_planner_text_has_explicit_tool_alias_invocation(text: str) -> bool:
    """Detect explicit pseudo-tool invocations such as ``SAVE_FILE: ...``.

    This is intentionally narrower than the full alias table. Generic words
    like ``read`` or ``run`` are allowed in prose and must not route ordinary
    text to GPU0. Alias-shaped tool emissions with underscores are controller
    protocol attempts, so they belong on the structured repair path.
    """
    raw = str(text or "")
    if not raw.strip():
        return False
    try:
        from .tool_contract import TOOL_ALIASES  # noqa: PLC0415
    except Exception:
        TOOL_ALIASES = {}
    generic_aliases = {
        "capabilities", "tools", "status", "diff", "search", "grep", "rg",
        "read", "patch", "edit", "validate", "validation", "smoke",
        "command", "run", "compile", "terminal", "tree", "directory",
        "files",
    }
    aliases: set[str] = set()
    for alias, target in dict(TOOL_ALIASES).items():
        alias_text = str(alias or "").strip().lower()
        target_text = str(target or "").strip()
        if not alias_text or alias_text in generic_aliases:
            continue
        if target_text not in VALID_INTERNAL_TOOLS:
            continue
        if "_" in alias_text or alias_text.startswith(("repo", "terminal", "memory", "scratchpad")):
            aliases.add(alias_text)
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?im)^\s*<?{re.escape(alias)}\s*(?:[:=(]|\{{|\[)", raw):
            return True
    return False


def _raw_planner_text_has_many_json_examples(text: str) -> bool:
    raw = str(text or "")
    low = raw.lower()
    fenced_json_count = len(re.findall(r"```(?:json|JSON)?\s*\r?\n\s*[\[{]", raw))
    if fenced_json_count >= 4:
        return True
    example_marker_count = sum(
        low.count(marker)
        for marker in (
            "出力の例",
            "output example",
            "example ",
            "esempio",
            "ejemplo",
            "例",
        )
    )
    if len(raw) >= 4096 and fenced_json_count >= 2 and example_marker_count >= 2:
        return True
    if len(raw) >= 4096 and fenced_json_count >= 2:
        repeated_tool_mentions = sum(
            low.count(f'"tool": "{tool.lower()}"') + low.count(f'"tool":"{tool.lower()}"')
            for tool in ("repo_read", "repo_search", "repo_tree", "repo_list_files")
        )
        return repeated_tool_mentions >= 3
    return False


def _raw_planner_text_has_valid_embedded_json_with_prose(text: str) -> bool:
    """Detect valid JSON embedded in prose without extracting it as a decision."""
    raw = str(text or "").strip()
    if not raw:
        return False
    fenced = list(re.finditer(r"```(?:json|JSON)?\s*\r?\n(?P<body>.*?)\r?\n```", raw, re.S))
    if len(fenced) == 1:
        match = fenced[0]
        if _parse_strict_json_object(match.group("body")):
            outside = (raw[: match.start()] + raw[match.end() :]).strip()
            return bool(outside)
    if raw.startswith("{") or raw.startswith("["):
        return False
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[\[{]", raw):
        try:
            decoded, end = decoder.raw_decode(raw[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            spans.append((match.start(), match.start() + end))
    if len(spans) != 1:
        return False
    start, end = spans[0]
    outside = (raw[:start] + raw[end:]).strip()
    return bool(outside)


def _raw_planner_text_retries_on_gpu1(text: str) -> bool:
    return _raw_planner_text_classification(text) in {
        "plain_text_non_json",
        "mixed_prose_with_embedded_json",
        "markdown_fenced_json_non_json",
        "long_mixed_json_examples",
        "native_notebook_cell_output",
    }


def _raw_planner_text_looks_like_tool_request(text: str) -> bool:
    """Detect malformed-but-recognizable tool/JSON requests for GPU0 repair."""
    return _raw_planner_text_classification(text) in {
        "corrupt_json",
        "tool_like_malformed",
    }


def _should_retry_incomprehensible_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    """Retry only raw non-JSON planner output, without inventing a controller action."""
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    reason = str(decision.get("reason") or "")
    retryable_reason = (
        reason == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE"
        or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        or "timeout" in reason.lower()
        or "non_json" in reason.lower()
        or "no_json" in reason.lower()
        or "non-json" in reason.lower()
    )
    if not retryable_reason:
        return False
    raw_planner_text = _decision_raw_planner_text(decision)
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    if int(retry_limit or 0) <= 0:
        return False
    return _planner_incomprehensible_retry_count(history) < int(retry_limit)


def _is_unrecoverable_plain_text_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    raw_planner_text = _decision_raw_planner_text(decision)
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    reason = str(decision.get("reason") or "").lower()
    relevant_reason = (
        "invalid_planner_output_non_json" in reason
        or "non-json" in reason
        or "non_json" in reason
        or "no_json" in reason
        or "degenerate" in reason
        or "timeout" in reason
    )
    if not relevant_reason:
        return False
    if int(retry_limit or 0) > 0:
        return _planner_incomprehensible_retry_count(history) >= int(retry_limit)
    return True


def _compact_repair_history(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        rows.append({
            "step": item.get("step"),
            "decision": {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
            "tool_result": {
                k: result.get(k)
                for k in ("tool", "ok", "summary", "path", "count", "total_matches", "truncated", "violations")
                if result.get(k) not in (None, "", [], {})
            },
        })
    return rows


def _compact_vulkan_repair_evidence_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    compact: dict[str, Any] = {"schema": "vulkan_repair_evidence_contract.v1"}
    for key in (
        "semantic_goal_classification",
        "goal_requests_code_product",
        "goal_requires_code_product_report",
        "goal_requests_apply",
        "target_kind",
        "resolved_goal_file",
        "resolved_goal_scope",
        "successful_repo_read_count",
        "verified_content_read_count",
        "planner_may_choose_final",
        "required_next_progress",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    for key in (
        "known_paths_from_latest_repo_list_files",
        "successful_repo_read_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
        "failed_repo_read_paths",
        "failed_repo_list_files_paths",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=140, list_limit=16)
    for key in (
        "code_product_contract",
        "finalization_contract",
        "core_discovery_status",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    candidates = contract.get("candidate_next_actions")
    if isinstance(candidates, list) and candidates:
        compact["candidate_next_actions"] = _prompt_clip_value(
            candidates,
            text_limit=260,
            list_limit=4,
        )
    rejections = contract.get("validation_rejections_tail")
    if isinstance(rejections, list) and rejections:
        compact["validation_rejections_tail"] = _prompt_clip_value(
            rejections,
            text_limit=260,
            list_limit=4,
        )
    return _prompt_clip_value(compact, text_limit=500, list_limit=16)


def _should_attempt_vulkan_repair(
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
) -> bool:
    """Allow explicit IA repair, but no controller fallback/normalization.

    Vulkan/GPU0 11435 may be asked once to convert the planner's own malformed
    emission or invalid tool proposal into a valid loop JSON decision. The
    original planner text remains visible in events/history/wrapper; the
    controller does not invent a substitute action.
    """
    if _vulkan_repair_seen(history) >= 1:
        return False
    decision = decision if isinstance(decision, dict) else {}
    action = str(decision.get("action") or "").strip().lower()
    reason = str(decision.get("reason") or "")
    contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
    semantic = contract.get("semantic_goal_classification") if isinstance(contract.get("semantic_goal_classification"), dict) else {}
    if (
        contract.get("goal_requests_code_product")
        or contract.get("goal_requires_code_product_report")
        or bool(semantic.get("must_produce_code_product"))
    ):
        return False
    if action == "block":
        raw_planner_text = _decision_raw_planner_text(decision)
        reason_low = reason.lower()
        if raw_planner_text and _raw_planner_text_looks_like_tool_request(raw_planner_text) and (
            "invalid_planner_output_non_json" in reason_low
            or "non-json" in reason_low
            or "no_json" in reason_low
            or "degenerate" in reason_low
            or "timeout" in reason_low
            or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        ):
            return True
        return False
    if action == "tool":
        tool = _normalize_tool_name(str(decision.get("tool") or ""))
        violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
        if tool == "repo_propose_code_edit":
            return False
        if any(
            str(violation).startswith((
                "repo_propose_code_edit_",
                "code_product_",
                "missing_code_product_candidate",
                "invalid_code_product_candidate",
                "prompt_context_continuation_required",
                "prompt_context_window_",
                "planner_scratchpad_window_",
                "planner_scratchpad_read_missing_selector",
                "repo_read_window_",
                "non_existing_path:",
                "repo_read_already_successful:",
                "repo_read_path_not_from_prior_file_evidence:",
                "repo_read_path_outside_requested_scope:",
                "repo_list_files_on_file_path_use_repo_read:",
                "repo_list_files_scope_mismatch:",
                "repo_list_files_limit_mismatch:",
                "repo_list_files_suffix_not_python:",
                "repeated_repo_list_files_after_useful_file_list",
                "tool_not_in_turn_surface",
                "native_tool_not_in_turn_surface",
                "final_required_tool_call_disallowed",
            ))
            for violation in violations
        ):
            return False
        if "repeated_same_tool_arguments_without_progress" in violations:
            return False
        return True
    return False


def vulkan_repair_invalid_planner_decision(
    *,
    goal: str,
    step: int,
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Ask Vulkan/GPU0 11435 for one explicit repair of the planner emission.

    This is not a hidden controller fallback. 11435 receives the original
    planner emission/proposal and must return one pure JSON decision. The raw
    planner output is preserved and surfaced even when repair succeeds.
    """
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = _repair_cache_key(raw_planner_text)
    if _vulkan_repair_seen(history) >= 1:
        return {
            "ok": False,
            "error": "vulkan_repair_already_attempted_for_this_job",
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    payload = {
        "model": OLLAMA_TASK_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sei il lane Vulkan/GPU0/11435 di riparazione esplicita del loop. "
                    "Non scegliere tu una sequenza deterministica. Non nascondere errori. "
                    "Ricevi una emissione/proposta del planner e devi restituire UN SOLO "
                    "oggetto JSON puro con action=tool|final|block. "
                    "Se la emissione contiene una risposta naturale utile, mettila dentro "
                    "final_answer. Se contiene una tool call utile, correggi solo il JSON. "
                    "Se non puoi riparare senza inventare, ritorna action=block con final_answer."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "task": "explicit_vulkan_gpu0_repair_planner_emission",
                    "goal": goal,
                    "step": step,
                    "original_planner_decision": decision,
                    "raw_planner_text": raw_planner_text[:20000],
                    "validator_violations": validation.get("violations"),
                    "evidence_contract": _compact_vulkan_repair_evidence_contract(
                        validation.get("evidence_contract")
                    ),
                    "evidence_contract_bounded_for_repair": True,
                    "history_tail": _compact_repair_history(history),
                    "available_tools": internal_tool_prompt(exclude_vulkan=False),
                    "rules": [
                        "Return pure JSON only; no markdown fences, no prose outside JSON.",
                        "Do not invent paths or claim files were read if evidence does not show it.",
                        "A natural-language answer is allowed only inside final_answer.",
                        "A tool call is allowed only if action=tool, tool is valid, and arguments are explicit.",
                        "Expose uncertainty in final_answer rather than hiding it.",
                    ],
                }, ensure_ascii=False, default=str),
            },
        ],
        "options": ollama_options(num_predict=1600),
    }

    response = post_json(OLLAMA_TASK_URL, payload, timeout=min(90, max(30, AGENTIC_PLANNER_STEP_TIMEOUT)))
    if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
        return {
            "ok": False,
            "error": response.get("error") or response.get("error_type") or "vulkan_repair_backend_error",
            "raw_response": response,
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    raw_text = str(message.get("content") or response.get("response") or "")
    repaired = _parse_strict_json_object(raw_text)
    if not isinstance(repaired, dict) or not repaired:
        return {
            "ok": False,
            "error": "vulkan_repair_no_pure_json_decision",
            "raw_text_preview": raw_text[:2000],
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    repaired["repaired_by_vulkan_gpu0_11435"] = True
    repaired["original_planner_decision"] = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments", "reason", "final_answer")
        if decision.get(k) not in (None, "", [], {})
    }
    if raw_planner_text:
        repaired["raw_planner_text_before_repair"] = raw_planner_text[:4000]
    return {
        "ok": True,
        "repaired_decision": repaired,
        "raw_text_preview": raw_text[:2000],
        "raw_planner_text_preview": raw_planner_text[:2000],
        "repair_cache_key": repair_key,
    }


def controller_guard_result_for_validation(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
    guard = {
        "tool": "controller_guard",
        "ok": True,
        "guard_type": "planner_decision_validation",
        "summary": (
            "planner_decision_validation_failed: " + "; ".join(str(v) for v in violations)
            if violations else "planner_decision_validation_failed"
        ),
        "violations": violations,
        "evidence_contract": contract,
        "rejected_decision": {
            k: (
                _prompt_clip_text(decision.get(k), 12000)
                if k == "final_answer" else decision.get(k)
            )
            for k in (
                "action", "tool", "arguments", "reason", "selected_by_3572",
                "coerced_by_3572", "planner_stream_meta", "final_answer",
            )
            if decision.get(k) not in (None, "", [], {})
        },
        "ollama_turn": _planner_ollama_turn_from_decision(decision),
    }
    if validation.get("semantic_goal_classification") not in (None, "", [], {}):
        guard["semantic_goal_classification"] = validation.get("semantic_goal_classification")
    if validation.get("invalid_decision_signature") not in (None, "", [], {}):
        guard["invalid_decision_signature"] = validation.get("invalid_decision_signature")
    if validation.get("invalid_decision_repeat_count") not in (None, "", [], {}):
        guard["invalid_decision_repeat_count"] = validation.get("invalid_decision_repeat_count")
    required_next_progress = str(contract.get("required_next_progress") or "").strip()
    if required_next_progress:
        guard["next_instruction"] = required_next_progress
    candidate_next_actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    if candidate_next_actions:
        guard["candidate_next_actions"] = candidate_next_actions[:6]
    if validation.get("action_plan_candidate") not in (None, "", [], {}):
        guard["action_plan_candidate"] = _prompt_clip_text(
            validation.get("action_plan_candidate"),
            12000,
        )
        if not guard.get("next_instruction"):
            guard["next_instruction"] = (
                "Treat action_plan_candidate as an intermediate plan only. "
                "Do not final with it. Use it to choose repo_read evidence and then "
                "repo_propose_code_edit with a complete inline diff/ops payload."
            )
    return guard


# ---------------------------------------------------------------------------
# Planner decision (single step)
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM = """\
Sei il planner principale 30B dell'agente locale AI-Carmine.
Il runtime esegue i tool; tu devi scegliere il prossimo passo.
Rispondi SOLO con JSON valido. Non usare markdown, testo libero, marker, prompt shell o token di ruolo.
Non usare tag o formati notebook/cella come <JupyterNotebookCell>, blocchi Python, notebook nativi o pseudo-tool non elencati: il runtime accetta solo un oggetto JSON puro.
Se il backend espone tool_call native, preferisci native tool_calls ai JSON testuali. Non simulare tool_call in prosa.
Azioni consentite: tool, final, block.
Se evidence_contract.finalization_contract.final_allowed=true devi preferire action=final, ma solo dopo avere letto almeno un file concreto nell'area core che stai descrivendo.
Un final valido per analisi repository deve usare evidence_contract.operational_notes.read_notes e file_memory:
- workflow/canonical entry;
- problemi/verifiche lette se presenti;
- core candidates con path concreti;
- limiti della copertura;
- path concreti presenti nell'evidenza.
Non usare il template ripetuto "core directories are ... well-structured repository ... clear separation of concerns" se non aggiungi evidenza concreta file-per-file.
Nel final cita almeno 5 path letti o listati e spiega il ruolo di almeno 3 file concreti; se non hai letto file nell'area core, scegli repo_read o terminal_run_command_wait invece di final.
Non ripetere repo_tree/repo_list_files/repo_read già respinti o già utili.
candidate_next_actions è una lista di mosse ammissibili, non uno script obbligatorio: se serve puoi scegliere un altro tool evidence-bound.
Hai accesso PowerShell progetto tramite terminal_run_command_wait con cwd=evidence_contract.project_powershell_access.cwd; è accesso del processo 3572, non elevazione UAC. Usalo per diagnostica read-only o validazioni mirate quando repo_* non basta.
vulkan_helper resta un tool interno composito disponibile: usalo una sola volta quando serve evidenza helper/Vulkan; se fallisce o viene respinto, torna al planner con altra mossa evidence-bound.
Il controller inietta required_working_set e optional_context prima di ogni turno. required_working_set è l'unico working set non troncabile per decisioni concrete; se manca un contenuto richiesto, scegli tool o block, non inferire da metadata.
Se una finestra in required_working_set o optional_context contiene schema planner_prompt_context_window.v1, il testo completo è in SQLite job-local. Quando has_more_after=true usa planner_scratchpad_read con kind=prompt_context_window, document_id, offset=window_end e max_chars per leggere la prossima finestra reale. Non trattare document_id/hash/count come sostituto del testo.
Memoria/RAG/chunk SQLite sono substrato intrinseco dentro optional_context.intrinsic_context, non nuovi tool da scegliere. Puoi chiamare runtime_sqlite_memory_search/write solo dopo avere nominato un gap selettivo concreto rimasto dopo intrinsic_context. Se intrinsic_context.retrieved_memory.count=0, la memoria è disponibile ma non contiene record pertinenti. Non dire mai "Long-term memory is not available".
Per risposte larghe che non entrano in un singolo turno, usa planner_scratchpad_write con kind=answer_chunk per salvare sezioni complete e validate. Il wrapper ricompone solo chunk completi; non usare answer_chunk come sostituto di repo_read/repo_propose_code_edit.
Per code product/diff larghi che richiedono piu finestre, usa planner_scratchpad_write con kind=code_product_build_state per salvare stato JSON schema code_product_build_state.v1; quando status=ready_for_propose chiama repo_propose_code_edit con payload completo, quando status=blocked_incomplete restituisci action=block typed.
Non inventare file. Usa solo path repo-relative presenti in history/evidence_contract.
Se il goal chiede un diff, unified diff, differenziale di codice, refactoring concreto, proposta patch o code product, non puoi fare final con sola prosa: devi prima leggere il target con repo_read e poi chiamare repo_propose_code_edit.
Se hai gia' prodotto solo raccomandazioni/next steps per un goal code-product, quel testo e' action_plan_candidate: usalo per scegliere il prossimo repo_read/repo_propose_code_edit, non ripeterlo come final.
repo_propose_code_edit è report-only: produce un payload completo con kind=code_edit_proposal, target_file, edit_kind, unified_diff completo oppure structured_operations complete oppure no_op con rationale. Non usare preview, summary o artifact path come sostituto del diff.
Per sostituzioni esatte dove old_text e new_text sono noti dal repo_read, devi usare repo_propose_code_edit con edit_kind=unified_diff, old_text e new_text: il tool genera il unified_diff completo con difflib. Non riscrivere manualmente un diff se puoi passare old_text/new_text esatti.
Per un goal di code product non chiamare repo_apply_patch salvo richiesta esplicita di apply/edit/fix/write. Per un goal apply/edit/fix/write continua a usare repo_apply_patch dopo repo_read dell'old_text esatto.
Per modificare file devi prima leggere l'old_text esatto con repo_read.
Gli esempi in tool_shape_examples e argument_contract.shape_examples sono solo shape examples, not runnable calls. Non copiare mai valori EXAMPLE_ONLY_DO_NOT_COPY. Per scegliere un tool usa valori reali da candidate_next_actions, required_working_set, verified_content_reads o input utente esplicito.
Shape examples non eseguibili sono nel payload tool_shape_examples. In native tool mode usa solo message.tool_calls per i tool; in legacy JSON mode usa solo il formato dichiarato da tool_shape_examples. Gli esempi non sono chiamate reali.
Non usare vulkan_helper come tool ordinario di navigazione: se una chiamata tool è invalida, 3572 può chiedere riparazione al lane Vulkan/11435.
"""


def _planner_system_for_current_mode() -> str:
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        return _PLANNER_SYSTEM
    return _PLANNER_SYSTEM.replace(
        "Rispondi SOLO con JSON valido. Non usare markdown, testo libero, marker, prompt shell o token di ruolo.",
        (
            "Quando scegli un tool devi usare solo native tool_calls del backend, "
            "non JSON testuale con action=tool. Per final o block rispondi con "
            "un singolo JSON valido. Non usare markdown, testo libero, marker, "
            "prompt shell o token di ruolo."
        ),
    ).replace(
        "Se il backend espone tool_call native, preferisci native tool_calls ai JSON testuali. Non simulare tool_call in prosa.",
        (
            "Il backend espone native tool_calls: per qualunque tool call devi usare "
            "message.tool_calls. Non simulare tool_call in prosa, nel content, in tag "
            "<tool_call> o come JSON testuale."
        ),
    ).replace(
        "Azioni consentite: tool, final, block.",
        (
            "Azioni testuali consentite quando non usi native tool_calls: final, block. "
            "L'azione tool nel content non e' consentita in native tool mode."
        ),
    )


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    goal = str(state.get("goal") or "")
    if _input_error_goal(goal):
        return {
            "action": "block",
            "reason": "missing_user_request_no_fallback",
            "final_answer": (
                "Public tool call is missing the natural-language user request. "
                "No semantic fallback was generated; the raw input error is surfaced."
            ),
        }
    from .tool_contract import TOOLS_SCHEMA  # noqa: PLC0415

    all_tool_manifest = [
        {
            "name": item["function"]["name"],
            "description": item["function"]["description"],
            "parameters": item["function"]["parameters"],
            "argument_contract": item["function"].get("argument_contract") or {},
        }
        for item in TOOLS_SCHEMA
        if isinstance(item.get("function"), dict)
        and item["function"].get("name") in internal_tools_list(exclude_vulkan=False)
    ]

    last_step = history[-1] if history else {}
    last_tool_result = last_step.get("tool_result") if isinstance(last_step, dict) else {}
    evidence_contract = planner_evidence_contract(goal, history)
    planner_memory = state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else {}
    if not planner_memory:
        planner_memory = planner_memory_surface({
            "goal": goal,
            "limit": 12,
            "target_key": _controller_memory_target_key(goal, evidence_contract),
        }, agent_job_root(job_id))
    intrinsic_context = build_planner_intrinsic_context(
        goal=goal,
        history=history,
        evidence_contract=evidence_contract,
        planner_memory=planner_memory,
        rag_db=PLANNER_RAG_DB,
        num_ctx=AGENTIC_PLANNER_NUM_CTX,
        max_chars=PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
        rag_top_k=PLANNER_INTRINSIC_RAG_TOP_K,
        rag_char_budget=PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
        rerank_engine=PLANNER_RAG_RERANKING_ENGINE,
        rerank_url=PLANNER_RAG_EXTERNAL_RERANKER_URL,
        rerank_model=PLANNER_RAG_RERANKING_MODEL,
        rerank_timeout_seconds=PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
        rag_embedding_batch_size=PLANNER_RAG_EMBEDDING_BATCH_SIZE,
    )
    if isinstance(intrinsic_context.get("budget_report"), dict):
        intrinsic_context["budget_report"]["num_ctx_requested"] = AGENTIC_PLANNER_NUM_CTX_REQUESTED
        intrinsic_context["budget_report"]["num_ctx_cap"] = AGENTIC_PLANNER_NUM_CTX_CAP
    evidence_contract = planner_evidence_contract(goal, history, intrinsic_context=intrinsic_context)

    native_tool_names = _tool_surface_names_for_turn(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
    )

    def build_payload_for_native_tool_names(tool_names: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        schema = (
            _native_tools_schema_for_planner(TOOLS_SCHEMA, tool_names)
            if AGENTIC_PLANNER_NATIVE_TOOLS
            else []
        )
        manifest = _filter_tool_manifest_for_names(all_tool_manifest, tool_names)
        payload, budget = _build_planner_user_payload(
            job_id=job_id,
            state=state,
            step=step,
            history=history,
            tool_manifest=manifest,
            evidence_contract=evidence_contract,
            planner_memory=planner_memory,
            intrinsic_context=intrinsic_context,
            last_tool_result=last_tool_result if isinstance(last_tool_result, dict) else {},
            native_tools_schema=schema,
        )
        return payload, budget, schema

    user_payload, prompt_budget, native_tools_schema = build_payload_for_native_tool_names(
        native_tool_names
    )
    prompt_context_continuation_required = _prompt_context_continuation_from_payload(user_payload)
    refined_native_tool_names = _tool_surface_names_for_turn(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
        prompt_context_continuation_required=prompt_context_continuation_required,
    )
    if AGENTIC_PLANNER_NATIVE_TOOLS and refined_native_tool_names != native_tool_names:
        native_tool_names = refined_native_tool_names
        user_payload, prompt_budget, native_tools_schema = build_payload_for_native_tool_names(
            native_tool_names
        )
        prompt_context_continuation_required = _prompt_context_continuation_from_payload(user_payload)

    required_errors = prompt_budget.get("required_working_set_errors") if isinstance(prompt_budget, dict) else []
    if isinstance(prompt_budget, dict):
        native_history_reserve_chars_for_budget = (
            int(prompt_budget.get("native_history_reserve_chars") or 0)
            if AGENTIC_PLANNER_NATIVE_TOOLS
            else 0
        )
        total_prompt_chars_for_budget = int(prompt_budget.get("total_prompt_chars") or 0)
        total_without_native_history_reserve = max(
            0,
            total_prompt_chars_for_budget - native_history_reserve_chars_for_budget,
        )
        generation_headroom_char_budget = int(
            prompt_budget.get("generation_headroom_char_budget")
            or _prompt_generation_headroom_char_budget()
            or 0
        )
        prompt_budget["native_history_reserve_is_synthetic"] = bool(native_history_reserve_chars_for_budget)
        prompt_budget["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
        prompt_budget["over_budget_without_native_history_reserve"] = bool(
            AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
            and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        )
        prompt_budget["over_generation_headroom_without_native_history_reserve"] = bool(
            generation_headroom_char_budget > 0
            and total_without_native_history_reserve > generation_headroom_char_budget
        )
    hard_required_errors = [
        err for err in (required_errors or [])
        if isinstance(err, dict) and err.get("error") in {
            "repo_read_full_content_window_unavailable",
            "repo_read_full_content_missing_in_required_working_set",
        }
    ]
    effective_prompt_over_budget = (
        bool(prompt_budget.get("over_generation_headroom_budget")) if isinstance(prompt_budget, dict) else False
    )
    if (
        isinstance(prompt_budget, dict)
        and AGENTIC_PLANNER_NATIVE_TOOLS
        and int(prompt_budget.get("native_history_reserve_chars") or 0) > 0
    ):
        effective_prompt_over_budget = bool(
            prompt_budget.get("over_generation_headroom_without_native_history_reserve")
        )
    if (
        isinstance(prompt_budget, dict)
        and effective_prompt_over_budget
        and int(prompt_budget.get("generation_headroom_char_budget") or 0) > 0
    ):
        hard_required_errors.append(
            {
                "error": "planner_prompt_no_generation_headroom",
                "total_prompt_chars": prompt_budget.get("total_prompt_chars"),
                "total_prompt_chars_without_native_history_reserve": prompt_budget.get("total_prompt_chars_without_native_history_reserve"),
                "prompt_char_budget": prompt_budget.get("char_budget"),
                "generation_headroom_char_budget": prompt_budget.get("generation_headroom_char_budget"),
                "generation_headroom_reserve_chars": prompt_budget.get("generation_headroom_reserve_chars"),
                "native_history_reserve_chars": prompt_budget.get("native_history_reserve_chars"),
                "required_working_set_chars": prompt_budget.get("required_working_set_chars"),
            }
        )
    if hard_required_errors:
        headroom_block = any(
            isinstance(err, dict) and err.get("error") == "planner_prompt_no_generation_headroom"
            for err in hard_required_errors
        )
        return {
            "action": "block",
            "reason": (
                "planner_prompt_no_generation_headroom"
                if headroom_block
                else "planner_prompt_required_working_set_invalid"
            ),
            "blocked_by": (
                "planner_prompt_no_generation_headroom"
                if headroom_block
                else "planner_prompt_required_payload_not_complete"
            ),
            "final_answer": (
                (
                    "Planner prompt construction refused to call 11434 without generation headroom. "
                    if headroom_block
                    else "Planner prompt construction refused to send truncated required payload. "
                )
                + f"Errors: {json.dumps(hard_required_errors, ensure_ascii=False, default=str)}"
            ),
            "prompt_budget_report": prompt_budget,
        }
    planner_system_prompt = _planner_system_for_current_mode()
    history_messages: list[dict[str, Any]] = []
    history_messages_report: dict[str, Any] = {
        "schema": "planner_history_messages.v1",
        "enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
        "message_count": 0,
        "message_chars": 0,
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        native_history_reserve_chars = int(prompt_budget.get("native_history_reserve_chars") or 0)
        prompt_chars_without_history_messages = max(
            0,
            int(prompt_budget.get("total_prompt_chars") or 0) - native_history_reserve_chars,
        )
        generation_headroom_char_budget = int(prompt_budget.get("generation_headroom_char_budget") or 0)
        if generation_headroom_char_budget > 0:
            history_message_budget = max(
                0,
                generation_headroom_char_budget - prompt_chars_without_history_messages,
            )
        else:
            history_message_budget = max(0, AGENTIC_PLANNER_NUM_CTX * 2)
        history_messages, history_messages_report = _planner_history_messages_for_ollama(
            history,
            root=agent_job_root(job_id),
            goal=goal,
            window_chars=_prompt_window_chars(True, 0),
            max_chars=history_message_budget,
        )
        prompt_budget["history_messages"] = history_messages_report
        prompt_budget["history_messages_chars"] = history_messages_report.get("message_chars", 0)
        prompt_budget["native_history_reserve_chars"] = native_history_reserve_chars
        prompt_budget["history_message_budget"] = history_message_budget
        prompt_budget["total_prompt_chars_with_history_messages"] = (
            prompt_chars_without_history_messages + int(history_messages_report.get("message_chars") or 0)
        )
        if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0:
            prompt_budget["over_budget_with_history_messages"] = (
                int(prompt_budget["total_prompt_chars_with_history_messages"])
                > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
            )
        if generation_headroom_char_budget > 0:
            prompt_budget["over_generation_headroom_with_history_messages"] = (
                int(prompt_budget["total_prompt_chars_with_history_messages"])
                > generation_headroom_char_budget
            )
            if prompt_budget["over_generation_headroom_with_history_messages"]:
                return {
                    "action": "block",
                    "reason": "planner_prompt_no_generation_headroom",
                    "blocked_by": "planner_prompt_no_generation_headroom",
                    "final_answer": (
                        "Planner prompt construction refused to call 11434 without generation headroom "
                        "after native history transport. "
                        f"total_prompt_chars_with_history_messages={prompt_budget['total_prompt_chars_with_history_messages']} "
                        f"generation_headroom_char_budget={generation_headroom_char_budget}."
                    ),
                    "prompt_budget_report": prompt_budget,
                }
        transportable_history_items = sum(
            1
            for item in (history if isinstance(history, list) else [])
            if _history_tool_result(item)
        )
        if (
            transportable_history_items > 0
            and int(history_messages_report.get("included_history_items") or 0) == 0
            and not prompt_context_continuation_required
        ):
            return {
                "action": "block",
                "reason": "planner_history_messages_budget_unavailable",
                "blocked_by": "planner_history_messages_not_transported",
                "final_answer": (
                    "Native tool mode requires prior tool history/results to be transported "
                    "through Ollama messages. The prompt budget left no room for any full "
                    "SQLite-windowed history message, so the planner was not called with "
                    "lost operational state."
                ),
                "prompt_budget_report": prompt_budget,
            }
    planner_payload = {
        "model": PLANNER_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "messages": [
            {"role": "system", "content": planner_system_prompt},
            *history_messages,
            {"role": "user",
             "content": json.dumps(user_payload, ensure_ascii=False, indent=2, default=str)},
        ],
        "options": {
            "temperature": AGENTIC_PLANNER_TEMPERATURE,
            "num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
        },
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        planner_payload["tools"] = native_tools_schema
    else:
        planner_payload["format"] = "json"

    prompt_capture: dict[str, Any] = {
        "ok": False,
        "schema": "planner_payload_capture.v1",
    }
    try:
        prompt_payload_path = agent_job_root(job_id) / "planner-prompts" / f"step-{int(step):03d}-planner-payload.json"
        write_json(
            prompt_payload_path,
            {
                "schema": "planner_payload_capture.v1",
                "job_id": job_id,
                "step": step,
                "planner_url": PLANNER_URL,
                "planner_model": PLANNER_MODEL,
                "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                "prompt_budget_report": prompt_budget,
                "user_payload": user_payload,
                "planner_payload": planner_payload,
            },
        )
        prompt_capture.update({
            "ok": True,
            "path": str(prompt_payload_path),
        })
    except Exception as exc:  # pragma: no cover - capture is diagnostic, not planner fallback
        prompt_capture.update({
            "ok": False,
            "error": "planner_payload_capture_failed",
            "error_type": type(exc).__name__,
            "details": str(exc)[:1000],
        })

    append_agent_event(
        job_id, "planner_request_started",
        f"Planner request step={step} timeout={AGENTIC_PLANNER_STEP_TIMEOUT}s.",
        {
            "planner_url": PLANNER_URL,
            "planner_model": PLANNER_MODEL,
            "num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
            "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
            "intrinsic_context_schema": intrinsic_context.get("schema"),
            "intrinsic_context_chars": (intrinsic_context.get("budget_report") or {}).get("intrinsic_context_chars"),
            "intrinsic_rag_status": (intrinsic_context.get("retrieved_rag_chunks") or {}).get("status"),
            "intrinsic_rag_rerank_status": ((intrinsic_context.get("retrieved_rag_chunks") or {}).get("rerank") or {}).get("status"),
            "prompt_char_budget": prompt_budget.get("char_budget") if isinstance(prompt_budget, dict) else None,
            "generation_headroom_char_budget": prompt_budget.get("generation_headroom_char_budget") if isinstance(prompt_budget, dict) else None,
            "generation_headroom_reserve_chars": prompt_budget.get("generation_headroom_reserve_chars") if isinstance(prompt_budget, dict) else None,
            "prompt_payload_chars": prompt_budget.get("total_user_payload_chars") if isinstance(prompt_budget, dict) else None,
            "prompt_over_budget": prompt_budget.get("over_budget") if isinstance(prompt_budget, dict) else None,
            "prompt_over_generation_headroom_budget": prompt_budget.get("over_generation_headroom_budget") if isinstance(prompt_budget, dict) else None,
            "required_working_set_chars": prompt_budget.get("required_working_set_chars") if isinstance(prompt_budget, dict) else None,
            "tool_surface_names": native_tool_names,
            "native_tool_surface_names": native_tool_names if AGENTIC_PLANNER_NATIVE_TOOLS else [],
            "planner_payload_capture": prompt_capture,
        },
        step=step,
    )

    stream_path = agent_job_planner_stream_path(job_id, step)
    response = post_json_stream_to_file(
        PLANNER_URL, planner_payload,
        timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
        job_id=job_id, step=step, stream_path=stream_path,
    )
    native_calls = response.get("native_tool_calls") if isinstance(response.get("native_tool_calls"), list) else []
    stream_meta = {
        key: response.get(key)
        for key in (
            "ollama_done_seen",
            "ollama_done_reason",
            "ollama_load_duration",
            "ollama_total_duration",
            "ollama_eval_count",
            "ollama_prompt_eval_count",
        )
        if response.get(key) not in (None, "", [], {})
    }
    if native_calls:
        decision = _native_tool_calls_decision(native_calls, str(response.get("response") or ""))
        if decision:
            decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
            decision["native_tool_calls_seen"] = len(native_calls)
            decision["allowed_tool_names"] = list(native_tool_names)
            decision["allowed_native_tool_names"] = list(native_tool_names)
            if prompt_context_continuation_required:
                decision["prompt_context_continuation_required"] = prompt_context_continuation_required
            if stream_meta:
                decision["planner_stream_meta"] = stream_meta
            return decision
    if AGENTIC_PLANNER_NATIVE_TOOLS and not native_calls:
        raw_text_for_native_mode = str(response.get("response") or response.get("partial_content") or "")
        decoded_text_decision = _parse_strict_json_object(raw_text_for_native_mode)
        if isinstance(decoded_text_decision, dict):
            action = str(decoded_text_decision.get("action") or "").strip().lower()
            if action in {"final", "done", "complete", "completed", "block", "blocked", "need_user", "needs_user"}:
                decision = _normalize_terminal_planner_decision(decoded_text_decision)
                decision.setdefault("raw_planner_text_preview", raw_text_for_native_mode[:2000])
                decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
                decision["native_tool_calls_seen"] = 0
                decision["native_tool_text_decision_allowed"] = action
                decision["allowed_tool_names"] = list(native_tool_names)
                if prompt_context_continuation_required:
                    decision["prompt_context_continuation_required"] = prompt_context_continuation_required
                if stream_meta:
                    decision["planner_stream_meta"] = stream_meta
                return decision
        prompt_eval_count = 0
        try:
            prompt_eval_count = int(response.get("ollama_prompt_eval_count") or 0)
        except Exception:
            prompt_eval_count = 0
        token_reserve = _planner_token_generation_reserve(AGENTIC_PLANNER_NUM_CTX)
        token_headroom_low = bool(
            AGENTIC_PLANNER_NUM_CTX > 0
            and prompt_eval_count > 0
            and token_reserve > 0
            and prompt_eval_count >= max(0, AGENTIC_PLANNER_NUM_CTX - token_reserve)
        )
        prompt_over_headroom_for_native = (
            bool(prompt_budget.get("over_generation_headroom_budget"))
            if isinstance(prompt_budget, dict)
            else False
        )
        if (
            isinstance(prompt_budget, dict)
            and AGENTIC_PLANNER_NATIVE_TOOLS
            and int(prompt_budget.get("native_history_reserve_chars") or 0) > 0
        ):
            prompt_over_headroom_for_native = bool(
                prompt_budget.get("over_generation_headroom_without_native_history_reserve")
            )
        if (
            (AGENTIC_PLANNER_NUM_CTX > 0 and prompt_eval_count >= AGENTIC_PLANNER_NUM_CTX)
            or token_headroom_low
            or prompt_over_headroom_for_native
            or (
                isinstance(prompt_budget, dict)
                and bool(prompt_budget.get("over_generation_headroom_with_history_messages"))
            )
        ):
            return {
                "action": "block",
                "reason": "planner_prompt_no_generation_headroom",
                "blocked_by": "planner_prompt_no_generation_headroom",
                "final_answer": (
                    "Planner native tool mode returned no tool call, but the prompt had no "
                    "safe generation headroom. This is a controller prompt-pack issue, not "
                    "a native tool-call violation."
                ),
                "raw_planner_text": raw_text_for_native_mode[:12000],
                "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
                "native_tool_calls_seen": 0,
                "controller_synthesized_protocol_block": True,
                "prompt_budget_report": prompt_budget,
                "prompt_token_headroom": {
                    "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                    "ollama_prompt_eval_count": prompt_eval_count,
                    "generation_token_reserve": token_reserve,
                    "headroom_tokens": (
                        AGENTIC_PLANNER_NUM_CTX - prompt_eval_count
                        if AGENTIC_PLANNER_NUM_CTX > 0 and prompt_eval_count > 0
                        else None
                    ),
                    "classification": (
                        "planner_prompt_token_headroom_low"
                        if token_headroom_low
                        else "planner_prompt_no_generation_headroom"
                    ),
                },
                **({"planner_stream_meta": stream_meta} if stream_meta else {}),
            }
        if not native_tools_schema:
            return {
                "action": "block",
                "reason": "planner_final_required_empty_output",
                "final_answer": (
                    "Planner had no native tools in this turn because the evidence contract "
                    "required a final answer, but Ollama returned neither a strict final JSON "
                    "object nor usable text."
                ),
                "raw_planner_text": raw_text_for_native_mode[:12000],
                "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
                "native_tool_calls_seen": 0,
                "controller_synthesized_protocol_block": True,
                "prompt_budget_report": prompt_budget,
                **({"planner_stream_meta": stream_meta} if stream_meta else {}),
            }
        return {
            "action": "block",
            "reason": "planner_native_tool_call_required",
            "final_answer": (
                "Planner native tool mode is required for tool execution, but Ollama "
                "did not return message.tool_calls. JSON-text tool fallback was not used."
            ),
            "raw_planner_text": raw_text_for_native_mode[:12000],
            "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
            "native_tool_calls_seen": 0,
            "controller_synthesized_protocol_block": True,
            **({"planner_stream_meta": stream_meta} if stream_meta else {}),
        }

    # --- degenerate output ---
    if response.get("planner_degenerate_output"):
        partial = str(response.get("partial_content") or "")
        return {
            "action": "block",
            "reason": f"PLANNER_DEGENERATE_OUTPUT_NON_JSON:{response.get('error')}",
            "final_answer": (
                "Planner 30B produced degenerate output. No partial JSON extraction, "
                "plaintext recovery, or controller fallback normalization was executed. "
                "Plain text output must be retried by the planner; malformed JSON or "
                "recognizable invalid tool calls remain eligible for Vulkan/GPU0 11435 repair. "
                f"Partial stream chars={len(partial)}. Stream artifact={stream_path}."
            ),
            "raw_planner_text": partial[:12000],
        }

    # --- timeout: surface, do not force a fallback decision ---
    if response.get("backend_timeout"):
        append_agent_event(
            job_id,
            "planner_timeout",
            f"Timeout after {AGENTIC_PLANNER_STEP_TIMEOUT}s; no forced retry/fallback.",
            {
                "error": response.get("error"),
                "partial_content_chars": len(str(response.get("partial_content") or "")),
                "stream_path": str(stream_path),
            },
            step=step,
        )
        partial = str(response.get("partial_content") or "")
        return {
            "action": "block",
            "reason": "planner_timeout_non_json_output",
            "final_answer": (
                "Planner 30B timed out. No forced retry or controller fallback was executed. "
                "Plain text partial output must be retried by the planner, not repaired by GPU0. "
                f"Partial stream chars={len(partial)}. Stream artifact={stream_path}."
            ),
            "raw_planner_text": partial[:12000],
        }

    if response.get("backend_unreachable") or response.get("backend_timeout"):
        return {
            "action": "block",
            "reason": "planner backend error",
            "final_answer": f"Planner 30B non raggiungibile: {response.get('error')}.",
        }

    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    raw_text = str(message.get("content") or response.get("response") or "")

    if planner_done_token(raw_text):
        if goal_requires_code_product_report(goal) and not successful_code_edit_proposals(history):
            return {
                "action": "block",
                "reason": "planner done token without required code product candidate",
                "final_answer": (
                    "Il planner ha emesso un token di completamento senza JSON, "
                    "ma il goal richiedeva un code product/diff e manca repo_propose_code_edit."
                ),
            }
        if goal_has_write_intent(goal) and not history_has_tool(history, "repo_apply_patch"):
            return {
                "action": "block",
                "reason": "planner done token without applying requested patch",
                "final_answer": (
                    "Il planner ha emesso un token di completamento senza JSON, "
                    "ma il goal richiedeva una patch non eseguita."
                ),
            }
        return {
            "action": "final",
            "final_answer": (
                f"Il planner ha emesso un token di completamento ({raw_text.strip()!r}). "
                "3572 ha chiuso il job usando la history degli artifact."
            ),
            "history_artifacts": summarize_history_artifacts(history),
        }

    decision = normalize_planner_decision(raw_text, goal, step, state)
    decision.setdefault("raw_planner_text_preview", raw_text[:2000])
    decision["allowed_tool_names"] = list(native_tool_names)
    if prompt_context_continuation_required:
        decision["prompt_context_continuation_required"] = prompt_context_continuation_required
    if stream_meta:
        decision["planner_stream_meta"] = stream_meta
    return decision


# ---------------------------------------------------------------------------
# Full agentic loop
# ---------------------------------------------------------------------------


def _compact_final_state_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    compact_result: dict[str, Any] = {}
    for key in (
        "auto_finalized_by", "blocked_by", "rejected_tool", "blocked_tool",
        "error", "error_type",
    ):
        if result.get(key) not in (None, "", [], {}):
            compact_result[key] = result.get(key)
    history = result.get("history")
    if isinstance(history, list):
        compact_result["history_count"] = len(history)
        compact_result["history_tail"] = planner_history_ledger(history[-8:])
        diagnostics = result.get("agent_flow_diagnostics") if isinstance(result.get("agent_flow_diagnostics"), dict) else {}
        if diagnostics:
            compact_result["agent_flow_diagnostics"] = diagnostics
    decision = result.get("planner_decision")
    if isinstance(decision, dict):
        compact_result["planner_decision"] = {
            k: decision.get(k)
            for k in ("action", "tool", "reason", "selected_by_3572", "coerced_by_3572")
            if decision.get(k) not in (None, "", [], {})
        }
    return compact_result


_PUBLIC_TERMINAL_POINTER_KEYS = {
    "artifact_path",
    "producer_artifact",
    "final_path",
    "events_path",
    "db",
    "db_path",
    "sqlite_path",
    "document_id",
    "evidence_contract",
    "raw_planner_text_preview",
    "raw_planner_text",
    "raw_text",
}


def _public_terminal_content_key(key: Any) -> bool:
    return str(key or "").lower() in {
        "content",
        "content_view",
        "unified_diff",
        "structured_operations",
        "old_text",
        "new_text",
        "stdout",
        "stderr",
        "stdout_tail",
        "stderr_tail",
        "text",
    }


def _public_terminal_sanitize_text(value: Any, *, content: bool = False) -> str:
    text = str(value or "")
    if not text:
        return ""
    if content:
        return text
    text = re.sub(r"\s+(?:backup_)?artifact=[^\s,}\]]+", "", text)
    text = re.sub(r'"(?:artifact|artifact_path|producer_artifact|document_id|db|db_path|sqlite_path)"\s*:\s*"[^"]*",?', "", text)
    text = re.sub(r"[A-Za-z]:\\[^\s,}\]]+", "[local_path_omitted]", text)
    text = re.sub(r"https?://(?:127\.0\.0\.1|localhost)[^\s,}\]]*", "[local_url_omitted]", text, flags=re.I)
    text = re.sub(r"\bqwen-agent-workspace[^\s,}\]]*", "[job_workspace_path_omitted]", text)
    text = re.sub(r"\bagent-jobs[^\s,}\]]*", "[job_path_omitted]", text)
    text = re.sub(r"\btool-results\\[^\s,}\]]*", "[tool_result_path_omitted]", text)
    text = re.sub(r"\S+\.sqlite\b", "[sqlite_path_omitted]", text, flags=re.I)
    return text


def _public_terminal_sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 12:
        return {}
    key_text = str(key or "")
    if key_text.lower() in _PUBLIC_TERMINAL_POINTER_KEYS:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for child_key, child_value in value.items():
            cleaned = _public_terminal_sanitize_value(child_value, key=str(child_key), depth=depth + 1)
            if cleaned not in (None, "", [], {}):
                out[str(child_key)] = cleaned
        return out
    if isinstance(value, list):
        out_list: list[Any] = []
        for item in value:
            cleaned = _public_terminal_sanitize_value(item, key=key_text, depth=depth + 1)
            if cleaned not in (None, "", [], {}):
                out_list.append(cleaned)
        return out_list
    if isinstance(value, str):
        return _public_terminal_sanitize_text(
            value,
            content=_public_terminal_content_key(key_text),
        )
    return value


def _public_terminal_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []

    def public_summary(value: Any) -> str:
        text = _prompt_clip_text(value, 1200)
        return _public_terminal_sanitize_text(text)

    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = _history_tool_result(item)
        tool = str(result.get("tool") or decision.get("tool") or "").strip()
        row: dict[str, Any] = {
            "step": item.get("step"),
            "action": decision.get("action"),
            "tool": tool or None,
            "ok": result.get("ok"),
            "reason": _prompt_clip_text(decision.get("reason"), 700),
            "arguments": _public_terminal_sanitize_value(
                decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {},
            ),
            "path": result.get("path"),
            "count": result.get("count"),
            "total_matches": result.get("total_matches"),
            "items_total": result.get("items_total"),
            "paths_total": result.get("paths_total"),
            "returncode": result.get("returncode"),
            "guard_type": result.get("guard_type"),
            "violations": result.get("violations"),
            "summary": public_summary(result.get("summary")),
        }
        if tool == "repo_read" and isinstance(result.get("items"), list):
            read_items = []
            for sub in result["items"][:80]:
                if not isinstance(sub, dict):
                    continue
                content, _meta = _repo_read_item_full_content(sub)
                read_items.append({
                    "ok": sub.get("ok"),
                    "path": sub.get("path"),
                    "line_count": sub.get("line_count"),
                    "truncated": sub.get("truncated"),
                    "content_chars": len(content) if content else None,
                    "content_sha256": _text_hash(content) if content else None,
                    "error": sub.get("error"),
                })
            row["items"] = read_items
        elif tool == "repo_propose_code_edit":
            for key in (
                "kind", "target_file", "edit_kind", "rationale",
                "source_writes_performed", "patch_application_performed",
                "manual_review_required", "validation_commands",
                "unified_diff", "structured_operations", "errors", "warnings",
                "target_metadata", "ast_evidence",
            ):
                if result.get(key) not in (None, "", [], {}):
                    row[key] = result.get(key)
        elif tool == "planner_scratchpad_read" and str(result.get("mode") or "") == "prompt_context_window":
            row["mode"] = result.get("mode")
            if isinstance(result.get("items"), list):
                row["items"] = [
                    _public_terminal_sanitize_value(_compact_prompt_context_window_item(sub))
                    for sub in result["items"][:80]
                    if isinstance(sub, dict)
                ]
        ledger.append({
            k: v
            for k, v in _public_terminal_sanitize_value(row).items()
            if v not in (None, "", [], {})
        })
    return ledger


def _public_terminal_result_for_30b(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    public = dict(result)
    history = result.get("history")
    if isinstance(history, list):
        public["history_count"] = len(history)
        public["history"] = _public_terminal_history_ledger(history)
        public["history_schema"] = "agentic_terminal_public_history_ledger.v1"
        public["raw_history_not_inlined"] = True
    memory_write = public.get("controller_memory_write")
    if isinstance(memory_write, dict):
        public["controller_memory_write"] = {
            k: memory_write.get(k)
            for k in ("ok", "tool", "kind", "tag", "record_id", "chars", "sha256", "target_key")
            if memory_write.get(k) not in (None, "", [], {})
        }
    for key in ("validation", "planner_decision"):
        section = public.get(key)
        if isinstance(section, dict):
            for drop_key in ("evidence_contract", "raw_planner_text_preview", "raw_planner_text", "raw_text"):
                section.pop(drop_key, None)
    return _public_terminal_sanitize_value(public) or {}


def _terminal_context_alias() -> dict[str, Any]:
    return {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }



def _planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if not decision:
            continue
        rows.append({
            k: v for k, v in {
                "step": item.get("step"),
                "action": decision.get("action"),
                "tool": decision.get("tool"),
                "arguments": decision.get("arguments"),
                "reason": decision.get("reason"),
            }.items() if v not in (None, "", [], {})
        })
    return rows


def _validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") != "controller_guard":
            continue
        if result.get("guard_type") != "planner_decision_validation":
            continue
        rows.append({
            k: v for k, v in {
                "step": item.get("step"),
                "violations": result.get("violations"),
                "rejected_decision": result.get("rejected_decision"),
                "evidence_contract": result.get("evidence_contract"),
                "summary": result.get("summary"),
            }.items() if v not in (None, "", [], {})
        })
    return rows


def _executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = result.get("tool")
        if not tool or tool == "controller_guard":
            continue
        rows.append({
            k: v for k, v in {
                "step": item.get("step"),
                "tool": tool,
                "ok": result.get("ok"),
                "path": result.get("path"),
                "count": result.get("count"),
                "total_matches": result.get("total_matches"),
                "items_total": result.get("items_total"),
                "paths_total": result.get("paths_total"),
            }.items() if v not in (None, "", [], {})
        })
    return rows


def _repo_read_content_views(
    history: list[dict[str, Any]],
    *,
    per_item_limit: int = 60000,
    total_limit: int = 180000,
) -> list[dict[str, Any]]:
    """Load concrete repo_read content views from tool-result artifacts.

    The compact planner history carries bounded summaries; OpenWebUI follow-up
    work needs the actual read content. This function reloads the recorded
    repo_read artifact when available and returns content views tied to path and
    artifact.
    """
    views: list[dict[str, Any]] = []
    used = 0
    seen: set[tuple[str, str]] = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") != "repo_read":
            continue
        artifact = str(result.get("artifact") or "")
        source_result = result
        if artifact:
            try:
                artifact_path = Path(artifact)
                if artifact_path.exists() and artifact_path.is_file():
                    loaded = json.loads(artifact_path.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(loaded, dict):
                        source_result = loaded
            except Exception:
                source_result = result
        for read_item in source_result.get("items") or []:
            if not isinstance(read_item, dict) or not read_item.get("ok") or not read_item.get("path"):
                continue
            path = str(read_item.get("path"))
            content, _content_meta = _repo_read_item_full_content(read_item)
            if not content:
                content = str(
                    read_item.get("content")
                    or read_item.get("content_view")
                    or read_item.get("content_preview")
                    or ""
                )
            if not content:
                continue
            key = (path, artifact)
            if key in seen:
                continue
            seen.add(key)
            remaining = max(0, total_limit - used)
            if remaining <= 0:
                break
            item_limit = max(1, min(per_item_limit, remaining))
            content_view = content[:item_limit]
            used += len(content_view)
            views.append({
                "path": path,
                "line_count": read_item.get("line_count"),
                "tool_truncated": bool(read_item.get("truncated")),
                "content_chars": len(content),
                "content_view_chars": len(content_view),
                "content_view_truncated_by_wrapper": len(content_view) < len(content),
                "content_view": content_view,
            })
        if used >= total_limit:
            break
    return views


def _execution_evidence_digest_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    """Human-visible evidence from the actual executed loop.

    This is deliberately not a replacement final written by the controller.  It
    exposes the concrete tool outputs that led to the planner final so
    OpenWebUI can continue with file edits or follow-up questions without
    seeing only a shallow one-paragraph final.
    """
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    if not history:
        return ""
    reads: list[str] = []
    lists: list[str] = []
    content_views = _repo_read_content_views(history)
    guards: list[str] = []
    repairs: list[str] = []
    raw_outputs: list[str] = []
    read_notes: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = str(tool_result.get("tool") or decision.get("tool") or "")
        if tool == "repo_read":
            paths: list[str] = []
            for read_item in tool_result.get("items") or []:
                if isinstance(read_item, dict) and read_item.get("ok") and read_item.get("path"):
                    path = str(read_item.get("path"))
                    paths.append(path)
                    content = str(read_item.get("content") or read_item.get("content_preview") or "")
                    key_lines = _extract_key_lines(content)
                    note = key_lines[0] if key_lines else ""
                    if note:
                        note = note[:180].replace("\n", " ")
                        row = f"{path}: {note}"
                        if row not in read_notes:
                            read_notes.append(row)
            if not paths and tool_result.get("path"):
                paths.append(str(tool_result.get("path")))
            for path in paths:
                if path not in reads:
                    reads.append(path)
        elif tool in {"repo_tree", "repo_list_files"}:
            path = tool_result.get("path")
            if path not in (None, ""):
                total = tool_result.get("total_matches") or tool_result.get("entries_total") or tool_result.get("count")
                truncated = tool_result.get("truncated")
                label = f"{tool}:{path}"
                if total not in (None, ""):
                    label += f" total={total}"
                if truncated:
                    label += " truncated=true"
                if label not in lists:
                    lists.append(label)
        elif tool == "controller_guard":
            summary = str(tool_result.get("summary") or "")
            if summary and summary not in guards:
                guards.append(summary)
            guard_raw = str(tool_result.get("raw_planner_text_preview") or "")
            if guard_raw:
                compact_raw = re.sub(r"\s+", " ", guard_raw).strip()[:500]
                if compact_raw and compact_raw not in raw_outputs:
                    raw_outputs.append(compact_raw)
            repair = tool_result.get("vulkan_repair") if isinstance(tool_result.get("vulkan_repair"), dict) else {}
            if repair:
                repair_label = "ok=" + str(repair.get("ok"))
                if repair.get("error"):
                    repair_label += " error=" + str(repair.get("error"))[:160]
                if repair_label not in repairs:
                    repairs.append(repair_label)
                raw_preview = str(repair.get("raw_planner_text_preview") or "")
                if raw_preview:
                    compact_raw = re.sub(r"\s+", " ", raw_preview).strip()[:500]
                    if compact_raw and compact_raw not in raw_outputs:
                        raw_outputs.append(compact_raw)
        elif decision.get("raw_planner_text_before_deterministic_strip"):
            raw_preview = str(decision.get("raw_planner_text_before_deterministic_strip") or "")
            compact_raw = re.sub(r"\s+", " ", raw_preview).strip()[:500]
            if compact_raw and compact_raw not in raw_outputs:
                raw_outputs.append(compact_raw)
    parts = [
        "OpenWebUI follow-up evidence from executed tools:",
        f"- agentic_steps_recorded={len(history)}",
    ]
    if lists:
        parts.append("- list/tree evidence: " + "; ".join(lists[:8]))
    if reads:
        shown = reads[:32]
        suffix = f" (+{len(reads) - len(shown)} more)" if len(reads) > len(shown) else ""
        parts.append("- successful repo_read paths: " + ", ".join(shown) + suffix)
    if read_notes:
        parts.append("- concrete content evidence:")
        for note in read_notes[:10]:
            parts.append("  - " + note)
    if content_views:
        parts.append("- repo_read content_view:")
        for view in content_views:
            meta = (
                f"path={view.get('path')} lines={view.get('line_count')} "
                f"chars={view.get('content_chars')}"
            )
            if view.get("tool_truncated"):
                meta += " tool_truncated=true"
            if view.get("content_view_truncated_by_wrapper"):
                meta += " content_view_truncated_by_wrapper=true"
            parts.append("  - " + meta)
            parts.append("````text")
            parts.append(str(view.get("content_view") or ""))
            parts.append("````")
    if guards:
        parts.append("- controller_guard events: " + "; ".join(guards[:5]))
    if repairs:
        parts.append("- Vulkan/GPU0 repair events: " + "; ".join(repairs[:5]))
    if raw_outputs:
        parts.append("- raw planner output surfaced:")
        for raw in raw_outputs[:3]:
            parts.append("  - " + raw)
    text = "\n".join(parts)
    return text[:limit] if int(limit or 0) > 0 else text


def _latest_code_product_payload(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history if isinstance(history, list) else []):
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        if (
            isinstance(result, dict)
            and result.get("tool") == "repo_propose_code_edit"
            and result.get("ok") is True
            and result.get("kind") == "code_edit_proposal"
        ):
            return result
    return {}


def _code_product_answer_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    proposal = _latest_code_product_payload(history)
    if not proposal:
        return ""
    target = str(proposal.get("target_file") or "")
    edit_kind = str(proposal.get("edit_kind") or "")
    lines = [
        "Code edit proposal generated.",
        f"- target_file: {target}",
        f"- edit_kind: {edit_kind}",
        f"- source_writes_performed: {str(proposal.get('source_writes_performed')).lower()}",
        f"- patch_application_performed: {str(proposal.get('patch_application_performed')).lower()}",
        f"- manual_review_required: {str(proposal.get('manual_review_required')).lower()}",
    ]
    rationale = str(proposal.get("rationale") or "").strip()
    if rationale:
        lines.append(f"- rationale: {rationale}")
    validation_commands = proposal.get("validation_commands")
    if isinstance(validation_commands, list) and validation_commands:
        lines.append("- validation_commands:")
        for command in validation_commands:
            lines.append(f"  - {command}")
    if edit_kind == "unified_diff":
        diff_text = str(proposal.get("unified_diff") or "")
        if not diff_text.strip():
            return ""
        lines.extend(["", "```diff", diff_text.rstrip("\n"), "```"])
    elif edit_kind == "structured_edit":
        operations = proposal.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            return ""
        lines.extend(["", "```json", json.dumps(operations, ensure_ascii=False, indent=2, default=str), "```"])
    elif edit_kind == "no_op":
        if not rationale:
            return ""
        lines.append("")
        lines.append("No patch content was produced because this proposal is an explicit no_op.")
    else:
        return ""
    text = "\n".join(lines)
    return text[:limit] if int(limit or 0) > 0 else text


def _partial_product_clean_text(value: Any, limit: int = 40000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:limit] if len(text) > limit else text


def _partial_products_for_30b(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(product: dict[str, Any]) -> None:
        if not isinstance(product, dict) or len(products) >= max(1, int(limit or 1)):
            return
        key = json.dumps(product, ensure_ascii=False, sort_keys=True, default=str)[:12000]
        if key in seen:
            return
        seen.add(key)
        products.append({k: v for k, v in product.items() if v not in (None, "", [], {})})

    for item in reversed(history if isinstance(history, list) else []):
        if len(products) >= max(1, int(limit or 1)):
            break
        if not isinstance(item, dict):
            continue
        step = item.get("step")
        result = _history_tool_result(item)
        rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
        rejected_tool = _normalize_tool_name(str(rejected.get("tool") or ""))
        rejected_args = rejected.get("arguments") if isinstance(rejected.get("arguments"), dict) else {}
        violations = result.get("violations") if isinstance(result.get("violations"), list) else []
        summary = str(result.get("summary") or "").strip()

        if rejected_tool == "repo_propose_code_edit":
            add({
                "kind": "partial_code_product_candidate",
                "source": "validator_rejected_repo_propose_code_edit",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": _repo_rel_token(rejected_args.get("target_file") or ""),
                "edit_kind": rejected_args.get("edit_kind"),
                "rationale": _partial_product_clean_text(rejected_args.get("rationale"), 8000),
                "unified_diff": _partial_product_clean_text(rejected_args.get("unified_diff"), 80000),
                "old_text": _partial_product_clean_text(rejected_args.get("old_text"), 30000),
                "new_text": _partial_product_clean_text(rejected_args.get("new_text"), 30000),
                "structured_operations": rejected_args.get("structured_operations") if isinstance(rejected_args.get("structured_operations"), list) else None,
                "reason": _partial_product_clean_text(rejected.get("reason"), 8000),
            })

        if rejected_tool == "planner_scratchpad_write" and str(rejected_args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
            state_text = _partial_product_clean_text(
                rejected_args.get("text") or rejected_args.get("content"),
                80000,
            )
            parsed = _code_product_build_state_parse(state_text)
            loose_payload: dict[str, Any] = {}
            if not parsed:
                try:
                    loose = json.loads(state_text)
                    if isinstance(loose, dict):
                        loose_payload = loose.get("payload") if isinstance(loose.get("payload"), dict) else loose
                except Exception:
                    loose_payload = {}
            add({
                "kind": "partial_code_product_build_state",
                "source": "validator_rejected_code_product_build_state",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": _repo_rel_token(
                    rejected_args.get("target_file")
                    or (parsed or loose_payload).get("target_file")
                    or ""
                ),
                "status": (parsed or loose_payload).get("status"),
                "edit_kind": (parsed or loose_payload).get("edit_kind"),
                "rationale": _partial_product_clean_text((parsed or loose_payload).get("rationale"), 8000),
                "state_text": state_text,
            })

        action_plan = _partial_product_clean_text(result.get("action_plan_candidate"), 40000)
        if action_plan:
            add({
                "kind": "action_plan_candidate",
                "source": "validator_rejected_final_for_code_product",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "text": action_plan,
            })

        repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
        if repair:
            repaired = repair.get("repaired_decision") if isinstance(repair.get("repaired_decision"), dict) else {}
            text = _partial_product_clean_text(
                repaired.get("final_answer")
                or repair.get("raw_text_preview")
                or repair.get("raw_planner_text_preview"),
                40000,
            )
            if text:
                add({
                    "kind": "repair_candidate_text",
                    "source": "vulkan_gpu0_repair_rejected_or_unvalidated",
                    "step": step,
                    "payload_is_complete": False,
                    "validator_accepted": False,
                    "rejection_summary": summary,
                    "violations": violations,
                    "text": text,
                    "repair_error": repair.get("error"),
                })
    return products


def _best_partial_product_for_30b(history: list[dict[str, Any]]) -> dict[str, Any]:
    products = _partial_products_for_30b(history, limit=8)
    for product in products:
        if str(product.get("unified_diff") or "").strip():
            return product
    return products[0] if products else {}


def _partial_product_answer_text(result: dict[str, Any] | None, limit: int = 60000) -> str:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    product = result.get("best_partial_product_for_30b") if isinstance(result.get("best_partial_product_for_30b"), dict) else {}
    if not product:
        product = _best_partial_product_for_30b(history)
    if not product:
        return ""
    lines = [
        "Prodotto parziale non validato dal controller.",
        f"- kind: {product.get('kind')}",
        f"- source: {product.get('source')}",
        f"- step: {product.get('step')}",
        f"- validator_accepted: {str(product.get('validator_accepted')).lower()}",
    ]
    if product.get("target_file"):
        lines.append(f"- target_file: {product.get('target_file')}")
    if product.get("edit_kind"):
        lines.append(f"- edit_kind: {product.get('edit_kind')}")
    if product.get("rejection_summary"):
        lines.append(f"- rejection_summary: {product.get('rejection_summary')}")
    rationale = str(product.get("rationale") or "").strip()
    if rationale:
        lines.append(f"- rationale: {rationale}")
    if str(product.get("unified_diff") or "").strip():
        lines.extend(["", "```diff", str(product.get("unified_diff")).rstrip("\n"), "```"])
    elif product.get("structured_operations"):
        lines.extend(["", "```json", json.dumps(product.get("structured_operations"), ensure_ascii=False, indent=2, default=str), "```"])
    elif str(product.get("text") or "").strip():
        lines.extend(["", str(product.get("text")).strip()])
    elif str(product.get("state_text") or "").strip():
        lines.extend(["", "```json", str(product.get("state_text")).strip(), "```"])
    text = "\n".join(lines)
    return text[:limit] if int(limit or 0) > 0 else text


def _agent_flow_diagnostics(
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact deterministic diagnostics for terminal artifacts."""
    history = history if isinstance(history, list) else []
    contract = planner_evidence_contract(goal, history)
    final_contract = contract.get("finalization_contract") if isinstance(contract, dict) else {}
    guard_counts: dict[str, int] = {}
    raw_previews: list[str] = []
    repeated_cache_keys: list[str] = []
    preseed_root_surface = False
    preseed_scope_surface = False
    preseed_file_surface = False
    deterministic_strip_count = 0
    native_tool_calls_seen = 0
    native_tool_call_validated = 0
    native_tool_call_repaired_by_gpu0 = 0
    native_tool_batch_executed = 0
    vulkan_repair_attempted = 0
    memory_tool_calls = 0
    scratchpad_entries = 0
    persistent_memory_records_written = 0
    persistent_memory_cleanup_dry_run = 0
    planner_memory_false_unavailable_claims = 0

    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if (
            result.get("tool") == "repo_tree"
            and result.get("ok")
            and bool(result.get("controller_preseed"))
            and str(result.get("path") or ".") in {"", "."}
        ):
            preseed_root_surface = True
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok") and result.get("preseed_reason") == "explicit_directory_request_needs_scope_surface":
            preseed_scope_surface = True
        if result.get("tool") == "repo_read" and result.get("ok") and result.get("preseed_reason") == "explicit_file_request_needs_file_surface":
            preseed_file_surface = True
        if decision.get("deterministic_strip"):
            deterministic_strip_count += 1
        if decision.get("native_tool_call"):
            native_tool_calls_seen += int(decision.get("native_tool_calls_seen") or 1)
            if result.get("ok") and result.get("tool") not in {None, "", "controller_guard"}:
                native_tool_call_validated += 1
        tool_name = str(result.get("tool") or decision.get("tool") or "")
        if tool_name in {
            "planner_scratchpad_read",
            "planner_scratchpad_write",
            "runtime_sqlite_memory_search",
            "runtime_sqlite_memory_write",
            "runtime_sqlite_memory_cleanup",
        }:
            memory_tool_calls += 1
        if tool_name == "planner_scratchpad_write" and result.get("ok"):
            scratchpad_entries += 1
        if tool_name == "runtime_sqlite_memory_write" and result.get("ok"):
            persistent_memory_records_written += 1
        if tool_name == "runtime_sqlite_memory_cleanup" and result.get("dry_run"):
            persistent_memory_cleanup_dry_run += 1
        raw = str(result.get("raw_planner_text_preview") or decision.get("raw_planner_text_before_deterministic_strip") or "")
        if raw.strip():
            compact_raw = re.sub(r"\s+", " ", raw).strip()[:700]
            if compact_raw and compact_raw not in raw_previews:
                raw_previews.append(compact_raw)
        if result.get("tool") == "controller_guard":
            guard_type = str(result.get("guard_type") or result.get("summary") or "unknown")
            guard_counts[guard_type] = guard_counts.get(guard_type, 0) + 1
            if guard_type == "planner_memory_false_unavailable_claim":
                planner_memory_false_unavailable_claims += 1
            cache_key = str(result.get("cache_key") or "")
            if cache_key and cache_key not in repeated_cache_keys:
                repeated_cache_keys.append(cache_key)
            repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
            if repair:
                vulkan_repair_attempted += 1
                if decision.get("native_tool_call") or (
                    isinstance(result.get("rejected_decision"), dict)
                    and result["rejected_decision"].get("native_tool_call")
                ):
                    native_tool_call_repaired_by_gpu0 += 1
        if isinstance(result.get("vulkan_repair"), dict):
            vulkan_repair_attempted += 1
        if decision.get("action") == "tool_batch":
            native_tool_batch_executed += 1

    return {
        "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
        "native_tool_calls_seen": native_tool_calls_seen,
        "native_tool_call_validated": native_tool_call_validated,
        "native_tool_call_repaired_by_gpu0": native_tool_call_repaired_by_gpu0,
        "native_tool_batch_executed": native_tool_batch_executed,
        "planner_retry_required_count": guard_counts.get("planner_retry_required", 0),
        "planner_retry_streak": _planner_incomprehensible_retry_count(history),
        "vulkan_repair_attempted": vulkan_repair_attempted > 0,
        "memory_tool_calls": memory_tool_calls,
        "scratchpad_entries": scratchpad_entries,
        "persistent_memory_records_written": persistent_memory_records_written,
        "persistent_memory_cleanup_dry_run": persistent_memory_cleanup_dry_run,
        "planner_memory_surface_available": bool(
            isinstance(planner_memory, dict) and planner_memory.get("available") is True
        ),
        "planner_memory_records_injected": int(
            planner_memory.get("record_count") or 0
        ) if isinstance(planner_memory, dict) else 0,
        "planner_memory_false_unavailable_claims": planner_memory_false_unavailable_claims,
        "preseed_root_surface": preseed_root_surface,
        "preseed_scope_surface": preseed_scope_surface,
        "preseed_file_surface": preseed_file_surface,
        "final_gate_blocker": final_contract.get("reason") if isinstance(final_contract, dict) else None,
        "final_allowed": bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False,
        "last_non_empty_raw_previews": raw_previews[-5:],
        "repeated_cache_keys": repeated_cache_keys[-10:],
        "guard_count": sum(guard_counts.values()),
        "guard_counts_by_type": guard_counts,
        "deterministic_strip_count": deterministic_strip_count,
    }



def answer_for_openwebui(status: str, final_summary: str, result: dict[str, Any] | None) -> str:
    """Top-level text the outer OpenWebUI model can use directly.

    The structured context remains available for evidence-bound continuation, but
    the public tool result must also expose one clear answer field.  Otherwise
    the outer model receives a nested contract and often treats it as opaque log
    data instead of an action/result to report to the user.
    """
    result = result if isinstance(result, dict) else {}
    summary = str(final_summary or "").strip() or "Job terminale senza final_summary."
    status_text = str(status or "unknown")
    if status_text == "completed":
        code_product_answer = _code_product_answer_text(result)
        if code_product_answer:
            evidence = _execution_evidence_digest_text(result)
            return code_product_answer if not evidence else code_product_answer + "\n\n" + evidence
        evidence = _execution_evidence_digest_text(result)
        return summary if not evidence else summary + "\n\n" + evidence
    if status_text == "blocked_needs_attention":
        blocked_by = str(result.get("blocked_by") or "unknown")
        extra: list[str] = []
        partial_answer = _partial_product_answer_text(result)
        if partial_answer:
            extra.append(partial_answer)
        raw_text = str(result.get("raw_planner_text") or "")
        if raw_text:
            extra.append("Raw planner output preview:\n" + raw_text[:3000])
        diagnostics = result.get("agent_flow_diagnostics") if isinstance(result.get("agent_flow_diagnostics"), dict) else {}
        raw_previews = diagnostics.get("last_non_empty_raw_previews") if isinstance(diagnostics, dict) else []
        if isinstance(raw_previews, list) and raw_previews:
            extra.append("Recent non-empty planner raw previews:\n" + "\n\n".join(str(x)[:900] for x in raw_previews[-3:]))
        if diagnostics.get("deterministic_strip_count"):
            extra.append(
                "Deterministic strip events occurred earlier in the same job: "
                + str(diagnostics.get("deterministic_strip_count"))
            )
        repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
        if repair:
            extra.append("Vulkan/GPU0 repair result:\n" + json.dumps(repair, ensure_ascii=False, default=str)[:3000])
        suffix = ("\n\n" + "\n\n".join(extra)) if extra else ""
        return (
            "Il loop agentico interno si è fermato prima del final del planner. "
            f"Stato={status_text}; blocker={blocked_by}.\n\n{summary}{suffix}"
        )
    if status_text == "max_steps_reached":
        partial_answer = _partial_product_answer_text(result)
        if partial_answer:
            return (
                "Il loop agentico interno ha raggiunto il limite di step senza un final valido del planner.\n\n"
                + partial_answer
                + "\n\n"
                + summary
            )
        return (
            "Il loop agentico interno ha raggiunto il limite di step senza un final del planner.\n\n"
            + summary
        )
    partial_answer = _partial_product_answer_text(result)
    if partial_answer:
        return (
            f"Risultato terminale del loop agentico: status={status_text}.\n\n"
            + partial_answer
            + "\n\n"
            + summary
        )
    return f"Risultato terminale del loop agentico: status={status_text}.\n\n{summary}"


def next_action_for_openwebui(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    status_text = str(status or "unknown")
    action = "answer_user_from_answer_for_30b"
    if status_text == "blocked_needs_attention":
        action = "report_blocker_and_use_structured_context_for_diagnosis"
    elif status_text == "completed":
        action = "answer_user_with_final_result"
    elif status_text == "max_steps_reached":
        action = "report_incomplete_loop_and_relevant_last_evidence"
    return {
        "action": action,
        "status": status_text,
        "blocked_by": result.get("blocked_by"),
        "do_not": [
            "do_not_ignore_answer_for_30b",
            "do_not_treat_job_url_as_the_only_result",
            "do_not_invent_repo_evidence_not_present_in_tool_context_for_30b",
        ],
        "use_fields_in_order": [
            "answer_for_30b",
            "tool_context_for_30b.best_partial_product_for_30b",
            "tool_context_for_30b.partial_products_for_30b",
            "tool_context_for_30b.artifacts",
            "tool_context_for_30b.evidence_contract_at_terminal",
            "tool_context_for_30b.history",
        ],
    }


def build_tool_context_for_30b(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Structured terminal context returned to OpenWebUI.

    This is not a human summary. It is the compact-but-complete execution trace
    the outer 30B needs to continue without losing the internal agent state.
    """
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
    diagnostics = _agent_flow_diagnostics(
        str(state.get("goal") or ""),
        history,
        state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else None,
    )
    if isinstance(result, dict):
        result = dict(result)
    partial_products = _partial_products_for_30b(history)
    best_partial_product = _best_partial_product_for_30b(history)
    if partial_products:
        result["partial_products_for_30b"] = partial_products
    if best_partial_product:
        result["best_partial_product_for_30b"] = best_partial_product
    controller_memory = state.get("controller_memory_last_write") if isinstance(state.get("controller_memory_last_write"), dict) else {}
    if controller_memory:
        diagnostics["controller_memory_records_written"] = 1 if controller_memory.get("ok") else 0
        diagnostics["controller_memory_target_key"] = controller_memory.get("target_key")
    result["agent_flow_diagnostics"] = diagnostics
    answer = answer_for_openwebui(status, final_summary, result)
    composed_answer = planner_composed_answer(agent_job_root(job_id))
    if status == "completed" and composed_answer.get("ok") and str(composed_answer.get("text") or "").strip():
        answer = str(composed_answer.get("text") or "").strip()
    evidence_digest = _execution_evidence_digest_text(result)
    evidence_view = _repo_read_content_views(history)
    next_action = next_action_for_openwebui(status, result)
    initial_orientation = (
        state.get("initial_orientation_surface")
        if isinstance(state.get("initial_orientation_surface"), dict)
        else _initial_orientation_surface_from_history(
            history,
            state.get("initial_orientation_skipped")
            if isinstance(state.get("initial_orientation_skipped"), list)
            else [],
        )
    )
    decisions = _planner_decision_rows(history)
    if terminal_decision:
        decisions.append({
            "step": terminal_decision.get("step"),
            "action": terminal_decision.get("action"),
            "tool": terminal_decision.get("tool"),
            "reason": terminal_decision.get("reason"),
            "final_answer_preview": str(terminal_decision.get("final_answer") or "")[:700],
            "terminal": True,
        })
    validation_rejections = _validation_rejection_rows(history)
    executed_tools = _executed_tool_rows(history)
    turn_memory = _planner_turn_memory(history, terminal_decision)
    result_digest = _compact_final_state_result(result)
    artifacts = _public_tool_artifact_rows(history)
    context = {
        "type": "agentic_loop_complete_structured_context",
        "contract_type": "agentic_loop_complete_structured_context",
        "not_a_summary": True,
        "openwebui_usage": {
            "primary_answer_field": "answer_for_30b",
            "next_action_field": "next_action_for_30b",
            "rule": (
                "Use answer_for_30b to respond to the user. Use the structured "
                "history/evidence only to justify or continue; never invent missing evidence."
            ),
        },
        "job": {
            "job_id": job_id,
            "status": status,
            "goal": state.get("goal"),
            "workspace": str(agent_job_root(job_id)),
            "planner_model": state.get("planner_model") or PLANNER_MODEL,
            "planner_url": state.get("planner_url") or PLANNER_URL,
        },
        "contract": {
            "planner_decides": True,
            "controller_validates_only": True,
            "controller_must_not_replace_planner_with_auto_tool_sequence": True,
            "invalid_planner_decision_flow": "planner_decision -> planner_decision_rejected/controller_guard -> next planner_decision",
            "final_requires_planner_final_action": True,
        },
        "execution_contract": {
            "planner_decides": True,
            "controller_validates_only": True,
            "controller_must_not_replace_planner_with_auto_tool_sequence": True,
            "invalid_planner_decision_flow": "planner_decision -> planner_decision_rejected/controller_guard -> next planner_decision",
            "final_requires_planner_final_action": True,
        },
        "final_answer": final_summary,
        "answer_for_30b": answer,
        "composed_answer": composed_answer,
        "artifacts": artifacts,
        "partial_products_for_30b": partial_products,
        "best_partial_product_for_30b": best_partial_product,
        "limits": _public_tool_context_limits(artifacts),
        "evidence_digest_for_30b": evidence_digest,
        "evidence_view_for_30b": evidence_view,
        "initial_orientation_surface": initial_orientation,
        "next_action_for_30b": next_action,
        "planner": {
            "planner_model": state.get("planner_model") or PLANNER_MODEL,
            "history_count": len(history),
            "terminal_decision": terminal_decision or None,
            "decisions": decisions,
            "validation_rejections": validation_rejections,
            "ollama_turns": turn_memory.get("ollama_turns", []),
        },
        "turn_memory": turn_memory,
        "ollama_turns": turn_memory.get("ollama_turns", []),
        "successful_tool_turns": turn_memory.get("successful_tool_turns", []),
        "evidence_contract_at_finish": planner_evidence_contract(str(state.get("goal") or ""), history),
        "evidence_contract_at_terminal": planner_evidence_contract(str(state.get("goal") or ""), history),
        "planner_memory": state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else {},
        "controller_memory": controller_memory,
        "agent_flow_diagnostics": diagnostics,
        "executed_tools": executed_tools,
        "history_count": len(history),
        "history": planner_history_ledger(history),
        "result_digest": result_digest,
        "planner_decision": result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else None,
        "blocked_by": result.get("blocked_by"),
        "local_references_omitted_for_openwebui": True,
    }
    return _strip_public_local_references(context)


def _controller_memory_lesson_text(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    history = result.get("history") if isinstance(result.get("history"), list) else []
    rejections = contract.get("validation_rejections_tail") if isinstance(contract.get("validation_rejections_tail"), list) else []
    last_rejection = next((r for r in reversed(rejections) if isinstance(r, dict) and r.get("summary")), {})
    reads = contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []
    lists = contract.get("repo_list_files_evidence") if isinstance(contract.get("repo_list_files_evidence"), list) else []
    list_paths = [str(row.get("path")) for row in lists if isinstance(row, dict) and row.get("path")]
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    lines = [
        f"job={job_id}",
        f"target={target_key}",
        f"status={status}",
        f"goal={str(state.get('goal') or '')[:240]}",
        f"final_gate={str(final_contract.get('reason') or '')[:240]}",
    ]
    if reads:
        lines.append("successful_reads=" + ", ".join(str(p) for p in reads[:8]))
    if list_paths:
        lines.append("listed_paths=" + ", ".join(list_paths[:8]))
    if last_rejection:
        lines.append("do_not_repeat_error=" + str(last_rejection.get("summary") or "")[:240])
    blocker = result.get("blocked_by") or result.get("blocked_tool") or result.get("rejected_tool")
    if blocker:
        lines.append("blocker=" + str(blocker)[:240])
    lines.append("correct_next=" + str(final_summary or final_contract.get("reason") or "")[:260])
    lines.append(f"history_count={len(history)}")
    return "\n".join(lines)[:1200]


def _write_controller_memory_lesson(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    goal = str(state.get("goal") or "")
    contract = planner_evidence_contract(goal, history)
    target_key = _controller_memory_target_key(goal, contract)
    text = _controller_memory_lesson_text(job_id, state, status, final_summary, result, contract, target_key)
    try:
        written = runtime_sqlite_memory_write({
            "kind": "controller_job_lesson",
            "tag": target_key,
            "text": text,
            "metadata": {
                "job_id": job_id,
                "status": status,
                "target_key": target_key,
                "target_kind": contract.get("target_kind"),
                "resolved_goal_scope": contract.get("resolved_goal_scope"),
                "resolved_goal_file": contract.get("resolved_goal_file"),
            },
        }, root)
    except Exception as exc:  # pragma: no cover - memory must not block job finalization
        written = {
            "ok": False,
            "tool": "runtime_sqlite_memory_write",
            "error": "controller_memory_lesson_write_failed",
            "error_type": type(exc).__name__,
            "details": str(exc)[:1000],
        }
    written["target_key"] = target_key
    written["controller_owned"] = True
    return written


def _loop_turn_memory_text(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    rejected = decision.get("rejected_decision") if isinstance(decision.get("rejected_decision"), dict) else {}
    lines = [
        f"loop_turn_key={job_id}:{row.get('step')}:{row.get('substep') or row.get('preseed_index') or ''}",
        f"job={job_id}",
        f"target={target_key}",
        f"step={row.get('step')}",
        f"substep={row.get('substep') or ''}",
        f"preseed_index={row.get('preseed_index') or ''}",
        f"goal={str(state.get('goal') or '')[:240]}",
        f"decision_action={str(decision.get('action') or '')[:80]}",
        f"decision_tool={str(decision.get('tool') or '')[:120]}",
        f"decision_reason={str(decision.get('reason') or '')[:240]}",
        f"decision_args={json.dumps(_prompt_clip_value(args, text_limit=180, list_limit=8), ensure_ascii=False, default=str)[:600]}",
        f"rejected_decision={json.dumps(_prompt_clip_value(rejected, text_limit=180, list_limit=8), ensure_ascii=False, default=str)[:600]}",
        f"result_tool={str(result.get('tool') or '')[:120]}",
        f"result_ok={result.get('ok')}",
        f"guard_type={str(result.get('guard_type') or '')[:120]}",
        f"summary={str(result.get('summary') or result.get('error') or '')[:260]}",
        f"successful_reads={', '.join(str(p) for p in (contract.get('successful_repo_read_paths') or [])[-8:])}",
        f"required_next_progress={str(contract.get('required_next_progress') or '')[:320]}",
        f"history_count_after_turn={contract.get('history_count') or ''}",
    ]
    return "\n".join(line for line in lines if not line.endswith("="))[:4000]


def _write_loop_turn_memory(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    root: Path,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist one controller-visible loop turn in SQLite memory.

    This is internal loop memory, not OpenWebUI public payload and not a planner
    tool call. The planner still decides; this only makes prior turns searchable
    without depending on how many message-history items fit in the next prompt.
    """
    goal = str(state.get("goal") or "")
    contract = planner_evidence_contract(goal, history)
    target_key = _controller_memory_target_key(goal, contract)
    text = _loop_turn_memory_text(job_id, state, row, contract, target_key)
    try:
        written = runtime_sqlite_memory_write({
            "kind": "controller_loop_turn",
            "tag": target_key,
            "text": text,
            "metadata": {
                "job_id": job_id,
                "step": row.get("step"),
                "substep": row.get("substep"),
                "preseed_index": row.get("preseed_index"),
                "target_key": target_key,
                "decision_action": (row.get("decision") or {}).get("action")
                if isinstance(row.get("decision"), dict) else None,
                "decision_tool": (row.get("decision") or {}).get("tool")
                if isinstance(row.get("decision"), dict) else None,
                "result_tool": (row.get("tool_result") or {}).get("tool")
                if isinstance(row.get("tool_result"), dict) else None,
                "result_ok": (row.get("tool_result") or {}).get("ok")
                if isinstance(row.get("tool_result"), dict) else None,
            },
        }, root)
    except Exception as exc:  # pragma: no cover - loop memory must not block routing
        written = {
            "ok": False,
            "tool": "runtime_sqlite_memory_write",
            "error": "controller_loop_turn_memory_write_failed",
            "error_type": type(exc).__name__,
            "details": str(exc)[:1000],
        }
    written["target_key"] = target_key
    written["controller_owned"] = True
    written["loop_turn_memory"] = True
    return written


def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = agent_job_root(job_id)
    result = dict(result or {})
    final_summary_with_turns = _final_summary_with_ollama_done_reasons(status, final_summary, result)
    controller_memory = _write_controller_memory_lesson(
        job_id, state, status, final_summary_with_turns, result, root
    )
    result["controller_memory_write"] = controller_memory
    state["controller_memory_last_write"] = controller_memory
    tool_context = build_tool_context_for_30b(job_id, state, status, final_summary_with_turns, result)
    if tool_context.get("partial_products_for_30b") not in (None, "", [], {}):
        result["partial_products_for_30b"] = tool_context.get("partial_products_for_30b")
    if tool_context.get("best_partial_product_for_30b") not in (None, "", [], {}):
        result["best_partial_product_for_30b"] = tool_context.get("best_partial_product_for_30b")
    public_result = _public_terminal_result_for_30b(result)
    answer = tool_context.get("answer_for_30b") or final_summary_with_turns
    public_final_summary = (
        answer
        if status == "completed" and _latest_code_product_payload(result.get("history") if isinstance(result.get("history"), list) else [])
        else final_summary_with_turns
    )
    next_action = tool_context.get("next_action_for_30b") or {}
    final = {
        "ok": status == "completed",
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "answer_for_30b": answer,
        "message_for_30b": answer,
        "next_action_for_30b": next_action,
        "result": public_result,
        "agent_flow_diagnostics": tool_context.get("agent_flow_diagnostics"),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": _terminal_context_alias(),
        "structured_context_for_30b": _terminal_context_alias(),
        "structured_result_for_30b": _terminal_context_alias(),
        "events_path": str(root / "events.ndjson"),
    }
    write_json(root / "final.json", final)
    (root / "final.md").write_text(answer, encoding="utf-8")
    state = load_agent_job_state(job_id) or state
    state.update({
        "status": status,
        "final_path": str(root / "final.json"),
        "final_markdown_path": str(root / "final.md"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "answer_for_30b": answer,
        "message_for_30b": answer,
        "next_action_for_30b": next_action,
        "result": _compact_final_state_result(public_result),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": _terminal_context_alias(),
        "structured_context_for_30b": _terminal_context_alias(),
        "structured_result_for_30b": _terminal_context_alias(),
    })
    write_agent_job_state(state)
    append_agent_event(
        job_id, "job_finished", f"Job finished status={status}.", {"status": status},
        step=state.get("current_step"),
    )
    return final


def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    from .tool_dispatch import dispatch_tool  # noqa
    from .tool_contract import normalize_tool_name, sanitize_tool_args  # noqa

    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    root = agent_job_root(job_id)
    max_steps = max(1, min(int(state.get("max_steps") or AGENT_DEFAULT_MAX_STEPS), AGENT_MAX_STEPS))
    approval_mode = str(state.get("approval_mode") or "safe_write_lab")
    original_args = dict(state.get("original_args") or {})
    public_tool_name = str(state.get("public_tool_name") or "vulkan_helper")
    history: list[dict[str, Any]] = []

    def persist_loop_turn_memory(row: dict[str, Any]) -> None:
        state["controller_loop_turn_memory_last_write"] = _write_loop_turn_memory(
            job_id,
            state,
            row,
            root,
            history,
        )

    def append_cached_tool_result(step_number: int, planner_decision: dict[str, Any], cached: dict[str, Any]) -> None:
        cached_result = cached.get("result") if isinstance(cached.get("result"), dict) else {}
        append_agent_event(
            job_id,
            "tool_cache_hit",
            f"{cached.get('tool')} reused cached intra-job result.",
            {
                "tool": cached.get("tool"),
                "cache_key": cached.get("cache_key"),
                "cached_from_step": cached_result.get("cached_from_step"),
                "cached_from_artifact": cached_result.get("cached_from_artifact"),
            },
            step=step_number,
        )
        row = {
            "step": step_number,
            "decision": {k: v for k, v in planner_decision.items() if k != "raw_planner_text_preview"},
            "tool_result": cached_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def append_repeat_guard_result(
        step_number: int,
        planner_decision: dict[str, Any],
        tool: str,
        internal_args: dict[str, Any],
    ) -> None:
        validation_repeat = {
            "ok": False,
            "violations": ["repeated_same_tool_arguments_without_progress"],
            "evidence_contract": planner_evidence_contract(str(state.get("goal") or ""), history),
        }
        guard_result = controller_guard_result_for_validation(validation_repeat, planner_decision)
        guard_result["guard_type"] = "repeat_guard"
        guard_result["summary"] = "repeated_same_tool_arguments_without_progress"
        guard_result["rejected_decision"] = {
            "action": planner_decision.get("action"),
            "tool": tool,
            "arguments": internal_args,
            "reason": planner_decision.get("reason"),
        }
        append_agent_event(job_id, "planner_decision_rejected", guard_result["summary"], guard_result, step=step_number)
        row = {
            "step": step_number,
            "decision": {"action": "continue_required", "reason": "repeat guard rejected planner proposal"},
            "tool_result": guard_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def execute_validated_tool_decision(step_number: int, planner_decision: dict[str, Any], substep: int | None = None) -> dict[str, Any] | None:
        tool = normalize_tool_name(str(planner_decision.get("tool") or ""))
        args = planner_decision.get("arguments") if isinstance(planner_decision.get("arguments"), dict) else {}
        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
        if repeated_tool_call_count(history, tool, internal_args) >= 2:
            append_repeat_guard_result(step_number, planner_decision, tool, internal_args)
            return None
        cache_key = _tool_cache_key(tool, internal_args)
        if cache_key:
            hit = _tool_cache_hit(history, tool, internal_args)
            if hit:
                cached_result = _cached_tool_result(hit, cache_key)
                append_cached_tool_result(step_number, planner_decision, {
                    "tool": tool,
                    "arguments": internal_args,
                    "cache_key": cache_key,
                    "result": cached_result,
                })
                return None

        allowed, block_reason = _agentic_tool_allowed(tool, internal_args, approval_mode)
        if not allowed:
            append_agent_event(job_id, "tool_blocked", block_reason, {"tool": tool}, step=step_number)
            return finalize_agentic_job(
                job_id, state, "blocked_needs_consent", block_reason,
                {"history": history, "blocked_tool": tool},
            )

        event_payload = {"tool": tool, "arguments": internal_args}
        if substep is not None:
            event_payload["substep"] = substep
        state["status_message"] = f"executing {tool}"
        write_agent_job_state(state)
        append_agent_event(job_id, "tool_start", f"Executing {tool}", event_payload, step=step_number)

        result = dispatch_tool(
            tool, internal_args, root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        suffix = f"-{substep:02d}" if substep is not None else ""
        tool_result_path = root / "tool-results" / f"step-{step_number:03d}{suffix}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {})
        compact_result["artifact"] = str(tool_result_path)
        if substep is not None:
            compact_result["substep"] = substep
        if cache_key and bool(compact_result.get("ok")):
            compact_result["cache_key"] = cache_key
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}", compact_result, step=step_number)
        row = {
            "step": step_number,
            "decision": {k: v for k, v in planner_decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        }
        if substep is not None:
            row["substep"] = substep
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)
        return None

    state.update({
        "status": "running_agentic",
        "planner_url": PLANNER_URL,
        "planner_model": PLANNER_MODEL,
        "selector_url": OLLAMA_TASK_URL,
        "selector_model": OLLAMA_TASK_MODEL,
    })
    write_agent_job_state(state)
    append_agent_event(
        job_id, "agentic_loop_started",
        "Controlled 30B planner loop started.",
        {"max_steps": max_steps, "planner_url": PLANNER_URL}, step=0,
    )

    initial_orientation_skipped: list[dict[str, Any]] = []

    def update_initial_orientation_state() -> None:
        state["initial_orientation_skipped"] = initial_orientation_skipped[-120:]
        state["initial_orientation_surface"] = _initial_orientation_surface_from_history(
            history,
            initial_orientation_skipped,
        )
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
        state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
            str(state.get("goal") or ""),
            history,
            state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else None,
        )
        write_agent_job_state(state)

    def add_initial_orientation_skipped(skipped: list[dict[str, Any]]) -> None:
        for item in skipped:
            if isinstance(item, dict) and item not in initial_orientation_skipped:
                initial_orientation_skipped.append(item)
        update_initial_orientation_state()

    def execute_controller_preseed(preseed_plan: dict[str, Any], preseed_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
        preseed_tool = str(preseed_plan["tool"])
        preseed_args = dict(preseed_plan["arguments"])
        preseed_event = str(preseed_plan["event"])
        preseed_result_event = str(preseed_plan["result_event"])
        preseed_reason = str(preseed_plan["reason"])
        internal_preseed_args = sanitize_tool_args(
            preseed_tool, dict(preseed_args), original_args, public_tool_name
        )
        preseed_cache_key = _tool_cache_key(preseed_tool, internal_preseed_args)
        state["status_message"] = preseed_event.replace("_", " ")
        write_agent_job_state(state)
        append_agent_event(
            job_id,
            preseed_event,
            f"Executing deterministic {preseed_tool} preseed.",
            {
                "tool": preseed_tool,
                "arguments": preseed_args,
                "cache_key": preseed_cache_key,
                "preseed_reason": preseed_reason,
                "preseed_index": preseed_index,
                "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
            },
            step=0,
        )
        try:
            preseed_result = dispatch_tool(
                preseed_tool,
                internal_preseed_args,
                root,
                allow_command=True,
                user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
            )
        except Exception as exc:  # pragma: no cover - defensive artifact preservation
            preseed_result = {
                "ok": False,
                "tool": preseed_tool,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": traceback.format_exc()[-4000:],
            }
        tool_results_dir = root / "tool-results"
        tool_results_dir.mkdir(parents=True, exist_ok=True)
        suffix = str(preseed_plan["artifact_suffix"]).replace("\\", "__").replace("/", "__")
        preseed_path = tool_results_dir / f"step-000-{preseed_index:02d}-controller_preseed_{suffix}.json"
        write_json(preseed_path, preseed_result)
        compact_preseed = compact_tool_result_for_planner(
            preseed_tool, preseed_result if isinstance(preseed_result, dict) else {}
        )
        compact_preseed.update({
            "artifact": str(preseed_path),
            "controller_preseed": True,
            "preseed_reason": preseed_reason,
            "preseed_index": preseed_index,
            "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
        })
        if preseed_cache_key:
            compact_preseed["cache_key"] = preseed_cache_key
        append_agent_event(
            job_id,
            preseed_result_event,
            f"{preseed_tool} preseed ok={bool(compact_preseed.get('ok'))}.",
            compact_preseed,
            step=0,
        )
        row = {
            "step": 0,
            "preseed_index": preseed_index,
            "decision": {
                "action": "controller_preseed",
                "tool": preseed_tool,
                "arguments": preseed_args,
                "reason": preseed_reason,
            },
            "tool_result": compact_preseed,
        }
        history.append(row)
        persist_loop_turn_memory(row)
        update_initial_orientation_state()
        return preseed_result if isinstance(preseed_result, dict) else {}, compact_preseed

    def execute_dynamic_initial_orientation(root_result: dict[str, Any], preseed_index: int) -> int:
        if not root_result.get("ok"):
            return preseed_index
        doc_plan, skipped = _controller_initial_doc_preseed_plan(root_result)
        add_initial_orientation_skipped(skipped)
        if doc_plan:
            execute_controller_preseed(doc_plan, preseed_index)
            preseed_index += 1

        area_plans, skipped = _controller_initial_area_list_plans(root_result)
        add_initial_orientation_skipped(skipped)
        for area_plan in area_plans:
            area_list_result, _area_compact = execute_controller_preseed(area_plan, preseed_index)
            preseed_index += 1
            area_read_plan, skipped = _controller_initial_area_read_plan(area_list_result)
            add_initial_orientation_skipped(skipped)
            if area_read_plan:
                execute_controller_preseed(area_read_plan, preseed_index)
                preseed_index += 1
        return preseed_index

    preseed_plan = _controller_preseed_plan(str(state.get("goal") or ""), original_args)
    if preseed_plan:
        preseed_index = 1
        root_preseed_result, _root_compact = execute_controller_preseed(preseed_plan, preseed_index)
        preseed_index += 1
        if preseed_plan.get("dynamic_initial_orientation") and root_preseed_result.get("ok"):
            preseed_index = execute_dynamic_initial_orientation(root_preseed_result, preseed_index)
        orientation_plan = _controller_file_code_product_orientation_preseed_plan(str(state.get("goal") or ""))
        if orientation_plan and not preseed_plan.get("dynamic_initial_orientation"):
            orientation_result, _orientation_compact = execute_controller_preseed(
                orientation_plan,
                preseed_index,
            )
            preseed_index += 1
            preseed_index = execute_dynamic_initial_orientation(orientation_result, preseed_index)

    for step in range(1, max_steps + 1):
        state = load_agent_job_state(job_id) or state
        if str(state.get("status") or "") == "cancel_requested":
            return finalize_agentic_job(job_id, state, "cancelled", "Job cancelled.", {"history": history})

        goal_text = str(state.get("goal") or "")
        contract_snapshot = planner_evidence_contract(goal_text, history)
        memory_snapshot = planner_memory_surface({
            "goal": goal_text,
            "limit": 12,
            "target_key": _controller_memory_target_key(goal_text, contract_snapshot),
        }, root)
        state.update({
            "current_step": step,
            "status_message": "planning next action",
            "evidence_contract": contract_snapshot,
            "planner_memory_surface": memory_snapshot,
            "working_memory_for_30b": {
                "schema": "agentic_loop_operational_memory.v1",
                "goal": state.get("goal"),
                "history_count": len(history),
                "successful_repo_read_paths": contract_snapshot.get("successful_repo_read_paths", []),
                "latest_repo_list_path": (contract_snapshot.get("repo_list_files_evidence") or [{}])[-1].get("path") if contract_snapshot.get("repo_list_files_evidence") else None,
                "candidate_next_actions": contract_snapshot.get("candidate_next_actions", []),
                "file_memory": contract_snapshot.get("file_memory", []),
                "operational_notes": contract_snapshot.get("operational_notes", {}),
                "planner_memory": memory_snapshot,
                "finalization_contract": contract_snapshot.get("finalization_contract", {}),
                "codex_quality": contract_snapshot.get("agentic_codex_quality", {}),
                "rejections_tail": contract_snapshot.get("validation_rejections_tail", []),
            },
        })
        write_agent_job_state(state)

        # The planner must remain the decision-maker. 3572 may validate or reject
        # the proposal, but must not synthesize hidden tool calls such as an
        # automatic repo_read after repo_list_files.
        decision = planner_decision(job_id, state, step, history)

        append_agent_event(
            job_id, "planner_decision",
            f"Decision: {decision.get('action')} {decision.get('tool', '')}",
            decision, step=step,
        )

        planner_memory_snapshot = (
            state.get("planner_memory_surface")
            if isinstance(state.get("planner_memory_surface"), dict)
            else {}
        )
        memory_claim_text = _decision_memory_claim_text(decision)
        if _planner_memory_false_unavailable_claim(memory_claim_text, planner_memory_snapshot):
            retry_limit = (
                AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES
                if step < max_steps else 0
            )
            retry_count = _planner_incomprehensible_retry_count(history)
            if int(retry_limit or 0) > 0 and retry_count < int(retry_limit):
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_memory_false_unavailable_claim",
                    "summary": "planner_memory_available_but_planner_claimed_unavailable",
                    "classification": "planner_memory_false_unavailable_claim_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "raw_planner_text_preview": memory_claim_text[:4000],
                    "planner_memory": {
                        "available": True,
                        "record_count": planner_memory_snapshot.get("record_count", 0),
                        "source": planner_memory_snapshot.get("source"),
                    },
                    "next_instruction": (
                        "planner_memory is available; do not claim long-term memory is unavailable; "
                        "repeat as one pure JSON object; use/cite intrinsic_context and planner_memory first; "
                        "call runtime_sqlite_memory_search only for a named selective gap"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                }
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner falsely claimed long-term memory unavailable",
                        "rejected_decision": guard_result["rejected_decision"],
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
                    str(state.get("goal") or ""),
                    history,
                    planner_memory_snapshot,
                )
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                (
                    "Planner claimed long-term memory is unavailable even though "
                    "the controller injected planner_memory.available=true."
                ),
                {
                    "history": history,
                    "blocked_by": "planner_memory_false_unavailable_claim",
                    "planner_decision": decision,
                    "agent_flow_diagnostics": _agent_flow_diagnostics(
                        str(state.get("goal") or ""),
                        history,
                        planner_memory_snapshot,
                    ),
                },
            )

        if str(decision.get("action") or "").strip().lower() == "tool_batch":
            calls = decision.get("tool_calls") if isinstance(decision.get("tool_calls"), list) else []
            batch_decisions: list[dict[str, Any]] = []
            batch_guard: dict[str, Any] | None = None
            if not calls:
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_invalid",
                    "summary": "native_tool_batch_empty",
                    "violations": ["native_tool_batch_empty"],
                }
            elif len(calls) > int(AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY or 1):
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_too_large",
                    "summary": "native_tool_batch_exceeds_readonly_limit",
                    "violations": ["native_tool_batch_too_large"],
                    "native_tool_call_count": len(calls),
                    "native_tool_call_limit": int(AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY or 1),
                }
            else:
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    call_decision = {
                        "action": "tool",
                        "tool": normalize_tool_name(str(call.get("tool") or "")),
                        "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                        "reason": "native_tool_call_batch",
                        "native_tool_call": True,
                        "raw_native_tool_call": call.get("raw_tool_call") if isinstance(call.get("raw_tool_call"), dict) else call,
                    }
                    if isinstance(decision.get("allowed_tool_names"), list):
                        call_decision["allowed_tool_names"] = list(decision["allowed_tool_names"])
                    if isinstance(decision.get("allowed_native_tool_names"), list):
                        call_decision["allowed_native_tool_names"] = list(decision["allowed_native_tool_names"])
                    if isinstance(decision.get("prompt_context_continuation_required"), dict):
                        call_decision["prompt_context_continuation_required"] = decision["prompt_context_continuation_required"]
                    internal_args = sanitize_tool_args(
                        call_decision["tool"],
                        dict(call_decision["arguments"]),
                        original_args,
                        public_tool_name,
                    )
                    if not _tool_cache_key(call_decision["tool"], internal_args):
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_non_readonly",
                            "summary": "native_tool_batch_requires_readonly_tools_only",
                            "violations": ["native_tool_batch_non_readonly"],
                            "rejected_decision": call_decision,
                        }
                        break
                    validation_i = validate_planner_decision_against_evidence(
                        str(state.get("goal") or ""), call_decision, history
                    )
                    if not validation_i.get("ok"):
                        should_repair_call = _should_attempt_vulkan_repair(call_decision, validation_i, history)
                        repair_result = {
                            "ok": False,
                            "error": "vulkan_repair_not_applicable_for_this_invalid_decision",
                        }
                        if should_repair_call:
                            repair_result = vulkan_repair_invalid_planner_decision(
                                goal=str(state.get("goal") or ""),
                                step=step,
                                decision=call_decision,
                                validation=validation_i,
                                history=history,
                                state=state,
                            )
                        if repair_result.get("ok") and isinstance(repair_result.get("repaired_decision"), dict):
                            repaired_decision = _normalize_terminal_planner_decision(
                                repair_result["repaired_decision"]
                            )
                            if _native_required_repaired_tool_decision_disallowed(repaired_decision):
                                batch_guard = {
                                    "tool": "controller_guard",
                                    "ok": True,
                                    "guard_type": "native_tool_batch_validation",
                                    "summary": "vulkan_repair_tool_decision_disallowed_in_native_mode",
                                    "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                                    "rejected_decision": call_decision,
                                    "vulkan_repair": repair_result,
                                }
                                break
                            append_agent_event(
                                job_id,
                                "vulkan_gpu0_decision_repair",
                                "Vulkan/GPU0 repaired invalid native batch tool call.",
                                {"repair_ok": True, "repaired_decision": repaired_decision},
                                step=step,
                            )
                            decision = repaired_decision
                            break
                        batch_guard = controller_guard_result_for_validation(validation_i, call_decision)
                        batch_guard["guard_type"] = "native_tool_batch_validation"
                        batch_guard["summary"] = "native_tool_batch_validation_failed"
                        if should_repair_call:
                            batch_guard["vulkan_repair"] = repair_result
                        break
                    batch_decisions.append(call_decision)

            if str(decision.get("action") or "").strip().lower() != "tool_batch":
                pass
            elif batch_guard:
                append_agent_event(job_id, "planner_decision_rejected", batch_guard["summary"], batch_guard, step=step)
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": batch_guard["summary"],
                        "rejected_decision": decision,
                    },
                    "tool_result": batch_guard,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            elif batch_decisions:
                append_agent_event(
                    job_id,
                    "native_tool_batch_executed",
                    f"Executing native read-only tool batch. count={len(batch_decisions)}",
                    {"count": len(batch_decisions)},
                    step=step,
                )
                for idx, batch_decision in enumerate(batch_decisions, start=1):
                    terminal = execute_validated_tool_decision(step, batch_decision, substep=idx)
                    if terminal is not None:
                        return terminal
                continue

        validation = validate_planner_decision_against_evidence(
            str(state.get("goal") or ""), decision, history
        )
        if not validation.get("ok"):
            raw_planner_text = _decision_raw_planner_text(decision)
            retry_limit = (
                AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES
                if step < max_steps else 0
            )
            planner_memory_snapshot = (
                state.get("planner_memory_surface")
                if isinstance(state.get("planner_memory_surface"), dict)
                else {}
            )
            validation_violations = {
                str(v)
                for v in (
                    validation.get("violations")
                    if isinstance(validation.get("violations"), list)
                    else []
                )
            }
            if "planner_native_tool_call_required" in validation_violations:
                prior_native_empty_guards = controller_guard_count(
                    history,
                    "planner_native_tool_call_required",
                )
                if prior_native_empty_guards >= int(retry_limit or 0):
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        (
                            "planner_native_tool_call_required_repeated: planner native tool mode "
                            "was active, tools were provided to Ollama, but the planner repeatedly "
                            "returned no message.tool_calls. Controller did not fall back to JSON-text "
                            "tool execution."
                        ),
                        {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": "planner_native_tool_call_required_repeated",
                            "validation": validation,
                            "agent_flow_diagnostics": _agent_flow_diagnostics(
                                str(state.get("goal") or ""),
                                history,
                                planner_memory_snapshot,
                            ),
                        },
                    )
                guard_result = controller_guard_result_for_validation(validation, decision)
                guard_result["guard_type"] = "planner_native_tool_call_required"
                guard_result["summary"] = "planner_native_tool_call_required"
                guard_result["retry_count"] = prior_native_empty_guards
                guard_result["retry_limit"] = int(retry_limit or 0)
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "native planner emitted no message.tool_calls",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            if (
                _planner_memory_false_unavailable_claim(raw_planner_text, planner_memory_snapshot)
                and int(retry_limit or 0) > 0
                and _planner_incomprehensible_retry_count(history) < int(retry_limit)
            ):
                retry_count = _planner_incomprehensible_retry_count(history)
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_memory_false_unavailable_claim",
                    "summary": "planner_memory_available_but_planner_claimed_unavailable",
                    "classification": "plain_text_non_json_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "violations": validation.get("violations"),
                    "raw_planner_text_preview": raw_planner_text[:4000],
                    "planner_memory": {
                        "available": True,
                        "record_count": planner_memory_snapshot.get("record_count", 0),
                        "source": planner_memory_snapshot.get("source"),
                    },
                    "next_instruction": (
                        "planner_memory is available; do not claim long-term memory is unavailable; "
                        "repeat as one pure JSON object and either use planner_memory, call a memory tool, "
                        "or choose another evidence-bound action"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                    "evidence_contract": validation.get("evidence_contract"),
                }
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner falsely claimed long-term memory unavailable",
                        "rejected_decision": guard_result["rejected_decision"],
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
                    str(state.get("goal") or ""),
                    history,
                    planner_memory_snapshot,
                )
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if _should_retry_incomprehensible_planner_output(
                decision, history, retry_limit
            ):
                output_classification = _raw_planner_text_classification(raw_planner_text)
                retry_count = _planner_incomprehensible_retry_count(history)
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_retry_required",
                    "summary": "planner_output_incomprehensible_repeat_required",
                    "classification": f"{output_classification}_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "violations": validation.get("violations"),
                    "raw_planner_text_preview": raw_planner_text[:4000],
                    "next_instruction": (
                        "repeat as one pure JSON object; no prose before or after; "
                        "choose from candidate_next_actions; do not answer unrelated "
                        "questions"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                    "evidence_contract": validation.get("evidence_contract"),
                }
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": (
                            "planner output incomprehensible; planner must repeat "
                            "with one pure JSON decision"
                        ),
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if "planner_repeated_invalid_code_product_decision" in {
                str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])
            }:
                guard_result = controller_guard_result_for_validation(validation, decision)
                guard_result["guard_type"] = "planner_repeated_invalid_code_product_decision"
                guard_result["summary"] = "planner_repeated_invalid_code_product_decision"
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner repeated identical invalid code-product decision",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                blocker_answer = (
                    "planner_repeated_invalid_code_product_decision: planner repeated the same invalid "
                    "repo_propose_code_edit placeholder/missing-payload decision after the validator "
                    "already required a route shift. Controller did not synthesize a patch or hidden tool call."
                )
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    blocker_answer,
                    {
                        "history": history,
                        "blocked_by": "planner_repeated_invalid_code_product_decision",
                        "planner_decision": decision,
                        "invalid_decision_signature": validation.get("invalid_decision_signature"),
                        "invalid_decision_repeat_count": validation.get("invalid_decision_repeat_count"),
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )

            rejection_signature = _controller_guard_rejection_signature(validation, decision)
            repeated_rejection_count = _controller_guard_rejection_signature_count(
                history,
                rejection_signature,
            )
            repeated_rejection_limit = max(1, int(retry_limit or 0))
            if repeated_rejection_count >= repeated_rejection_limit:
                guard_result = controller_guard_result_for_validation(validation, decision)
                guard_result["guard_type"] = "repeated_identical_planner_rejection"
                guard_result["summary"] = "repeated_identical_planner_rejection"
                guard_result["invalid_decision_signature"] = rejection_signature
                guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
                guard_result["retry_limit"] = repeated_rejection_limit
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner repeated identical rejected decision",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    (
                        "repeated_identical_planner_rejection: planner repeated the same "
                        "validator-rejected decision after controller feedback. Controller "
                        "stopped the loop and preserved available payloads instead of "
                        "consuming max_steps."
                    ),
                    {
                        "history": history,
                        "blocked_by": "repeated_identical_planner_rejection",
                        "planner_decision": decision,
                        "validation": validation,
                        "invalid_decision_signature": rejection_signature,
                        "invalid_decision_repeat_count": repeated_rejection_count + 1,
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )

            if _is_unrecoverable_plain_text_planner_output(decision, history, retry_limit):
                final_answer = str(decision.get("final_answer") or decision.get("reason") or "")
                raw_text = str(decision.get("raw_planner_text") or "")
                output_classification = _raw_planner_text_classification(raw_text)
                repair_reason = f"{output_classification}_not_gpu0_repairable"
                if raw_text:
                    final_answer += (
                        "\n\nRaw planner output surfaced, first 4000 chars:\n"
                        + raw_text[:4000]
                    )
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    "planner_output_gpu1_retry_unrecoverable_no_gpu0_repair",
                    {
                        "classification": output_classification,
                        "retry_count": _planner_incomprehensible_retry_count(history),
                        "retry_limit": int(AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES or 0),
                        "raw_planner_text_preview": raw_text[:4000],
                        "vulkan_repair": {
                            "attempted": False,
                            "reason": repair_reason,
                        },
                    },
                    step=step,
                )
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    final_answer,
                    {
                        "history": history,
                        "planner_decision": decision,
                        "blocked_by": decision.get("reason"),
                        "classification": f"planner_output_{output_classification}_unrecoverable",
                        "raw_planner_text": decision.get("raw_planner_text"),
                        "vulkan_repair": {
                            "attempted": False,
                            "reason": repair_reason,
                        },
                    },
                )

            repair_result: dict[str, Any] = {
                "ok": False,
                "error": "vulkan_repair_not_applicable_for_this_invalid_decision",
            }
            cached_repair_result = _cached_vulkan_repair_result(decision, history)
            should_attempt_vulkan = bool(cached_repair_result)
            if cached_repair_result:
                repair_result = cached_repair_result
                append_agent_event(
                    job_id,
                    "vulkan_gpu0_repair_cache_hit",
                    "Reused cached Vulkan/GPU0 repair for identical raw planner output.",
                    {
                        "repair_cache_key": repair_result.get("repair_cache_key"),
                        "cached_from_step": repair_result.get("cached_from_step"),
                        "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                    },
                    step=step,
                )
            else:
                should_attempt_vulkan = _should_attempt_vulkan_repair(decision, validation, history)
            if should_attempt_vulkan and not cached_repair_result:
                repair_result = vulkan_repair_invalid_planner_decision(
                    goal=str(state.get("goal") or ""),
                    step=step,
                    decision=decision,
                    validation=validation,
                    history=history,
                    state=state,
                )

            if (
                should_attempt_vulkan
                and repair_result.get("ok")
                and isinstance(repair_result.get("repaired_decision"), dict)
            ):
                repaired_decision = _normalize_terminal_planner_decision(
                    repair_result["repaired_decision"]
                )
                if _native_required_repaired_tool_decision_disallowed(repaired_decision):
                    repaired_validation = {
                        "ok": False,
                        "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                        "evidence_contract": planner_evidence_contract(str(state.get("goal") or ""), history),
                    }
                else:
                    repaired_validation = validate_planner_decision_against_evidence(
                        str(state.get("goal") or ""), repaired_decision, history
                    )
                append_agent_event(
                    job_id,
                    "vulkan_gpu0_decision_repair",
                    "Vulkan/GPU0/11435 proposed repaired planner decision.",
                    {
                        "repair_ok": bool(repaired_validation.get("ok")),
                        "original_violations": validation.get("violations"),
                        "repaired_validation": repaired_validation,
                        "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                        "repair_cache_key": repair_result.get("repair_cache_key"),
                        "repair_cache_hit": repair_result.get("repair_cache_hit"),
                        "cached_from_step": repair_result.get("cached_from_step"),
                        "repaired_decision": {
                            k: repaired_decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer")
                            if repaired_decision.get(k) not in (None, "", [], {})
                        },
                    },
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner proposal rejected; explicit Vulkan/GPU0 repair attempted and surfaced",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": {
                        "tool": "controller_guard",
                        "ok": True,
                        "guard_type": "vulkan_decision_repair",
                        "summary": "vulkan_gpu0_11435_repaired_invalid_planner_emission",
                        "violations": validation.get("violations"),
                        "evidence_contract": validation.get("evidence_contract"),
                        "vulkan_repair": {
                            "ok": True,
                            "raw_text_preview": repair_result.get("raw_text_preview"),
                            "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                            "repair_cache_key": repair_result.get("repair_cache_key"),
                            "repair_cache_hit": repair_result.get("repair_cache_hit"),
                            "cached_from_step": repair_result.get("cached_from_step"),
                            "repaired_decision": {
                                k: repaired_decision.get(k)
                                for k in ("action", "tool", "arguments", "reason", "final_answer")
                                if repaired_decision.get(k) not in (None, "", [], {})
                            },
                            "repaired_validation": repaired_validation,
                        },
                    },
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                if repaired_validation.get("ok"):
                    decision = repaired_decision
                    validation = repaired_validation
                else:
                    continue
            else:
                guard_result = controller_guard_result_for_validation(validation, decision)
                if should_attempt_vulkan:
                    guard_result["vulkan_repair"] = {
                        k: repair_result.get(k)
                        for k in (
                            "ok", "error", "raw_text_preview", "raw_planner_text_preview",
                            "repair_cache_key", "repair_cache_hit", "cached_from_step",
                        )
                        if repair_result.get(k) not in (None, "", [], {})
                    }
                append_agent_event(
                    job_id, "planner_decision_rejected",
                    guard_result.get("summary") or "Planner decision rejected by evidence validator.",
                    guard_result, step=step,
                )

                if (
                    str(decision.get("action") or "").strip().lower() == "block"
                    and str(decision.get("reason") or "") == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE"
                ):
                    final_answer = str(decision.get("final_answer") or decision.get("reason") or "")
                    if should_attempt_vulkan:
                        final_answer += (
                            "\n\nVulkan/GPU0 11435 repair was attempted and failed: "
                            + str(repair_result.get("error") or "unknown")
                        )
                    raw_text = str(decision.get("raw_planner_text") or "")
                    if raw_text:
                        final_answer += (
                            "\n\nRaw planner output surfaced, first 4000 chars:\n"
                            + raw_text[:4000]
                        )
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        final_answer,
                        {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": decision.get("reason"),
                            "classification": "planner_output_unrecoverable",
                            "raw_planner_text": decision.get("raw_planner_text"),
                            "vulkan_repair": repair_result if should_attempt_vulkan else {"attempted": False},
                        },
                    )

                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner proposal rejected by evidence validator; explicit repair not available or failed",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

        decision = _normalize_terminal_planner_decision(decision if isinstance(decision, dict) else {})
        action = str(decision.get("action") or "tool").strip().lower()

        # --- final ---
        if action in {"final", "done", "complete", "completed"}:
            final_answer = str(
                decision.get("final_answer") or decision.get("answer")
                or decision.get("summary") or "Job completed."
            )
            if goal_has_write_intent(state.get("goal") or "") and not history_has_tool(history, "repo_apply_patch"):
                row = {
                    "step": step,
                    "decision": {"action": "continue_required",
                                  "reason": "final rejected: patch requested but not applied"},
                    "tool_result": {
                        "tool": "controller_guard", "ok": True,
                        "summary": (
                            "The user requested a patch. You may not final yet. "
                            "Use repo_apply_patch if old_text/new_text are ready, "
                            "or repo_read to get old_text first."
                        ),
                    },
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            terminal_decision = dict(decision)
            terminal_decision["step"] = step
            return finalize_agentic_job(
                job_id, state, "completed", final_answer,
                {"history": history, "planner_decision": terminal_decision},
            )

        # --- block ---
        if action in {"block", "blocked", "need_user", "needs_user"}:
            # No fallback: do not convert planner block/no-json/timeout into a
            # controller_guard loop. Surface the real loop result and artifacts.
            final_answer = str(decision.get("final_answer") or decision.get("reason") or "Job blocked.")
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                final_answer,
                {"history": history, "planner_decision": decision, "blocked_by": decision.get("reason")},
            )

        # --- tool ---
        tool = normalize_tool_name(str(decision.get("tool") or ""))
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}

        if not tool or tool not in VALID_INTERNAL_TOOLS:
            # Should be unreachable because validate_planner_decision_against_evidence()
            # rejects invalid tools. Do not substitute repo_capabilities here: that
            # would let 3572 replace planner reasoning with a hidden controller step.
            return finalize_agentic_job(
                job_id, state, "blocked_needs_attention",
                f"Planner selected invalid tool: {tool or '<empty>'}.",
                {"history": history, "blocked_by": "invalid_planner_tool", "planner_decision": decision},
            )

        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
        if repeated_tool_call_count(history, tool, internal_args) >= 2:
            append_repeat_guard_result(step, decision, tool, internal_args)
            continue

        cache_key = _tool_cache_key(tool, internal_args)
        hit = _tool_cache_hit(history, tool, internal_args)
        if hit:
            effective_cache_key = cache_key or str(hit.get("cache_key") or "")
            append_cached_tool_result(
                step,
                decision,
                {
                    "tool": tool,
                    "arguments": internal_args,
                    "cache_key": effective_cache_key,
                    "result": _cached_tool_result(hit, effective_cache_key),
                },
            )
            continue

        # approval gate
        allowed, block_reason = _agentic_tool_allowed(tool, internal_args, approval_mode)
        if not allowed:
            append_agent_event(job_id, "tool_blocked", block_reason, {"tool": tool}, step=step)
            return finalize_agentic_job(
                job_id, state, "blocked_needs_consent", block_reason,
                {"history": history, "blocked_tool": tool},
            )

        state["status_message"] = f"executing {tool}"
        write_agent_job_state(state)
        append_agent_event(job_id, "tool_start", f"Executing {tool}",
                            {"tool": tool, "arguments": internal_args}, step=step)

        result = dispatch_tool(
            tool, internal_args, root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        tool_result_path = root / "tool-results" / f"step-{step:03d}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {})
        compact_result["artifact"] = str(tool_result_path)
        if cache_key and bool(compact_result.get("ok")):
            compact_result["cache_key"] = cache_key
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}",
                            compact_result, step=step)

        row = {
            "step": step,
            "decision": {k: v for k, v in decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

        # No controller_auto_final here: the next planner step must inspect the
        # structured evidence and decide whether to continue, read more, or final.

    return finalize_agentic_job(
        job_id, state, "max_steps_reached",
        f"Max steps reached ({max_steps}) before planner produced a final answer.",
        {"history": history},
    )


def _agentic_tool_allowed(
    tool: str, args: dict[str, Any], approval_mode: str
) -> tuple[bool, str]:
    mode = str(approval_mode or "safe_write_lab").lower()
    readonly_modes = {"read_only", "readonly", "no_write", "dry_run"}
    if tool in {"repo_apply_patch", "repo_write_file"} and mode in {
        "read_only", "readonly", "no_write", "dry_run"
    }:
        return False, f"{tool} blocked by read_only approval_mode"
    if (
        tool == "runtime_sqlite_memory_cleanup"
        and bool(args.get("apply"))
        and mode in readonly_modes
    ):
        return False, "runtime_sqlite_memory_cleanup apply blocked by read_only approval_mode"
    if tool == "repo_command":
        from .repo_tools import dangerous_command  # noqa: PLC0415
        if mode in readonly_modes and dangerous_command(
            str(args.get("command") or "")
        ):
            return False, "dangerous repo_command blocked by read_only approval_mode"
    return True, ""
