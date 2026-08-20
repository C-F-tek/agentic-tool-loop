"""Required next tool call validator extracted from validator.py.

Manages validation of ``required_next_tool_call`` against evidence,
including deterministic proof checks, path verification, and
duplicate recovery contracts.
"""

from __future__ import annotations

from typing import Any, Mapping, Tuple

from aicarmine_broker.application.planner.path_utils import (
    collect_repo_paths,
    known_contract_repo_dirs,
    known_contract_repo_paths,
    route_token_is_prose_or_metric,
    search_query_is_concrete,
)
from aicarmine_broker.application.shared.path_tokens import repo_path_token as _repo_path_token


def required_next_route_has_deterministic_proof(
    required_call: dict[str, Any],
    contract: dict[str, Any],
) -> bool:
    """Return True if *required_call* has a deterministic concrete route."""
    required_call = required_call if isinstance(required_call, dict) else {}
    tool = str(required_call.get("tool") or "").strip()
    args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}
    if tool == "repo_read":
        return True
    if tool == "repo_list_files":
        path = _repo_path_token(args.get("path") or ".") or "."
        if path == ".":
            return True
        return not route_token_is_prose_or_metric(path) and path in known_contract_repo_dirs(contract)
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query = args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
        if not search_query_is_concrete(query):
            return False
        path = _repo_path_token(args.get("path")) if args.get("path") else ""
        if path and path not in known_contract_repo_paths(contract) and path not in known_contract_repo_dirs(contract):
            return False
        return True
    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = _repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        if document_id and not route_token_is_prose_or_metric(document_id):
            return True
        return bool(target_file and target_file in known_contract_repo_paths(contract))
    return False


def coalesce_required_next_tool_tool(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize a required_next_tool_call dict to a canonical shape."""
    tool = str(value.get("tool") or "").strip().lower()
    args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
    if not tool:
        return {"tool": "", "arguments": {}, "allow_only_if_missing_evidence": False}
    out = {
        "tool": tool,
        "arguments": args,
        "allow_only_if_missing_evidence": bool(value.get("allow_only_if_missing_evidence")),
        "reason": str(value.get("reason") or "").strip(),
        "source": str(value.get("source") or "repo_analysis_final_model_quality").strip(),
    }
    if tool == "repo_read":
        if "paths" in args:
            normalized_paths = [
                _repo_path_token(item)
                for item in args.get("paths", [])
                if _repo_path_token(item)
            ] if isinstance(args.get("paths"), list) else []
            if normalized_paths:
                out["arguments"] = {"paths": normalized_paths}
            else:
                out["arguments"] = {}
        else:
            path = _repo_path_token(args.get("path"))
            if path:
                out["arguments"] = {"path": path}
            else:
                out["arguments"] = {}
        if out["arguments"]:
            out["allow_only_if_missing_evidence"] = True
    elif not args:
        out["arguments"] = {}
    return out


def coerce_final_rewrite_latch(value: Any) -> str:
    """Normalize a value to a valid latch state."""
    raw = str(value or "inactive").strip().lower()
    return raw if raw in {"inactive", "rewrite_required", "required_gap_only", "terminal_block_required"} else "inactive"