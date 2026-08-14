"""Prompt-facing evidence contract compaction helpers."""
from __future__ import annotations

from typing import Any

from .values import prompt_clip_text, prompt_clip_value


EVIDENCE_PROMPT_KEEP_KEYS = (
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
    "micro_batch_contract",
    "minimum_read_coverage",
    "coverage_satisfied",
    "covered_owner_paths",
    "missing_owner_paths",
    "candidate_owner_paths",
    "planner_may_choose_final",
    "code_product_contract",
    "finalization_contract",
    "required_next_progress",
    "required_next_tool_call",
    "validation_rejections_tail",
    "failed_repo_read_paths",
    "failed_repo_list_files_paths",
    "forbidden_repeated_repo_read_paths",
    "read_admissible_paths",
    "validator_admissible_repo_read_paths",
)


def _counted_top_list(
    value: Any,

    item_limit: int,
    text_limit: int,
) -> tuple[list[Any], int, int]:
    if not isinstance(value, list):
        return [], 0, 0
    shown = prompt_clip_value(
        value[: max(0, int(item_limit or 0))],
        text_limit=text_limit,
        list_limit=item_limit,
    )
    shown_list = shown if isinstance(shown, list) else []
    return shown_list, len(value), max(0, len(value) - len(shown_list))


def _apply_counted_top_list(
    out: dict[str, Any],
    key: str,
    
    item_limit: int,
    text_limit: int,
) -> None:
    if key not in out or not isinstance(out.get(key), list):
        return
    shown, count, omitted = _counted_top_list(
        out.get(key),
        item_limit=item_limit,
        text_limit=text_limit,
    )
    out[key] = shown
    out[f"{key}_count"] = count
    if omitted:
        out[f"{key}_omitted_count"] = omitted


