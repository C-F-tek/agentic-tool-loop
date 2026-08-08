"""Planner replan specialist helpers extracted from planner.py.

This module owns:
- _specialist_route_audit
- _sanitize_replan_required_next_tool_call
- _sanitize_replan_specialist_response
- _replan_contract_path_items
- _replan_repo_path_token
- _replan_contract_repo_read_allowlist
- _replan_contract_known_repo_paths
- _replan_known_repo_dirs
- _replan_route_token_is_prose_or_metric
- _replan_search_query_is_concrete
- _mark_replan_required_call_validated
- _replan_required_repo_read_paths
- _sanitize_replan_specialist_result_against_contract
- planner_replan_specialist_for_validation
"""
from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Replan specialist route tools (constants)
# ---------------------------------------------------------------------------

_REPLAN_SPECIALIST_ROUTE_TOOLS = frozenset({
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
    "planner_scratchpad_read",
})

_FINAL_QUALITY_ROUTE_TOOLS = frozenset({
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
})


def _list_or_empty(value: Any) -> list:
    """Safely return a list or empty list."""
    if isinstance(value, list):
        return value
    return []


def _dict_or_empty(value: Any) -> dict:
    """Safely return a dict or empty dict."""
    if isinstance(value, dict):
        return value
    return {}


def _prompt_clip_text(text: str, limit: int = 12000) -> str:
    """Clip text to limit characters."""
    if not isinstance(text, str):
        return ""
    return text[:limit]


def _prompt_clip_value(value: Any, *, text_limit: int = 12000, list_limit: int = 8) -> Any:
    """Clip a value (text or list) to specified limits."""
    if isinstance(value, list):
        clipped = [str(v) for v in value[:list_limit]]
        return clipped
    return _prompt_clip_text(str(value or ""), text_limit)


def _normalize_tool_name(value: str) -> str:
    """Normalize tool name to canonical form."""
    return str(value or "").strip().lower()


# ---------------------------------------------------------------------------
# Specialist route audit
# ---------------------------------------------------------------------------

def _specialist_route_audit(
    required_call: Any,
    history: list[dict[str, Any]],
    *,
    source: str,
    allowed_tools: set[str] | None = None,
) -> dict[str, Any]:
    """Audit a required_next_tool_call for replan specialist validity."""
    allowed = allowed_tools or _REPLAN_SPECIALIST_ROUTE_TOOLS
    if not isinstance(required_call, dict):
        return {
            "schema": "specialist_route_audit.v1",
            "accepted": False,
            "source": source,
            "rejected_reason": "required_next_tool_call_invalid_shape",
            "safe_feedback": "Do not provide a required_next_tool_call unless it is a valid object.",
            "diagnostic_only": True,
        }
    tool = _normalize_tool_name(str(required_call.get("tool") or ""))
    raw_args = required_call.get("arguments")
    args = raw_args if isinstance(raw_args, dict) else {}
    audit: dict[str, Any] = {
        "schema": "specialist_route_audit.v1",
        "accepted": False,
        "source": source,
        "tool": tool,
        "arguments": args,
    }
    if not tool or tool not in allowed:
        audit.update({
            "rejected_reason": "tool_not_allowed_for_specialist_route",
            "allowed_tools": sorted(allowed),
            "safe_feedback": (
                "Choose only an allowed read/search route, or omit required_next_tool_call "
                "and instruct the planner to rewrite final/block from existing evidence."
            ),
            "diagnostic_only": True,
        })
        return audit
    if not args:
        audit.update({
            "rejected_reason": "missing_route_arguments",
            "safe_feedback": (
                "Provide concrete arguments for the required route, or omit required_next_tool_call "
                "and use required_next_progress only."
            ),
            "diagnostic_only": True,
        })
        return audit
    # Satisfaction check delegated to caller via deps
    audit["satisfaction_check_pending"] = True
    audit["accepted"] = True
    audit["rejected_reason"] = ""
    audit["normalized_route"] = {"tool": tool, "arguments": args}
    return audit


# ---------------------------------------------------------------------------
# Sanitize replan tool calls
# ---------------------------------------------------------------------------

