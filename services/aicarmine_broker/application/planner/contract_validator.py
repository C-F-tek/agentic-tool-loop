"""Contract validation and evidence management."""

from __future__ import annotations

from typing import Any, Mapping

from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
    required_next_tool_call_satisfaction,
)
from aicarmine_broker.application.shared.path_tokens import repo_path_token as _repo_path_token
from aicarmine_broker.application.shared.validation_utils import (
    _list_or_empty,
    _repo_path_is_concrete,
    _coalesce_repo_read_paths,
    _final_quality_repo_read_allowlist,
    _collect_repo_paths,
    _known_contract_repo_paths,
    _known_contract_repo_dirs,
    _route_token_is_prose_or_metric,
    _search_query_is_concrete,
    _required_next_route_has_deterministic_proof,
)


def _normalize_terminal_planner_decision(
    decision: dict[str, Any]
) -> dict[str, Any]:
    """Normalize terminal planner decision."""
    from ...import_refs import _resolve_lazy

    # Import dependencies via registry
    dispatch_tool = _resolve_lazy(".tool_dispatch", ["dispatch_tool"])["dispatch_tool"]
    normalize_tool_name = _resolve_lazy(".tool_contract", ["normalize_tool_name"])["normalize_tool_name"]
    sanitize_tool_args = _resolve_lazy(".tool_contract", ["sanitize_tool_args"])["sanitize_tool_args"]

    return decision


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path_is_concrete(token: Any) -> bool:
    token = _repo_path_token(token)
    if not token:
        return False
    lowered = token.lower()
    if lowered in {"services", "tools", "cache", "cache_dir", "repo"}:
        return False
    if " " in token:
        return False
    if token in {".", ".."}:
        return False
    if "/" in token or "\\" in token:
        return True
    if token.count(".") >= 1:
        return True
    return False


def _coalesce_repo_read_paths(values: Any) -> list[str]:
    if isinstance(values, tuple):
        values = list(values)
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        token = _repo_path_token(value)
        if not _repo_path_is_concrete(token):
            continue
        if token not in out:
            out.append(token)
    return out


def _final_quality_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    allowlist: set[str] = set()
    memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    read_notes = operational.get("read_notes") if isinstance(operational.get("read_notes"), list) else []
    rows: list[dict[str, Any]] = [row for row in memory if isinstance(row, dict)] + [
        row for row in read_notes if isinstance(row, dict)
    ]

    def add_token(raw: Any) -> None:
        token = _repo_path_token(raw)
        if token and _repo_path_is_concrete(token):
            allowlist.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        values = contract.get(key)
        if isinstance(values, dict):
            for item in values.values():
                if isinstance(item, dict):
                    add_token(item.get("path"))
                    add_token(item.get("repo_path"))
                else:
                    add_token(item)
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    add_token(item.get("path"))
                    add_token(item.get("repo_path"))
                else:
                    add_token(item)
    verified_reads = contract.get("verified_content_reads")
    if isinstance(verified_reads, list):
        for read in verified_reads:
            if isinstance(read, dict):
                add_token(read.get("path") or read.get("repo_path"))
    for row in rows:
        add_token(row.get("path"))
        for path in row.get("mentioned_paths") if isinstance(row.get("mentioned_paths"), list) else []:
            add_token(path)
    return allowlist


def _collect_repo_paths(values: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(values, dict):
        for item in values.values():
            token = _repo_path_token(item)
            if token:
                out.add(token)
    elif isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                token = _repo_path_token(item.get("path") or item.get("source_path") or item.get("repo_path"))
            else:
                token = _repo_path_token(item)
            if token:
                out.add(token)
    else:
        token = _repo_path_token(values)
        if token:
            out.add(token)
    return out


def _known_contract_repo_paths(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    paths: set[str] = set()
    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "verified_content_reads",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        paths.update(_collect_repo_paths(contract.get(key)))
    coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        paths.update(_collect_repo_paths(coverage.get(key)))
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    final_coverage = (
        final_contract.get("minimum_read_coverage")
        if isinstance(final_contract.get("minimum_read_coverage"), dict)
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        paths.update(_collect_repo_paths(final_coverage.get(key)))
    return {path for path in paths if path and path != "."}


def _known_contract_repo_dirs(contract: dict[str, Any]) -> set[str]:
    dirs = {"."}
    for path in _known_contract_repo_paths(contract):
        parts = [part for part in path.split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _route_token_is_prose_or_metric(value: Any) -> bool:
    token = _repo_path_token(value)
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
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return True
    if " " in token:
        return True
    return False


def _search_query_is_concrete(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or len(text) > 260:
        return False
    lowered = text.lower()
    if lowered in {
        "docs/config",
        "ridondanze/rischi",
        "8/2",
        "8/8",
        "9/9",
        "planner/controller rejection paths",
    }:
        return False
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return False
    useful_tokens = [
        token
        for token in lowered.replace(",", " ").replace(";", " ").split()
        if len(token) >= 3 and "/" not in token and any(ch.isalpha() for ch in token)
    ]
    if "/" in lowered and len(useful_tokens) < 2:
        return False
    return bool(useful_tokens)


def _required_next_route_has_deterministic_proof(
    required_call: dict[str, Any],
    contract: dict[str, Any],
) -> bool:
    required_call = required_call if isinstance(required_call, dict) else {}
    tool = str(required_call.get("tool") or "").strip()
    args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}
    if tool == "repo_read":
        return True
    if tool == "repo_list_files":
        path = _repo_path_token(args.get("path") or ".") or "."
        if path == ".":
            return True
        return not _route_token_is_prose_or_metric(path) and path in _known_contract_repo_dirs(contract)
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query = args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
        if not _search_query_is_concrete(query):
            return False
        path = _repo_path_token(args.get("path")) if args.get("path") else ""
        if path and path not in _known_contract_repo_paths(contract) and path not in _known_contract_repo_dirs(contract):
            return False
        return True
    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = _repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        if document_id and not _route_token_is_prose_or_metric(document_id):
            return True
        return bool(target_file and target_file in _known_contract_repo_paths(contract))
    return False