"""Code-product build-state history and action helpers."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .state import (
    CODE_PRODUCT_BUILD_STATE_KIND,
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_build_state_section,
    goal_exact_text_block,
)
from ..shared.history_queries import history_tool_result
from ..shared.path_tokens import repo_rel_token
from ..prompt.values import text_hash
from ..prompt.window_signatures import (
    decision_paths,
    planner_scratchpad_window_signature,
    repo_read_window_range_for_target,
    repo_read_window_signature,
)
from ..evidence.audit_guidance import role_guidance_text
from ...tool_contract import normalize_tool_name


ArtifactPayloadLoader = Callable[[dict[str, Any]], dict[str, Any]]
RepoReadFullContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
NextScratchpadWindowAction = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]

CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS = {
    "repo_propose_code_edit_missing_unified_diff",
    "repo_propose_code_edit_missing_structured_operations",
    "code_product_payload_not_complete",
    "invalid_code_product_candidate",
}


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return False
    sha256 = text_hash(text)
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if (
            result.get("tool") == "planner_scratchpad_write"
            and result.get("ok") is True
            and str(result.get("mode") or "") == CODE_PRODUCT_BUILD_STATE_KIND
            and repo_rel_token(result.get("target_file") or "") == target
            and str(result.get("sha256") or "") == sha256
        ):
            return True
    return False


def code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
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
        "target_file": repo_rel_token(result.get("target_file") or ""),
        "status": result.get("status"),
        "sha256": result.get("sha256"),
        "complete_payload_ready": bool(result.get("complete_payload_ready")),
        "payload_loaded": False,
    }
    if tool == "planner_scratchpad_read":
        items = _list_or_empty(result.get("items"))
        if not items:
            return {}
        for item in reversed(items):
            if not isinstance(item, dict):
                continue
            metadata = _dict_or_empty(item.get("metadata"))
            parsed_state = code_product_build_state_parse(str(item.get("text") or ""))
            if parsed_state:
                state = parsed_state
                base.update({
                    "document_id": item.get("document_id") or base.get("document_id"),
                    "section": item.get("section") or base.get("section"),
                    "target_file": repo_rel_token(
                        metadata.get("target_file")
                        or state.get("target_file")
                        or base.get("target_file")
                        or ""
                    ),
                    "status": metadata.get("status") or state.get("status") or base.get("status"),
                    "sha256": item.get("sha256") or base.get("sha256"),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                    "full_chars": item.get("full_chars"),
                    "complete": item.get("complete"),
                    "has_more_after": item.get("has_more_after"),
                })
                ready_args = code_product_build_state_ready_payload(state)
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
                    "target_file": repo_rel_token(metadata.get("target_file") or base.get("target_file") or ""),
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


def latest_code_product_build_state(
    history: list[dict[str, Any]],
    target_file: str = "",
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    for item in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(item)
        state = code_product_build_state_from_result(result)
        if not state:
            continue
        state_target = repo_rel_token(state.get("target_file") or "")
        if target and target != "." and state_target and state_target != target:
            continue
        return state
    return {}


def successful_code_edit_proposals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") == "repo_propose_code_edit" and result.get("ok") is True:
            proposals.append(result)
    return proposals


def failed_code_edit_proposal_validation_row(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    result = history_tool_result(item)
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
            "old_text/new_text, or typed block. "
            + role_guidance_text("code_product_replan")
        ),
        "action_plan_candidate": "",
        "raw_planner_text_preview": "",
        "violations": list(dict.fromkeys(violations)),
        "rejected_decision": decision,
    }


def code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    target = repo_rel_token(target_file or state.get("target_file") or "")
    args: dict[str, Any] = {
        "kind": CODE_PRODUCT_BUILD_STATE_KIND,
        "max_chars": 8000,
    }
    if state.get("document_id"):
        args["document_id"] = state.get("document_id")
        args["offset"] = int(state.get("window_end") or 0)
    elif target and target != ".":
        args["target_file"] = target
        args["section"] = code_product_build_state_section(target)
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


def code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadFullContentLoader,
    limit: int = 3,
) -> list[dict[str, Any]]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return []
    windows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = same_tool_artifact_payload(result)
        raw_items = _list_or_empty(source.get("items"))
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = text_hash(text)
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
                "window_sha256": text_hash(text),
            })
            if len(windows) >= max(1, int(limit or 1)):
                return windows
    return windows


def code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadFullContentLoader,
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return {}
    source_windows = code_product_source_windows_from_reads(
        history or [],
        target,
        same_tool_artifact_payload=same_tool_artifact_payload,
        repo_read_item_full_content=repo_read_item_full_content,
    )
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
    if code_product_build_state_duplicate_write(history or [], target_file=target, text=state_text):
        return {}
    return {
        "action": "tool",
        "tool": "planner_scratchpad_write",
        "arguments": {
            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
            "target_file": target,
            "status": "collecting_source",
            "section": code_product_build_state_section(target),
            "max_chars": 8000,
            "text": state_text,
        },
        "reason": (
            "Persist a valid internal code_product_build_state with real repo_read "
            "source-window progress before attempting repo_propose_code_edit."
        ),
    }


def code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    args = state.get("ready_arguments") if isinstance(state.get("ready_arguments"), dict) else {}
    if not args:
        loaded_state = _dict_or_empty(state.get("state"))
        args = code_product_build_state_ready_payload(loaded_state)
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


def code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    old_text = goal_exact_text_block(goal, "old_text")
    new_text = goal_exact_text_block(goal, "new_text")
    if not (old_text and new_text):
        return {}
    args: dict[str, Any] = {
        "target_file": target,
        "edit_kind": "unified_diff",
        "rationale": "Report-only unified diff from exact old_text/new_text supplied by the user.",
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


def successful_window_signatures(history: list[dict[str, Any]], tool: str) -> set[str]:
    wanted_tool = normalize_tool_name(tool)
    signatures: set[str] = set()
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        result = history_tool_result(row)
        if normalize_tool_name(str(result.get("tool") or "")) != wanted_tool or result.get("ok") is not True:
            continue
        decision = _dict_or_empty(row.get("decision"))
        args = _dict_or_empty(decision.get("arguments"))
        if wanted_tool == "repo_read":
            signature = repo_read_window_signature(args)
        elif wanted_tool == "planner_scratchpad_read":
            signature = planner_scratchpad_window_signature(args)
        else:
            signature = ""
        if signature:
            signatures.add(signature)
    return signatures


def successful_repo_read_window_ranges(history: list[dict[str, Any]], target_file: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        result = history_tool_result(row)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        decision = _dict_or_empty(row.get("decision"))
        args = _dict_or_empty(decision.get("arguments"))
        item_range = repo_read_window_range_for_target(args, target_file)
        if item_range and item_range not in ranges:
            ranges.append(item_range)
    return ranges


def code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    target = repo_rel_token(target_file)
    count = 0
    for item in validation_rejections if isinstance(validation_rejections, list) else []:
        if not isinstance(item, dict):
            continue
        violations = {str(v) for v in (item.get("violations") or [])}
        if not violations.intersection(CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS):
            continue
        rejected = _dict_or_empty(item.get("rejected_decision"))
        if str(rejected.get("tool") or "") != "repo_propose_code_edit":
            continue
        args = _dict_or_empty(rejected.get("arguments"))
        rejected_target = repo_rel_token(args.get("target_file") or args.get("path") or "")
        if target and target != "." and rejected_target != target:
            continue
        count += 1
    return count


def code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
    single_file_prompt_read_chars: int,
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return {}
    try:
        total_lines = max(0, int(line_count or 0))
    except (TypeError, ValueError):
        total_lines = 0
    ranges = successful_repo_read_window_ranges(history or [], target)
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
        "max_chars": int(single_file_prompt_read_chars),
    }
    if repo_read_window_signature(args) in successful_window_signatures(history or [], "repo_read"):
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


def strip_duplicate_window_candidate(
    actions: list[dict[str, Any]],
    *,
    tool: str,
    signature: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    wanted_tool = normalize_tool_name(tool)
    for item in actions if isinstance(actions, list) else []:
        if not isinstance(item, dict) or normalize_tool_name(str(item.get("tool") or "")) != wanted_tool:
            out.append(item)
            continue
        args = _dict_or_empty(item.get("arguments"))
        if wanted_tool == "repo_read":
            item_signature = repo_read_window_signature(args)
        elif wanted_tool == "planner_scratchpad_read":
            item_signature = planner_scratchpad_window_signature(args)
        else:
            item_signature = ""
        if item_signature and item_signature == signature:
            continue
        out.append(item)
    return out


def apply_duplicate_window_replan_contract(
    contract: dict[str, Any],
    *,
    violation: str,
    tool: str,
    args: dict[str, Any],
    history: list[dict[str, Any]],
    planner_scratchpad_next_window_action_from_history: NextScratchpadWindowAction,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadFullContentLoader,
    single_file_prompt_read_chars: int,
) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    signature = (
        repo_read_window_signature(args)
        if tool == "repo_read"
        else planner_scratchpad_window_signature(args)
        if tool == "planner_scratchpad_read"
        else ""
    )
    raw_existing_actions = _list_or_empty(contract.get("candidate_next_actions"))
    existing_actions = [item for item in raw_existing_actions if isinstance(item, dict)]
    existing = strip_duplicate_window_candidate(
        existing_actions,
        tool=tool,
        signature=signature,
    )
    code_contract = _dict_or_empty(contract.get("code_product_contract"))
    apply_goal = bool(contract.get("goal_requests_apply"))
    code_product_goal = bool(
        code_contract.get("required")
        or contract.get("goal_requires_code_product")
        or contract.get("goal_requests_code_product")
    )
    next_actions: list[dict[str, Any]] = []
    if tool == "planner_scratchpad_read":
        next_window = planner_scratchpad_next_window_action_from_history(args, history)
        if next_window:
            next_actions.append(next_window)
        contract["required_next_progress"] = (
            "The requested SQLite window was already consumed. Replan now: read the next "
            "unconsumed SQLite window if candidate_next_actions provides one; otherwise use "
            "the already-read window evidence to produce a complete payload or return a typed "
            "block. "
            + role_guidance_text("code_product_replan")
            + " Do not repeat the same planner_scratchpad_read arguments."
        )
    elif tool == "repo_read":
        target_paths = decision_paths(args)
        target = repo_rel_token(target_paths[0]) if target_paths else ""
        if apply_goal:
            existing = [
                item for item in existing
                if normalize_tool_name(str(item.get("tool") or "")) != "planner_scratchpad_write"
            ]
            contract["required_next_progress"] = (
                "The requested repo_read window already succeeded and a cache hit would not be progress. "
                "This is an apply/edit goal: do not call repo_read for that target again. Use "
                "verified_content_reads/required_working_set for the target and call repo_apply_patch "
                "only with old_text exactly equal to verified repo_read content, or return a typed block "
                "if a valid patch cannot be built."
            )
        elif not code_product_goal:
            required = _dict_or_empty(contract.get("required_next_tool_call"))
            required_args = _dict_or_empty(required.get("arguments"))
            required_paths = [repo_rel_token(path) for path in decision_paths(required_args)]
            if normalize_tool_name(str(required.get("tool") or "")) == "repo_read" and (
                not target or target in required_paths
            ):
                contract.pop("required_next_tool_call", None)
                contract["required_next_tool_call_satisfied"] = {
                    "satisfied": True,
                    "tool": "repo_read",
                    "arguments": required_args,
                    "paths": required_paths or target_paths,
                    "reason": "duplicate_repo_read_already_successful",
                    "window_signature": signature,
                }
            contract["required_next_progress"] = (
                "The requested repo_read already succeeded and repeating it is not progress. "
                "This is a repository analysis/audit flow: use verified_content_reads and "
                "successful_repo_read_paths already in the evidence contract to answer with "
                "action=final if coverage is sufficient; otherwise choose a different concrete "
                "repo_semantic_search, repo_rg_search, or repo_read gap that is not already "
                "satisfied. Do not call repo_propose_code_edit or write code_product_build_state."
            )
            contract["duplicate_window_replan"] = {
                "schema": "duplicate_window_replan.v1",
                "tool": tool,
                "violation": violation,
                "target_paths": target_paths,
                "analysis_flow": True,
            }
        else:
            line_count = 0
            for row in contract.get("verified_content_reads") or []:
                if isinstance(row, dict) and repo_rel_token(row.get("path") or "") == target:
                    try:
                        line_count = int(row.get("line_count") or 0)
                    except (TypeError, ValueError):
                        line_count = 0
                    break
            route_candidate = code_product_source_window_candidate(
                target,
                line_count=line_count,
                history=history,
                single_file_prompt_read_chars=single_file_prompt_read_chars,
            )
            if route_candidate:
                next_actions.append(route_candidate)
            if target:
                build_state_action = code_product_build_state_write_action(
                    target,
                    history,
                    same_tool_artifact_payload=same_tool_artifact_payload,
                    repo_read_item_full_content=repo_read_item_full_content,
                )
                if build_state_action:
                    next_actions.append(build_state_action)
            contract["required_next_progress"] = (
                "The requested repo_read window already succeeded and a cache hit would not be progress. "
                "Replan now: read a different unconsumed source window if candidate_next_actions provides "
                "one; otherwise use verified_content_reads/required_working_set for the target and call "
                "repo_propose_code_edit only with a complete unified_diff or old_text/new_text, or return "
                "a typed block. "
                + role_guidance_text("code_product_replan")
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
    if tool != "repo_read" or apply_goal or code_product_goal:
        code_contract["duplicate_window_replan_required"] = True
        code_contract["duplicate_window_violation"] = violation
        contract["code_product_contract"] = code_contract
    return contract


def code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    target = repo_rel_token(path)
    if target.endswith("__init__.py") or target.endswith("__main__.py"):
        return True
    rows = _list_or_empty(contract.get("verified_content_reads"))
    for row in rows:
        if not isinstance(row, dict) or repo_rel_token(row.get("path") or "") != target:
            continue
        try:
            return int(row.get("line_count") or 0) < 20
        except Exception:
            return True
    return False