def _sanitize_replan_required_next_tool_call(value: Any) -> dict[str, Any]:
    """Sanitize a required_next_tool_call for replan specialist output."""
    if not isinstance(value, dict):
        return {}
    tool = str(value.get("tool") or "").strip()
    if tool not in _REPLAN_SPECIALIST_ROUTE_TOOLS:
        return {}
    raw_args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
    allowed_args = {
        "repo_read": {
            "path", "paths", "line", "line_start", "line_count", "start_line",
            "end_line", "before", "after", "max_chars",
        },
        "repo_semantic_search": {
            "query", "path", "limit", "top_k", "max_results", "candidate_limit",
            "rerank", "reindex", "max_chunk_chars",
        },
        "repo_rg_search": {"query", "pattern", "path", "max_results", "context"},
        "repo_search": {"query", "pattern", "symbol", "path", "max_results"},
        "repo_list_files": {"path", "limit", "suffix", "glob", "max_files"},
        "planner_scratchpad_read": {
            "kind", "document_id", "offset", "max_chars", "target_file",
            "section", "line_start", "line_count",
        },
    }.get(tool, set())
    args = {
        key: raw_args.get(key)
        for key in allowed_args
        if raw_args.get(key) not in (None, "", [], {})
    }
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"} and not (
        args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
    ):
        return {}
    if tool == "repo_read" and not (args.get("path") or args.get("paths")):
        return {}
    if tool == "planner_scratchpad_read" and not (
        args.get("document_id") or args.get("target_file") or args.get("section")
    ):
        return {}
    reason = str(value.get("reason") or "").strip()
    return {
        "tool": tool,
        "arguments": args,
        "reason": _prompt_clip_text(reason, 500) if reason else "replan_specialist_required_next_tool_call",
        "source": "planner_replan_specialist",
    }


def _sanitize_replan_specialist_response(value: Any) -> dict[str, Any]:
    """Sanitize a replan specialist JSON response."""
    base = {
        "schema": "planner_replan_specialist_result.v1",
        "available": False,
        "ok": False,
        "decision": "invalid",
    }
    if not isinstance(value, dict):
        return {**base, "error": "invalid_json_object"}
    decision = str(value.get("decision") or "").strip().lower()
    if decision not in {"continue_required", "block_recommended", "retry_same_context"}:
        return {**base, "raw_decision": _prompt_clip_value(value, text_limit=500, list_limit=6)}
    required_next_progress = str(value.get("required_next_progress") or "").strip()
    if not required_next_progress:
        return {**base, "decision": decision, "error": "missing_required_next_progress"}
    required_next_tool_call = _sanitize_replan_required_next_tool_call(value.get("required_next_tool_call"))
    return {
        "schema": "planner_replan_specialist_result.v1",
        "available": True,
        "ok": True,
        "decision": decision,
        "required_next_progress": _prompt_clip_text(required_next_progress, 1000),
        "required_next_tool_call": required_next_tool_call,
        "rationale": _prompt_clip_text(value.get("rationale"), 600),
        "confidence": value.get("confidence"),
    }


# ---------------------------------------------------------------------------
# Replan contract path helpers
# ---------------------------------------------------------------------------

def _replan_contract_path_items(value: Any) -> list[Any]:
    """Extract path items from a replan contract value."""
    if isinstance(value, dict):
        items = value.get("items")
        return items if isinstance(items, list) else []
    if isinstance(value, list):
        return value
    return []


def _replan_repo_path_token(value: Any) -> str:
    """Convert a replan contract value to a repo-relative path token."""
    if isinstance(value, dict):
        value = value.get("path") or value.get("source_path") or ""
    token = str(value or "").strip().replace("\\", "/")
    while token.startswith("./"):
        token = token[2:]
    return token


def _replan_contract_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    """Compute the allowed repo_read paths from a replan contract."""
    contract = contract if isinstance(contract, dict) else {}
    allowed: set[str] = set()
    completed: set[str] = set()

    def add_token(target: set[str], item: Any) -> None:
        token = _replan_repo_path_token(item)
        if token:
            target.add(token)

    for key in ("validator_admissible_repo_read_paths", "read_admissible_paths"):
        for item in _replan_contract_path_items(contract.get(key)):
            add_token(allowed, item)

    for key in ("successful_repo_read_paths", "verified_content_reads"):
        for item in _replan_contract_path_items(contract.get(key)):
            add_token(completed, item)

    for row in _replan_contract_path_items(contract.get("stale_required_next_tool_calls")):
        if not isinstance(row, dict):
            continue
        args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
        for item in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
            add_token(completed, item)

    return allowed - completed