def _compact_verified_content_reads(value: Any,  item_limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    compact: list[dict[str, Any]] = []
    for row in value[: max(0, int(item_limit or 0))]:
        if not isinstance(row, dict):
            continue
        item: dict[str, Any] = {}
        for key in (
            "path",
            "repo_path",
            "line_count",
            "truncated",
            "preview_only",
            "content_chars",
            "sha256",
            "source",
            "document_id",
            "offset",
            "max_chars",
            "complete",
        ):
            if row.get(key) not in (None, "", [], {}):
                item[key] = prompt_clip_value(row.get(key), text_limit=220, list_limit=4)
        if "content_chars" not in item:
            for content_key in ("content", "content_preview", "content_excerpt", "text"):
                content = row.get(content_key)
                if isinstance(content, str) and content:
                    item["content_chars"] = len(content)
                    item["content_not_duplicated_here"] = True
                    break
        if item:
            compact.append(item)
    return compact


def compact_evidence_contract_for_prompt(
    contract: dict[str, Any],
    
    prompt_preview_chars: int,
) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    out = {
        key: contract.get(key)
        for key in EVIDENCE_PROMPT_KEEP_KEYS
        if contract.get(key) not in (None, "", [], {})
    }
    if isinstance(out.get("verified_content_reads"), list):
        raw_reads = out["verified_content_reads"]
        compact_reads = _compact_verified_content_reads(raw_reads, item_limit=8)
        out["verified_content_reads"] = compact_reads
        out["verified_content_reads_count"] = len(raw_reads)
        if len(raw_reads) > len(compact_reads):
            out["verified_content_reads_omitted_count"] = len(raw_reads) - len(compact_reads)
    for key in (
        "successful_repo_read_paths",
        "covered_owner_paths",
        "missing_owner_paths",
        "candidate_owner_paths",
        "failed_repo_read_paths",
        "failed_repo_list_files_paths",
        "forbidden_repeated_repo_read_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
    ):
        _apply_counted_top_list(out, key, item_limit=24, text_limit=180)
    for key in (
        "candidate_next_actions",
        "core_discovery_candidates",
        "validation_rejections_tail",
    ):
        _apply_counted_top_list(out, key, item_limit=8, text_limit=320)
    if out.get("forbidden_repeated_repo_read_paths"):
        out["forbidden_repeated_repo_read_paths_note"] = (
            "Do not repeat full-path repo_read for forbidden_repeated_repo_read_paths."
        )
    if isinstance(out.get("initial_orientation_surface"), dict):
        out["initial_orientation_surface"] = prompt_clip_value(
            out["initial_orientation_surface"],
            text_limit=360,
            list_limit=6,
        )
        out["initial_orientation_surface_compacted"] = True
    file_memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    out["file_memory_count"] = len(file_memory)
    out["file_memory"] = [
        {
            "path": row.get("path"),
            "line_count": row.get("line_count"),
            "truncated": row.get("truncated"),
            "key_lines": prompt_clip_value(row.get("key_lines") or [], text_limit=220, list_limit=8),
            "content_excerpt": prompt_clip_text(row.get("content_excerpt"), 240),
        }
        for row in file_memory[:6]
        if isinstance(row, dict)
    ]
    if len(file_memory) > len(out["file_memory"]):
        out["file_memory_omitted_count"] = len(file_memory) - len(out["file_memory"])
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    if operational:
        out["operational_notes"] = {
            "final_allowed": operational.get("final_allowed"),
            "next_instruction": prompt_clip_text(operational.get("next_instruction"), 500),
            "candidate_next_actions": prompt_clip_value(
                operational.get("candidate_next_actions") or [],
                list_limit=6,
            ),
        }
    micro_batch = out.get("micro_batch_contract")
    if isinstance(micro_batch, dict) and micro_batch:
        compact_micro = {
            key: prompt_clip_value(micro_batch.get(key), text_limit=360, list_limit=8)
            for key in (
                "schema",
                "allowed",
                "mode",
                "max_batch_size",
                "allowed_tools",
                "reason",
            )
            if micro_batch.get(key) not in (None, "", [], {})
        }
        compact_actions = _compact_allowed_batch_actions_for_prompt(
            micro_batch.get("allowed_batch_actions"),
            list_limit=8,
        )
        if compact_actions:
            compact_micro["allowed_batch_actions"] = compact_actions
        out["micro_batch_contract"] = compact_micro
    return prompt_clip_value(out, text_limit=prompt_preview_chars, list_limit=12)


def _compact_allowed_batch_actions_for_prompt(
    actions: Any,
    
    list_limit: int,
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    if not isinstance(actions, list):
        return compact
    for action in actions[: max(0, int(list_limit or 0))]:
        if not isinstance(action, dict):
            continue
        item: dict[str, Any] = {}
        for key in ("action_id", "tool"):
            if action.get(key) not in (None, "", [], {}):
                item[key] = action.get(key)
        args = action.get("arguments")
        if isinstance(args, dict) and args:
            item["arguments"] = prompt_clip_value(args, text_limit=260, list_limit=8)
        if item:
            compact.append(item)
    return compact


def hard_budget_evidence_contract_summary(
    contract: dict[str, Any],
    
    reason: str,
) -> dict[str, Any]:
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
        "minimum_read_coverage",
        "coverage_satisfied",
        "covered_owner_paths",
        "missing_owner_paths",
        "planner_may_choose_final",
        "required_next_progress",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = prompt_clip_value(value, text_limit=320, list_limit=6)
    final_contract = contract.get("finalization_contract")
    if isinstance(final_contract, dict):
        compact["finalization_contract"] = {
            key: prompt_clip_value(final_contract.get(key), text_limit=260, list_limit=4)
            for key in (
                "final_allowed",
                "planner_may_choose_final",
                "coverage_satisfied",
                "missing_owner_paths",
                "reason",
            )
            if final_contract.get(key) not in (None, "", [], {})
        }
    code_contract = contract.get("code_product_contract")
    if isinstance(code_contract, dict):
        compact["code_product_contract"] = {
            key: prompt_clip_value(code_contract.get(key), text_limit=320, list_limit=8)
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
        compact["candidate_next_actions"] = prompt_clip_value(
            candidates,
            text_limit=700,
            list_limit=3,
        )
    micro_batch = contract.get("micro_batch_contract")
    if isinstance(micro_batch, dict) and micro_batch:
        compact_actions = _compact_allowed_batch_actions_for_prompt(
            micro_batch.get("allowed_batch_actions"),
            list_limit=8,
        )
        compact["micro_batch_contract"] = {
            key: prompt_clip_value(micro_batch.get(key), text_limit=420, list_limit=8)
            for key in (
                "schema",
                "allowed",
                "mode",
                "max_batch_size",
                "allowed_tools",
                "reason",
            )
            if micro_batch.get(key) not in (None, "", [], {})
        }
        if compact_actions:
            compact["micro_batch_contract"]["allowed_batch_actions"] = compact_actions
    for key in ("required_next_tool_call", "forbidden_repeated_tool_calls"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = prompt_clip_value(value, text_limit=500, list_limit=8)
    for key in ("successful_repo_read_paths", "read_admissible_paths", "validator_admissible_repo_read_paths"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = prompt_clip_value(value, text_limit=160, list_limit=5)
    return compact
