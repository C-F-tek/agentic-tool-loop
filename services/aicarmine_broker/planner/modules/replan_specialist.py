"""
replan_specialist.py

Extracted from planner.py for simplicity and maintainability.
Contains replan specialist functions for validator rejection handling.

Dependencies: This module requires several helper functions that are
imported from planner.py at runtime via the __init__.py or direct imports.
"""
from __future__ import annotations

from typing import Any


def _validation_needs_replan_specialist(
    violations: list[Any],
    contract: dict[str, Any],
    decision: dict[str, Any],
) -> bool:
    text = " ".join(str(value or "") for value in violations).lower()
    code_contract = contract.get("code_product_contract") if isinstance(contract, dict) else {}
    tool = str(decision.get("tool") or "").strip()
    if isinstance(code_contract, dict) and (code_contract.get("required") or code_contract.get("route_shift_after_payload_rejection")):
        return True
    if tool in {"repo_propose_code_edit", "planner_scratchpad_write", "planner_scratchpad_read"} and any(
        token in text
        for token in (
            "code_product",
            "repo_propose_code_edit",
            "planner_scratchpad",
            "support",
            "ready_without_complete_payload",
        )
    ):
        return True
    return any(
        token in text
        for token in (
            "planner_repeated_invalid_code_product_decision",
            "invalid_code_product_candidate",
            "code_product_route_shift_required",
            "support_subturn_validation_failed",
            "repo_read_window_already_successful_without_progress",
            "planner_scratchpad_window_already_successful_without_progress",
            "repo_read_already_successful",
            "required_next_tool_call_pending",
            "required_next_tool_call_from_previous_guard",
            "ignores_pending_actions",
            "inconsistent_flow_mapping",
            "duplicate_window",
        )
    )


def _sanitize_replan_required_next_tool_call(value: Any) -> dict[str, Any]:
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


def _replan_contract_path_items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        items = value.get("items")
        return items if isinstance(items, list) else []
    if isinstance(value, list):
        return value
    return []


def _replan_repo_path_token(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("path") or value.get("source_path") or ""
    token = str(value or "").strip().replace("\\", "/")
    while token.startswith("./"):
        token = token[2:]
    return token


def _replan_contract_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
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

    final_contract = contract.get("finalization_contract") if isinstance(contract, dict) else {}
    coverage = (
        final_contract.get("minimum_read_coverage")
        if isinstance(final_contract, dict) and final_contract.get("minimum_read_coverage")
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        for item in _replan_contract_path_items(coverage.get(key)):
            add(item)

    return known


def _replan_known_repo_dirs(paths: set[str]) -> set[str]:
    dirs = {"."}
    for path in paths:
        parts = [part for part in str(path).split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _replan_route_token_is_prose_or_metric(token: str) -> bool:
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
    required_call["validated"] = True
    required_call["validation_source"] = source
    result["required_next_tool_call"] = required_call
    result["required_next_tool_call_validated"] = True
    result["required_next_tool_call_validation_source"] = source
    return result


def _replan_required_repo_read_paths(args: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    if not isinstance(args, dict):
        return out
    if args.get("path") not in (None, "", [], {}):
        out.append(args.get("path"))
    raw_paths = args.get("paths")
    if isinstance(raw_paths, list):
        out.extend(raw_paths)
    return out


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
    tool = str(required_call.get("tool") or "").strip()
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


def planner_replan_specialist_for_validation(
    *,
    goal: str,
    decision: dict[str, Any],
    validation: dict[str, Any],
    prevalidation_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    violations = _list_or_empty(validation.get("violations"))
    contract = _dict_or_empty(validation.get("evidence_contract"))
    if not _validation_needs_replan_specialist(violations or [], contract, decision):
        return {}
    code_contract = _dict_or_empty(contract.get("code_product_contract"))
    replan_role = "code_product_replan" if code_contract.get("required") else "planner_replan"
    request_payload = {
        "schema": "planner_replan_specialist_request.v1",
        "task": "route_next_planner_turn_after_validator_rejection",
        "goal": str(goal or ""),
        "rejected_decision": _prompt_clip_value(
            {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
            text_limit=1600,
            list_limit=6,
        ),
        "validator_violations": violations,
        "evidence_contract": _compact_vulkan_repair_evidence_contract(contract),
        "repo_read_allowlist": sorted(_replan_contract_repo_read_allowlist(contract))[:48],
        "role_guidance": role_guidance_for_goal(replan_role, goal),
        "rules": [
            "Return strict JSON only.",
            "Do not execute tools and do not invent payload content.",
            "The next planner turn must still emit the action; validator remains authoritative.",
            "For code-product replan, choose either a complete repo_propose_code_edit in the next planner turn or a typed block.",
            "For repo-analysis replan, never convert duplicate-read/final-quality failures into repo_propose_code_edit or code_product_build_state.",
            "If the rejected required_next_tool_call is already satisfied, set required_next_progress toward final rewrite or one different concrete evidence gap.",
            "If prevalidation_feedback is present, do not repeat the rejected route. Choose one different valid route or omit required_next_tool_call.",
            "Use required_next_tool_call only for a concrete read/search/window route, never for invented code edits.",
            "repo_read_allowlist contains only unread validator-admissible paths; if it is empty, do not choose repo_read.",
            "For repo_read, choose only paths listed in repo_read_allowlist; prose, metrics, headings, concepts, and already-read files must become required_next_progress or a search query.",
        ],
        "allowed_required_next_tools": sorted(_REPLAN_SPECIALIST_ROUTE_TOOLS),
        "required_json_shape": {
            "decision": "continue_required | block_recommended | retry_same_context",
            "required_next_progress": "one concise instruction for the next planner turn",
            "required_next_tool_call": {
                "tool": "repo_read | repo_semantic_search | repo_rg_search | repo_search | repo_list_files | planner_scratchpad_read",
                "arguments": {"path": "or query/document selector"},
                "reason": "why this route is required",
            },
            "rationale": "short reason",
        },
    }
    return request_payload


# Type aliases and constants used by extracted functions
_REPLAN_SPECIALIST_ROUTE_TOOLS = {
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
    "planner_scratchpad_read",
}

_FINAL_QUALITY_ROUTE_TOOLS = {
    "repo_read",
    "repo_semantic_search",
    "repo_rg_search",
    "repo_search",
    "repo_list_files",
}

# These are imported from planner.py at runtime
from ...planner import (
    _list_or_empty,
    _dict_or_empty,
    _prompt_clip_text,
    _prompt_clip_value,
    _compact_vulkan_repair_evidence_contract,
    role_guidance_for_goal,
)