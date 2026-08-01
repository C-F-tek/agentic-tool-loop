"""Candidate next-action helpers forfrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 planner turn surface policy."""
from __future__ import annotations

from typing import Any, Callable

from ...tool_contract import normalize_tool_name
from ..code_product.state import CODE_PRODUCT_BUILD_STATE_KIND
from ..shared.diagnostics import safe_json_text, safe_text
from .batch_contract import canonical_batch_call_key
from .required_tool_call import canonical_required_tool_call_key


def _stable_action_key(action: Any) -> str:
    text, _diagnostic = safe_json_text(
        action,
        reason="candidate_action_key_json_failed",
        separators=(",", ":"),
    )
    return text


def candidate_action_tool(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    return normalize_tool_name(safe_text(action.get("tool"), limit=160))


def candidate_action_args(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    args = action.get("arguments")
    return args if isinstance(args, dict) else {}


def candidate_action_is_build_state_write(action: Any) -> bool:
    return (
        candidate_action_tool(action) == "planner_scratchpad_write"
        and safe_text(candidate_action_args(action).get("kind"), limit=160).strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def candidate_action_is_build_state_read(action: Any) -> bool:
    args = candidate_action_args(action)
    return (
        candidate_action_tool(action) == "planner_scratchpad_read"
        and safe_text(args.get("kind") or args.get("mode"), limit=160).strip() == CODE_PRODUCT_BUILD_STATE_KIND
    )


def dedupe_candidate_actions(actions: list[Any], *, limit: int = 16) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = _stable_action_key(action)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
        if len(deduped) >= limit:
            break
    return deduped


def candidate_actions_from_evidence(
    goal: str,
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    final_allowed: bool,
    *,
    failed_list_paths: list[str] | None = None,
    core_discovery_candidates: list[dict[str, Any]] | None = None,
    repo_rel_token: Callable[[str], str],
    repo_analysis_goal: Callable[[str], bool],
    repo_doc_or_config: Callable[[str], bool],
    low_signal_top_dir: Callable[[str], bool],
    rank_core_candidates: Callable[[list[dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]],
    path_exists_repo_relative: Callable[[str], bool],
    goal_target_scope: Callable[[str], str],
    input_error_goal: Callable[[str], bool],
    path_under_scope: Callable[[str, str], bool],
    core_discovery_read_paths: Callable[..., list[str]],
    scoped_concrete_read_target: int,
    repo_concrete_read_target: int,
    scope_read_candidates_from_evidence: Callable[..., list[str]],
    multi_file_prompt_read_chars: Callable[[], int],
    meaningful_read_candidates_from_evidence: Callable[..., list[str]],
    single_file_prompt_read_chars: Callable[[], int],
    repo_code_file: Callable[[str], bool],
    repo_readable_evidence_file: Callable[[str], bool] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    already = set(read_ok)
    failed_lists = set(repo_rel_token(p) for p in (failed_list_paths or []))
    repo_goal = repo_analysis_goal(goal)
    doc_reads = [p for p in read_ok if repo_doc_or_config(p)]

    def readable_repo_path(path: Any, *, scope: str = "") -> str:
        p = repo_rel_token(path)
        if not p or p in already:
            return ""
        if scope and not path_under_scope(p, scope):
            return ""
        if not path_exists_repo_relative(p):
            return ""
        if repo_readable_evidence_file is not None and not repo_readable_evidence_file(p):
            return ""
        return p

    def readable_repo_paths(paths: list[Any], *, scope: str = "", limit: int | None = None) -> list[str]:
        out: list[str] = []
        for path in paths:
            p = readable_repo_path(path, scope=scope)
            if p and p not in out:
                out.append(p)
                if limit is not None and len(out) >= limit:
                    break
        return out

    def add(action: dict[str, Any]) -> None:
        key = _stable_action_key(action)
        for existing in candidates:
            if _stable_action_key(existing) == key:
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
        and not low_signal_top_dir(safe_text(row.get("path"), limit=1000))
    ]

    def add_core_list_candidates(limit: int = 5) -> None:
        ranked_core = sorted(
            rank_core_candidates(file_memory, list_rows),
            key=lambda item: (
                -int(item.get("score") or 0),
                safe_text(item.get("path"), limit=1000).lower(),
            ),
        )
        for core in ranked_core[:limit]:
            p = core.get("path")
            if (
                p
                and p not in failed_lists
                and path_exists_repo_relative(safe_text(p, limit=1000))
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

    target_scope = goal_target_scope(goal)
    discovery_selected = core_discovery_read_paths(
        core_discovery_candidates,
        read_ok=already,
        target_scope=target_scope,
        limit=scoped_concrete_read_target if target_scope else repo_concrete_read_target,
    )
    discovery_selected = readable_repo_paths(
        discovery_selected,
        scope=target_scope,
        limit=scoped_concrete_read_target if target_scope else repo_concrete_read_target,
    )
    if discovery_selected:
        add({
            "action": "tool",
            "tool": "repo_read",
            "arguments": {
                "paths": discovery_selected,
                "max_chars": multi_file_prompt_read_chars(),
                "max_paths": len(discovery_selected),
            },
            "reason": (
                "Read core_discovery_candidates from RAG/rerank or rebuilt LAB_REPO ranking; "
                "ranking is discovery-only and does not authorize a patch."
            ),
        })

    if target_scope and not input_error_goal(goal):
        scoped_rows = [
            row for row in list_rows
            if path_under_scope(safe_text(row.get("path"), limit=1000), target_scope)
            and safe_text(row.get("path") or ".", limit=1000) not in ("", ".")
        ]
        if not scoped_rows:
            add({
                "action": "tool",
                "tool": "repo_list_files",
                "arguments": {"path": target_scope, "limit": 120},
                "reason": f"Inspect requested scope {target_scope}; root tree alone is not enough evidence.",
            })
        else:
            selected = scope_read_candidates_from_evidence(
                list_rows,
                target_scope,
                read_ok=already,
            )
            selected = readable_repo_paths(selected, scope=target_scope, limit=scoped_concrete_read_target)
            if selected:
                add({
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {
                        "paths": selected,
                        "max_chars": multi_file_prompt_read_chars(),
                        "max_paths": len(selected),
                    },
                    "reason": (
                        f"Read up to {scoped_concrete_read_target} dynamically discovered "
                        f"readable files inside requested scope {target_scope} before finalizing."
                    ),
                })
        if candidates:
            return candidates[:16]

    # If a meaningful non-root area has already been listed, read from that area
    # before falling back to more root documentation. Otherwise the planner can
    # spend many turns reading low-signal root docs and still final with only a
    # directory-name summary.
    if repo_goal and meaningful_rows:
        selected = meaningful_read_candidates_from_evidence(
            list_rows,
            read_ok=already,
        )
        selected = readable_repo_paths(selected, limit=repo_concrete_read_target)
        if selected:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {
                    "paths": selected,
                    "max_chars": multi_file_prompt_read_chars(),
                    "max_paths": len(selected),
                },
                "reason": (
                    f"Read up to {repo_concrete_read_target} dynamically discovered "
                    "readable files from already listed meaningful non-root areas before finalizing."
                ),
            })
            for p in selected[:repo_concrete_read_target]:
                add({
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": p, "max_chars": single_file_prompt_read_chars()},
                    "reason": "Read concrete readable file from meaningful non-root area before finalizing.",
                })

    # Once enough root docs exist, prefer opening a real core directory instead
    # of continuing a root-doc crawl. This remains a candidate list for the
    # planner, not a controller-executed script.
    if repo_goal and len(doc_reads) >= 3 and not meaningful_rows:
        add_core_list_candidates(limit=5)

    docs = readable_repo_paths([p for p in listed if repo_doc_or_config(p)])
    # Generic repo analysis needs representative docs, not every support/template
    # document. After a small baseline, spend budget on core directories/files.
    if not (repo_goal and len(doc_reads) >= 6):
        if docs:
            doc_paths = docs[:scoped_concrete_read_target]
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {
                    "paths": doc_paths,
                    "max_chars": multi_file_prompt_read_chars(),
                    "max_paths": len(doc_paths),
                },
                "reason": "Read repository documentation/config already discovered in evidence before finalizing.",
            })

        for p in docs[:scoped_concrete_read_target]:
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": p, "max_chars": single_file_prompt_read_chars()},
                "reason": "Unread repository documentation/config candidate from prior evidence.",
            })

    for p in listed:
        readable = readable_repo_path(p)
        if readable and repo_code_file(readable):
            add({
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": readable, "max_chars": single_file_prompt_read_chars()},
                "reason": "Unread readable file discovered from evidence.",
            })
            if len(candidates) >= 12:
                break

    add_core_list_candidates(limit=5)

    return candidates[:16]


