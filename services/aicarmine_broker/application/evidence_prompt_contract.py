"""Prompt-facing evidence contract compaction helpers."""
from __future__ import annotations

from typing import Any

from .prompt_values import prompt_clip_text, prompt_clip_value


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


def compact_evidence_contract_for_prompt(
    contract: dict[str, Any],
    *,
    prompt_preview_chars: int,
) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    out = {
        key: contract.get(key)
        for key in EVIDENCE_PROMPT_KEEP_KEYS
        if contract.get(key) not in (None, "", [], {})
    }
    file_memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    out["file_memory"] = [
        {
            "path": row.get("path"),
            "line_count": row.get("line_count"),
            "truncated": row.get("truncated"),
            "key_lines": prompt_clip_value(row.get("key_lines") or [], text_limit=220, list_limit=8),
            "content_excerpt": prompt_clip_text(row.get("content_excerpt"), 500),
        }
        for row in file_memory[:6]
        if isinstance(row, dict)
    ]
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
    return prompt_clip_value(out, text_limit=prompt_preview_chars, list_limit=12)


def hard_budget_evidence_contract_summary(
    contract: dict[str, Any],
    *,
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
            for key in ("final_allowed", "planner_may_choose_final", "reason")
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
    for key in ("required_next_tool_call", "forbidden_repeated_tool_calls"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = prompt_clip_value(value, text_limit=500, list_limit=8)
    for key in ("successful_repo_read_paths", "read_admissible_paths", "validator_admissible_repo_read_paths"):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = prompt_clip_value(value, text_limit=160, list_limit=5)
    return compact
