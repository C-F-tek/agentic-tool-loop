"""Intra-job planner cache helpers.
from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)


The cache is history-only: it reuses successful read-only tool results and
successful Vulkan repair decisions already present in the same job history.
It does not execute tools, repair text, or persist global state.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from ..application.shared.path_tokens import repo_rel_token as _repo_rel_token
from ..config import VALID_INTERNAL_TOOLS
from ..tool_contract import normalize_tool_name as _normalize_tool_name


def _decision_paths(args: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    if isinstance(args.get("paths"), list):
        paths.extend(str(x) for x in args["paths"] if str(x).strip())
    if args.get("path"):
        paths.append(str(args.get("path")))
    if isinstance(args.get("items"), list):
        for item in args["items"]:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
            elif isinstance(item, str):
                paths.append(item)
    out: list[str] = []
    for path in paths:
        n = _repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
    if not isinstance(decision, dict):
        return ""
    return str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )


CACHEABLE_READ_TOOLS = frozenset({
    "repo_capabilities",
    "repo_status",
    "repo_tree",
    "repo_list_files",
    "repo_search",
    "repo_rg_search",
    "repo_semantic_search",
    "repo_read",
    "terminal_list_files",
    "terminal_search_files",
    "planner_scratchpad_read",
    "runtime_sqlite_memory_search",
})

CACHE_IGNORED_ARG_KEYS = frozenset({
    "public_tool_name",
    "public_tool_x",
    "original_30b_arguments",
    "called_by_30b",
    "tool_name",
    "tool_result_for",
    "operation_id",
    "reason",
    "summary",
    "preview",
    "raw_preview",
    "raw_text_preview",
    "raw_planner_text",
    "raw_planner_text_preview",
    "raw_planner_text_before_repair",
    "repaired_by_vulkan_gpu0_11435",
    "original_planner_decision",
    "vulkan_repair",
    "repair_cache_key",
    "repair_cache_hit",
    "cache_key",
    "cache_hit",
    "cached_from_step",
    "cached_from_artifact",
})


def _read_only_tool_cacheable(tool: str) -> bool:
    return _normalize_tool_name(tool) in CACHEABLE_READ_TOOLS


def _cache_normalized_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _cache_normalized_value(sub)
            for key, sub in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in CACHE_IGNORED_ARG_KEYS
            and sub not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_cache_normalized_value(sub) for sub in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _cache_normalized_path(value: Any) -> str:
    return _repo_rel_token(value)


def _cache_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _cache_effective_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = _normalize_tool_name(tool)
    source = args if isinstance(args, dict) else {}
    effective = {
        str(key): value
        for key, value in source.items()
        if str(key) not in CACHE_IGNORED_ARG_KEYS
        and value not in (None, "", [], {})
    }

    if tool in {"repo_capabilities", "repo_status"}:
        effective = {}
    elif tool == "repo_tree":
        effective["path"] = _cache_normalized_path(effective.get("path") or ".")
        effective["max_depth"] = _cache_int(effective.get("max_depth") or 3, 3)
        effective["max_files"] = _cache_int(effective.get("max_files") or 200, 200)
    elif tool == "repo_list_files":
        effective["path"] = _cache_normalized_path(effective.get("path") or ".")
        if "suffix" in effective:
            effective["suffix"] = str(effective.get("suffix") or "")
        if "extension" in effective:
            effective["extension"] = str(effective.get("extension") or "")
        effective["limit"] = _cache_int(effective.get("limit") or effective.get("max_files") or 20, 20)
        effective["max_files"] = _cache_int(effective.get("max_files") or effective.get("limit") or 20, 20)
        effective["max_depth"] = _cache_int(effective.get("max_depth") or 50, 50)
        if "core" in effective:
            effective["core"] = bool(effective.get("core"))
    elif tool == "repo_search":
        if "pattern" in effective and "query" not in effective:
            effective["query"] = effective.pop("pattern")
        if "symbol" in effective and "query" not in effective:
            effective["query"] = effective.pop("symbol")
        effective["query"] = str(effective.get("query") or "")
        effective["path"] = _cache_normalized_path(effective.get("path") or ".")
        effective["mode"] = str(effective.get("mode") or "rg")
        effective["max_results"] = _cache_int(effective.get("max_results") or 80, 80)
    elif tool == "repo_rg_search":
        if "pattern" not in effective and "query" in effective:
            effective["pattern"] = effective.pop("query")
        effective = {
            "pattern": str(effective.get("pattern") or ""),
            "path": _cache_normalized_path(effective.get("path") or "."),
        }
    elif tool == "repo_semantic_search":
        effective["query"] = str(effective.get("query") or "")
        effective["path"] = _cache_normalized_path(effective.get("path") or ".")
        effective["limit"] = _cache_int(
            effective.get("limit") or effective.get("top_k") or effective.get("max_results") or 8,
            8,
        )
        default_candidate_limit = max(40, int(effective["limit"]) * 8)
        effective["candidate_limit"] = _cache_int(
            effective.get("candidate_limit") or default_candidate_limit,
            default_candidate_limit,
        )
        effective["max_chunk_chars"] = _cache_int(
            effective.get("max_chunk_chars") or effective.get("max_chars") or 1200,
            1200,
        )
        effective["rerank"] = bool(effective.get("rerank", True))
        effective["rerank_candidate_limit"] = _cache_int(
            effective.get("rerank_candidate_limit") or min(default_candidate_limit, 12),
            min(default_candidate_limit, 12),
        )
        effective["rerank_doc_chars"] = _cache_int(effective.get("rerank_doc_chars") or 2500, 2500)
        effective["rerank_timeout_seconds"] = _cache_int(
            effective.get("rerank_timeout_seconds") or 30,
            30,
        )
        effective["reindex"] = bool(effective.get("reindex", True))
        effective.pop("top_k", None)
        effective.pop("max_results", None)
        effective.pop("max_chars", None)
    elif tool == "repo_read":
        paths = _decision_paths(effective)
        if len(paths) == 1:
            effective = {"path": paths[0]}
        elif paths:
            effective = {"paths": paths}
        else:
            effective = {}
        for key in ("line", "before", "after"):
            if key in source and source.get(key) not in (None, ""):
                effective[key] = _cache_int(source.get(key), 0)
        effective["max_chars"] = _cache_int(source.get("max_chars") or 20000, 20000)
    elif tool == "terminal_list_files":
        directory = effective.get("directory") or effective.get("path") or ""
        if directory:
            effective["directory"] = str(directory).replace("\\", "/").rstrip("/") or "."
        effective.pop("path", None)
        effective["pattern"] = str(effective.get("pattern") or "*")
        effective["recurse"] = bool(effective.get("recurse") or False)
        effective["limit"] = _cache_int(effective.get("limit") or 200, 200)
    elif tool == "terminal_search_files":
        directory = effective.get("directory") or effective.get("path") or ""
        if directory:
            effective["directory"] = str(directory).replace("\\", "/").rstrip("/") or "."
        effective.pop("path", None)
        effective["query"] = str(effective.get("query") or "")
        effective["content"] = bool(effective.get("content") or False)
        effective["limit"] = _cache_int(effective.get("limit") or 200, 200)
    elif tool == "planner_scratchpad_read":
        kind = str(effective.get("kind") or "")
        if (
            kind in {"prompt_context", "prompt_context_window"}
            or effective.get("document_id") not in (None, "")
            or effective.get("id") not in (None, "")
            or effective.get("section") not in (None, "")
            or effective.get("offset") not in (None, "")
        ):
            effective["kind"] = "prompt_context_window"
            effective["document_id"] = str(effective.get("document_id") or effective.get("id") or "")
            effective.pop("id", None)
            effective["section"] = str(effective.get("section") or effective.get("tag") or "")
            effective["query"] = str(effective.get("query") or "")
            effective["offset"] = _cache_int(effective.get("offset") or 0, 0)
            effective["max_chars"] = _cache_int(effective.get("max_chars") or 3000, 3000)
            effective["limit"] = _cache_int(effective.get("limit") or 3, 3)
            effective.pop("tag", None)
        else:
            effective["query"] = str(effective.get("query") or "")
            effective["tag"] = str(effective.get("tag") or "")
            effective["limit"] = _cache_int(effective.get("limit") or 50, 50)
    elif tool == "runtime_sqlite_memory_search":
        effective["query"] = str(effective.get("query") or "")
        effective["kind"] = str(effective.get("kind") or "")
        effective["tag"] = str(effective.get("tag") or "")
        effective["limit"] = _cache_int(effective.get("limit") or 50, 50)
        if "db" in effective:
            effective["db"] = str(effective.get("db") or "")

    return _cache_normalized_value(effective)


def _tool_cache_key(tool: str, args: dict[str, Any]) -> str:
    tool = _normalize_tool_name(tool)
    if not _read_only_tool_cacheable(tool):
        return ""
    return json.dumps(
        {"tool": tool, "arguments": _cache_effective_args(tool, args)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _tool_cache_hit(
    history: list[dict[str, Any]],
    tool: str,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    cache_key = _tool_cache_key(tool, args)
    if not cache_key:
        return None
    tool = _normalize_tool_name(tool)
    requested_repo_read_paths = _decision_paths(args) if tool == "repo_read" else []
    repo_read_has_window = any(str(key) in args and args.get(key) not in (None, "") for key in ("line", "before", "after"))
    for item in reversed(history or []):
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if _normalize_tool_name(str(result.get("tool") or "")) != tool:
            continue
        if not bool(result.get("ok")):
            continue
        stored_key = ""
        if not (
            tool == "planner_scratchpad_read"
            and str(result.get("mode") or "") == "prompt_context_window"
        ):
            stored_key = str(result.get("cache_key") or "")
        if not stored_key:
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            decision_args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
            stored_key = _tool_cache_key(tool, decision_args)
        if stored_key == cache_key:
            return {
                "step": item.get("step"),
                "artifact": result.get("artifact"),
                "result": result,
                "cache_key": cache_key,
            }
        if (
            tool == "repo_read"
            and requested_repo_read_paths
            and not repo_read_has_window
            and _repo_read_result_covers_paths(result, requested_repo_read_paths)
        ):
            return {
                "step": item.get("step"),
                "artifact": result.get("artifact"),
                "result": result,
                "cache_key": cache_key,
            }
    return None


def _repo_read_result_covers_paths(result: dict[str, Any], requested_paths: list[str]) -> bool:
    if not requested_paths:
        return False
    items = result.get("items")
    if not isinstance(items, list):
        return False
    by_path: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        path = _repo_rel_token(item.get("path") or "")
        if path:
            by_path[path] = item
    for requested in requested_paths:
        item = by_path.get(_repo_rel_token(requested))
        if not item or not bool(item.get("ok")):
            return False
        if bool(item.get("truncated")):
            return False
    return True


def _cached_tool_result(hit: dict[str, Any], cache_key: str) -> dict[str, Any]:
    result = copy.deepcopy(hit.get("result") if isinstance(hit.get("result"), dict) else {})
    result["cache_hit"] = True
    result["cache_key"] = cache_key
    result["cached_from_step"] = hit.get("step")
    if hit.get("artifact"):
        result["cached_from_artifact"] = hit.get("artifact")
    return result


def _tool_cache_hit_for_decision(
    *,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    original_args: dict[str, Any],
    public_tool_name: str,
) -> dict[str, Any] | None:
    from ..tool_contract import normalize_tool_name, sanitize_tool_args  # noqa: PLC0415

    if not isinstance(decision, dict):
        return None
    action = str(decision.get("action") or "tool").strip().lower()
    if action != "tool":
        return None
    tool = normalize_tool_name(str(decision.get("tool") or ""))
    if tool not in VALID_INTERNAL_TOOLS or not _read_only_tool_cacheable(tool):
        return None
    raw_args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    internal_args = sanitize_tool_args(tool, dict(raw_args), original_args, public_tool_name)
    hit = _tool_cache_hit(history, tool, internal_args)
    if not hit:
        return None
    cache_key = str(hit.get("cache_key") or _tool_cache_key(tool, internal_args))
    return {
        "tool": tool,
        "arguments": internal_args,
        "cache_key": cache_key,
        "result": _cached_tool_result(hit, cache_key),
    }


def repeated_tool_call_count(
    history: list[dict[str, Any]], tool: str, args: dict[str, Any]
) -> int:
    tool = _normalize_tool_name(tool)
    wanted_cache_key = _tool_cache_key(tool, args)
    wanted = json.dumps(
        {"tool": tool, "arguments": args},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    count = 0
    for item in history:
        if not isinstance(item, dict) or not isinstance(item.get("decision"), dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        candidates = [item["decision"]]
        for source in (item["decision"], result):
            rejected = source.get("rejected_decision") if isinstance(source.get("rejected_decision"), dict) else {}
            if rejected:
                candidates.append(rejected)
        for decision in candidates:
            decision_tool = _normalize_tool_name(str(decision.get("tool") or ""))
            if decision_tool != tool:
                continue
            decision_args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
            if wanted_cache_key and _tool_cache_key(decision_tool, decision_args) == wanted_cache_key:
                count += 1
                break
            if json.dumps(
                {"tool": decision_tool, "arguments": decision_args},
                ensure_ascii=False, sort_keys=True, default=str,
            ) == wanted:
                count += 1
                break
    return count


def _repair_cache_key(raw_planner_text: str) -> str:
    raw = str(raw_planner_text or "")
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _cached_vulkan_repair_result(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = _repair_cache_key(raw_planner_text)
    if not repair_key:
        return None
    for item in reversed(history or []):
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
        if not repair or not bool(repair.get("ok")):
            continue
        if str(repair.get("repair_cache_key") or "") != repair_key:
            continue
        repaired_decision = repair.get("repaired_decision")
        if not isinstance(repaired_decision, dict) or not repaired_decision:
            continue
        return {
            "ok": True,
            "repaired_decision": copy.deepcopy(repaired_decision),
            "raw_text_preview": repair.get("raw_text_preview"),
            "raw_planner_text_preview": repair.get("raw_planner_text_preview"),
            "repair_cache_key": repair_key,
            "repair_cache_hit": True,
            "cached_from_step": item.get("step"),
        }
    return None