def _replan_contract_known_repo_paths(contract: dict[str, Any]) -> set[str]:
    """Compute all known repo paths from a replan contract."""
    contract = contract if isinstance(contract, dict) else {}
    known: set[str] = set()

    def add(item: Any) -> None:
        token = _replan_repo_path_token(item)
        if token:
            known.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        for item in _replan_contract_path_items(contract.get(key)):
            add(item)

    for item in _replan_contract_path_items(contract.get("verified_content_reads")):
        add(item)

    final_contract = _dict_or_empty(contract.get("finalization_contract"))
    coverage = _dict_or_empty(
        final_contract.get("minimum_read_coverage")
        or contract.get("minimum_read_coverage")
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _replan_contract_path_items(coverage.get(key)):
            add(item)

    return known


def _replan_known_repo_dirs(paths: set[str]) -> set[str]:
    """Extract directory prefixes from a set of repo paths."""
    dirs = {"."}
    for path in paths:
        parts = [part for part in path.split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _replan_route_token_is_prose_or_metric(token: str) -> bool:
    """Check if a replan route token looks like prose or a metric rather than a concrete path."""
    token = str(token or "").strip()
    if not token:
        return True
    lowered = token.lower()
    if lowered in {
        "ridondanze/rischi",
        "docs/config",
        "planner/final-quality",
        "planner/controller rejection paths",
    }:
        return True
    if any(sep in lowered for sep in (":\\", "://")):
        return True
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if compact.isdigit() and "/" in lowered:
        return True
    if " " in token and not any(token.endswith(suffix) for suffix in (".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt")):
        return True
    return False


def _replan_search_query_is_concrete(value: Any) -> bool:
    """Check if a replan search query is concrete enough for use."""
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if len(text) > 260:
        return False
    if _replan_route_token_is_prose_or_metric(text):
        return False
    if lowered in {"docs/config", "ridondanze/rischi", "8/2", "8/8", "9/9"}:
        return False
    useful_tokens = [
        token
        for token in lowered.replace(",", " ").replace(";", " ").split()
        if len(token) >= 3 and "/" not in token and any(ch.isalpha() for ch in token)
    ]
    if "/" in lowered and len(useful_tokens) < 2:
        return False
    return bool(useful_tokens)


def _mark_replan_required_call_validated(
    result: dict[str, Any],
    required_call: dict[str, Any],
    *,
    source: str = "planner_replan_specialist_sanitizer",
) -> dict[str, Any]:
    """Mark a replan required call as validated."""
    required_call["validated"] = True
    required_call["validation_source"] = source
    result["required_next_tool_call"] = required_call
    result["required_next_tool_call_validated"] = True
    result["required_next_tool_call_validation_source"] = source
    return result


def _replan_required_repo_read_paths(args: dict[str, Any]) -> list[Any]:
    """Extract repo_read paths from replan arguments."""
    out: list[Any] = []
    if not isinstance(args, dict):
        return out
    if args.get("path") not in (None, "", [], {}):
        out.append(args.get("path"))
    raw_paths = args.get("paths")
    if isinstance(raw_paths, list):
        out.extend(raw_paths)
    return out


# ---------------------------------------------------------------------------
# Sanitize replan specialist result against contract
# ---------------------------------------------------------------------------

def _sanitize_replan_specialist_result_against_contract(
    result: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Do not let replan specialist turn prose/metrics into required routes."""
    result = result if isinstance(result, dict) else {}
    if result.get("ok") is not True:
        return result

    required_call = (
        result.get("required_next_tool_call")
        if isinstance(result.get("required_next_tool_call"), dict)
        else {}
    )
    tool = _normalize_tool_name(str(required_call.get("tool") or ""))
    if not tool:
        return result

    args = (
        required_call.get("arguments")
        if isinstance(required_call.get("arguments"), dict)
        else {}
    )
    known_paths = _replan_contract_known_repo_paths(contract)
    known_dirs = _replan_known_repo_dirs(known_paths)

    if tool == "repo_read":
        raw_paths = _replan_required_repo_read_paths(args)
        allowed_paths = _replan_contract_repo_read_allowlist(contract)

        valid_paths: list[str] = []
        invalid_paths: list[str] = []
        for raw_path in raw_paths:
            token = _replan_repo_path_token(raw_path)
            if token and token in allowed_paths:
                if token not in valid_paths:
                    valid_paths.append(token)
            elif token and token not in invalid_paths:
                invalid_paths.append(token)

        if invalid_paths:
            result["invalid_required_next_tool_call_paths"] = invalid_paths[:12]
            result["invalid_required_next_tool_call_reason"] = (
                "planner_replan_specialist proposed repo_read paths that are not "
                "known/admissible repo paths in the current evidence contract"
            )

        if valid_paths:
            required_call["arguments"] = {"paths": valid_paths[:12]}
            return _mark_replan_required_call_validated(result, required_call)

        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        if invalid_paths:
            result["decision"] = "block_recommended"
            result["required_next_progress"] = (
                "Replan specialist proposed no valid existing repo_read path. "
                "Do not call repo_read for prose, metrics, headings, or non-existing paths. "
                "Use verified evidence for a terminal answer if allowed, or return a typed block."
            )
        return result

    if tool == "repo_list_files":
        path_token = _replan_repo_path_token(args.get("path") or ".") or "."
        if path_token == "." or (path_token in known_dirs and not _replan_route_token_is_prose_or_metric(path_token)):
            args["path"] = path_token
            required_call["arguments"] = args
            return _mark_replan_required_call_validated(result, required_call)
        result["invalid_required_next_tool_call_paths"] = [path_token]
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed repo_list_files path that is not "
            "a known concrete repo directory in the current evidence contract"
        )
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not list files for prose, metrics, headings, or unknown path tokens. "
            "Use verified evidence for final/block, or provide a concrete search query."
        )
        return result

    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query_value = args.get("query") or args.get("pattern") or args.get("symbol")
        if _replan_search_query_is_concrete(query_value):
            path_token = _replan_repo_path_token(args.get("path")) if args.get("path") else ""
            if path_token and path_token not in known_dirs and path_token not in known_paths:
                result["invalid_required_next_tool_call_paths"] = [path_token]
                args.pop("path", None)
            required_call["arguments"] = args
            return _mark_replan_required_call_validated(result, required_call)
        result["invalid_required_next_tool_call_query"] = str(query_value or "").strip()[:260]
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed a search query that looks like a "
            "heading, metric, violation label, or path token rather than a concrete query"
        )
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not lock the next turn on a weak search query. Rewrite from verified "
            "evidence if possible, or provide a concrete semantic query in prose-free form."
        )
        return result

    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = _replan_repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        section = str(args.get("section") or "").strip()
        if document_id and not _replan_route_token_is_prose_or_metric(document_id):
            return _mark_replan_required_call_validated(result, required_call)
        if target_file and target_file in known_paths:
            return _mark_replan_required_call_validated(result, required_call)
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed planner_scratchpad_read without a "
            "known document_id or verified target_file"
        )
        if target_file:
            result["invalid_required_next_tool_call_paths"] = [target_file]
        elif section:
            result["invalid_required_next_tool_call_query"] = section[:260]
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not lock rewrite recovery on an unverified scratchpad selector. "
            "Use verified evidence for final/block, or request a concrete known window."
        )
        return result

    result["required_next_tool_call"] = {}
    result["required_next_tool_call_validated"] = False
    result["invalid_required_next_tool_call_reason"] = (
        "planner_replan_specialist proposed a route that has no deterministic validator proof"
    )
    return result


# ---------------------------------------------------------------------------
# Main replan specialist function
# ---------------------------------------------------------------------------

def planner_replan_specialist_for_validation(
    *,
    goal: str,
    decision: dict[str, Any],
    validation: dict[str, Any],
    prevalidation_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the replan specialist for validator rejection evidence.
    
    This is a stub - full implementation remains in planner.py.
    """
    # TODO: Full implementation
    return {
        "schema": "planner_replan_specialist_result.v1",
        "available": False,
        "ok": False,
        "decision": "unavailable",
        "error": "implementation_moved_to_planner.py",
    }