def final_composition_tool_names_from_candidates(contract: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = candidate_action_tool(action)
        args = candidate_action_args(action)
        if name == "planner_scratchpad_write" and safe_text(args.get("kind"), limit=160).strip() == "answer_chunk":
            names.add(name)
    return names


def required_next_tool_call_from_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    tool = candidate_action_tool(action)
    args = candidate_action_args(action)
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


def _readonly_batch_actions_from_continuation(action: dict[str, Any]) -> list[dict[str, Any]]:
    args = candidate_action_args(action)
    batch_window = action.get("batch_window") if isinstance(action.get("batch_window"), dict) else {}
    try:
        offset = max(0, int(args.get("offset") or batch_window.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        max_chars = max(500, int(args.get("max_chars") or batch_window.get("max_chars") or 3000))
    except (TypeError, ValueError):
        max_chars = 3000
    try:
        full_chars = max(0, int(batch_window.get("full_chars") or 0))
    except (TypeError, ValueError):
        full_chars = 0
    try:
        max_actions = max(1, min(8, int(batch_window.get("max_batch_actions") or 8)))
    except (TypeError, ValueError):
        max_actions = 8

    offsets = [offset]
    if full_chars > offset and max_chars > 0:
        current = offset + max_chars
        while current < full_chars and len(offsets) < max_actions:
            offsets.append(current)
            current += max_chars

    out: list[dict[str, Any]] = []
    for current_offset in offsets:
        call_args = {
            key: args.get(key)
            for key in ("kind", "document_id", "section", "max_chars", "target_file")
            if args.get(key) not in (None, "", [], {})
        }
        call_args["offset"] = current_offset
        call_args["max_chars"] = max_chars
        action_id_parts = [
            "required_scratchpad_read_continuation",
            safe_text(call_args.get("document_id") or call_args.get("section"), limit=300),
            str(current_offset),
            str(max_chars),
        ]
        out.append({
            "action_id": ":".join(action_id_parts),
            "tool": "planner_scratchpad_read",
            "arguments": call_args,
            "reason": action.get("reason"),
            "source": "required_next_tool_call",
            "independent_read_only": True,
        })
    return out


def _batch_action_key(action: dict[str, Any]) -> str:
    return canonical_batch_call_key(candidate_action_tool(action), candidate_action_args(action))


def enforce_required_scratchpad_read_continuation_contract(
    contract: dict[str, Any],
    continuation: dict[str, Any],
) -> dict[str, Any]:
    """Make an exact scratchpad-read continuation dominate terminal guidance."""
    out = dict(contract) if isinstance(contract, dict) else {}
    if not isinstance(continuation, dict):
        return out
    tool = candidate_action_tool(continuation)
    args = candidate_action_args(continuation)
    if tool != "planner_scratchpad_read" or not args:
        return out

    reason = safe_text(
        continuation.get("reason")
        or out.get("required_next_progress")
        or "Required planner scratchpad continuation must be consumed before final/block.",
        limit=900,
    )
    action = {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": {
            key: value
            for key, value in args.items()
            if value not in (None, "", [], {})
        },
        "reason": reason,
    }
    if isinstance(continuation.get("batch_window"), dict):
        action["batch_window"] = continuation["batch_window"]
    required = required_next_tool_call_from_action(action)
    if not required:
        return out

    out["candidate_next_actions"] = [action]
    out["required_next_tool_call"] = required
    out["planner_may_choose_final"] = False
    out["required_next_progress"] = reason

    final_contract = out.get("finalization_contract") if isinstance(out.get("finalization_contract"), dict) else {}
    final_contract = dict(final_contract)
    final_contract["final_allowed"] = False
    final_contract["planner_may_choose_final"] = False
    final_contract["reason"] = reason
    out["finalization_contract"] = final_contract

    micro_batch = out.get("micro_batch_contract") if isinstance(out.get("micro_batch_contract"), dict) else {}
    micro_batch = dict(micro_batch)
    allowed_actions = (
        micro_batch.get("allowed_batch_actions")
        if isinstance(micro_batch.get("allowed_batch_actions"), list)
        else []
    )
    required_batch_actions = _readonly_batch_actions_from_continuation(action)
    merged_actions = list(required_batch_actions)
    seen = {_batch_action_key(item) for item in required_batch_actions}
    for item in allowed_actions:
        if not isinstance(item, dict):
            continue
        if candidate_action_tool(item) != "planner_scratchpad_read":
            continue
        key = _batch_action_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged_actions.append(item)
    micro_batch.update(
        {
            "schema": "planner_micro_batch_contract.v1",
            "allowed": len(merged_actions) >= 2,
            "mode": "native_message_tool_calls_only",
            "max_batch_size": len(merged_actions),
            "allowed_tools": ["planner_scratchpad_read"],
            "allowed_batch_actions": merged_actions,
            "guard": (
                "Batching is allowed only for read-only planner_scratchpad_read "
                "continuation windows. Write/apply/command/final/block actions remain forbidden."
            ),
            "reason": (
                "scratchpad_read_continuation_readonly_batch_available"
                if len(merged_actions) >= 2
                else "scratchpad_read_continuation_single_read_available"
            ),
            "writes_allowed": False,
            "validation_tools_allowed": False,
        }
    )
    out["micro_batch_contract"] = micro_batch

    return out


def decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    if not isinstance(decision, dict) or not isinstance(continuation, dict):
        return True
    if continuation.get("tool") != "planner_scratchpad_read":
        return True
    if normalize_tool_name(safe_text(decision.get("tool"), limit=160)) != "planner_scratchpad_read":
        return False
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    expected = continuation.get("arguments") if isinstance(continuation.get("arguments"), dict) else {}
    expected_kind = safe_text(expected.get("kind") or "prompt_context_window", limit=160)
    if safe_text(args.get("kind"), limit=160) != expected_kind:
        return False
    if safe_text(args.get("document_id"), limit=300) != safe_text(expected.get("document_id"), limit=300):
        return False
    try:
        if int(args.get("offset") or 0) != int(expected.get("offset") or 0):
            return False
        if expected.get("max_chars") not in (None, ""):
            return int(args.get("max_chars") or 0) == int(expected.get("max_chars") or 0)
        return True
    except (TypeError, ValueError):
        return False


def preserve_required_next_tool_call_for_prompt(
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
        candidates = (
            previous_evidence_contract.get("candidate_next_actions")
            if isinstance(previous_evidence_contract.get("candidate_next_actions"), list)
            else []
        )
        if len(candidates) == 1 and candidate_action_tool(candidates[0]) == "planner_scratchpad_read":
            required = required_next_tool_call_from_action(candidates[0])
    if not required:
        return
    if _required_call_marked_satisfied(previous_evidence_contract, required):
        evidence["required_next_tool_call_satisfied"] = (
            previous_evidence_contract.get("required_next_tool_call_satisfied")
            if isinstance(previous_evidence_contract.get("required_next_tool_call_satisfied"), dict)
            else {}
        )
        stale = previous_evidence_contract.get("stale_required_next_tool_calls")
        if isinstance(stale, list) and stale:
            evidence["stale_required_next_tool_calls"] = stale[:8]
        payload["evidence_contract"] = evidence
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
    required_key = _stable_action_key(required)
    matched_action = {}
    for action in prev_actions:
        if not isinstance(action, dict):
            continue
        action_required = required_next_tool_call_from_action(action)
        if _stable_action_key(action_required) == required_key:
            matched_action = action
            break
    if matched_action:
        action_key = _stable_action_key(matched_action)
        evidence["candidate_next_actions"] = [matched_action] + [
            item for item in current_actions
            if _stable_action_key(item) != action_key
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
    if required.get("tool") == "planner_scratchpad_read":
        continuation = {
            "tool": "planner_scratchpad_read",
            "arguments": required.get("arguments") if isinstance(required.get("arguments"), dict) else {},
            "reason": (
                prev_final_contract.get("reason")
                or evidence.get("required_next_progress")
                or required.get("reason")
            ),
        }
        if isinstance(matched_action.get("batch_window"), dict):
            continuation["batch_window"] = matched_action["batch_window"]
        evidence = enforce_required_scratchpad_read_continuation_contract(evidence, continuation)
        payload["required_next_tool_call"] = evidence.get("required_next_tool_call")
        if isinstance(evidence.get("forbidden_repeated_tool_calls"), list):
            payload["forbidden_repeated_tool_calls"] = evidence["forbidden_repeated_tool_calls"]
        payload["evidence_contract"] = evidence
        return
    if prev_final_contract.get("final_allowed") is False:
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = prev_final_contract.get("reason") or evidence.get("required_next_progress")
        evidence["planner_may_choose_final"] = False
    evidence["finalization_contract"] = final_contract
    payload["evidence_contract"] = evidence


def _required_call_marked_satisfied(contract: dict[str, Any], required: dict[str, Any]) -> bool:
    if not isinstance(contract, dict) or not isinstance(required, dict) or not required:
        return False
    key = canonical_required_tool_call_key(required.get("tool"), required.get("arguments"))
    current = (
        contract.get("required_next_tool_call_satisfied")
        if isinstance(contract.get("required_next_tool_call_satisfied"), dict)
        else {}
    )
    current_key = current.get("key") or canonical_required_tool_call_key(
        current.get("tool"),
        current.get("arguments"),
    )
    if current.get("satisfied") is True and current_key == key:
        return True
    stale = contract.get("stale_required_next_tool_calls")
    for item in stale if isinstance(stale, list) else []:
        if not isinstance(item, dict):
            continue
        item_key = item.get("key") or canonical_required_tool_call_key(
            item.get("tool"),
            item.get("arguments"),
        )
        if item.get("satisfied") is True and item_key == key:
            return True
    return False
