"""Evidence contract window helpers extracted from planner.py."""
from __future__ import annotations

import json
from typing import Any

from aicarmine_broker.application.prompt.values import prompt_clip_value


def _compact_evidence_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    """Imported from application.prompt.evidence_contract."""
    from aicarmine_broker.application.prompt.evidence_contract import (
        compact_evidence_contract_for_prompt as _impl,
    )
    return _impl(contract, prompt_preview_chars=24000)


def _store_prompt_value_window(
    root: str,
    *,
    section: str,
    value: Any,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Imported from planner_intrinsic_context."""
    from aicarmine_broker.application.shared.memory_tools import (
        planner_prompt_context_store_window,
    )
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return planner_prompt_context_store_window(
        root,
        section=section,
        text=text,
        query=query,
        max_chars=max(500, int(max_chars or 1000)),
        metadata=metadata or {},
    )


def _prompt_clip_text(value: Any, limit: int) -> str:
    """Imported from application.prompt.values."""
    from aicarmine_broker.application.prompt.values import prompt_clip_value
    if isinstance(value, str):
        return str(value)[:limit]
    if isinstance(value, (list, tuple)):
        return str(value)[:limit]
    return str(value)[:limit]


def json_char_len(value: Any) -> int:
    """Compute JSON serialization length."""
    return len(json.dumps(value, ensure_ascii=False, indent=2, default=str))


# Evidence contract key groups with clip limits — lookup table strategy (§8.4)
_EVIDENCE_CONTRACT_KEY_GROUPS: tuple[tuple[str, int, int], ...] = (
    # (key_group_name, text_limit, list_limit)
    ("semantic_fields", 300, 4),       # semantic_goal_classification, goal_requests_*, target_kind, resolved_*, counts, coverage, planner_may_choose_final, required_next_progress
    ("path_fields", 180, 20),          # successful_repo_read_paths, read_admissible_paths, validator_admissible_*, failed_*
    ("contract_fields", 260, 4),       # core_discovery_status, code_product_contract, finalization_contract, initial_orientation_surface
)


def windowed_evidence_contract_for_prompt(
    root: str,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a windowed evidence contract for the planner prompt.
    
    If the compact contract exceeds summary_limit, extract key groups with
    appropriate clip limits and store the full contract as a windowed document.
    """
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
    if json_char_len(compact_full) > summary_limit:
        compact: dict[str, Any] = {}
        # Lookup table strategy: iterate key groups instead of manual loops
        for group_name, text_limit, list_limit in _EVIDENCE_CONTRACT_KEY_GROUPS:
            keys = {
                "semantic_fields": (
                    "semantic_goal_classification", "goal_requests_code_product",
                    "goal_requires_code_product_report", "goal_requests_apply",
                    "action_plan_candidate", "target_kind", "resolved_goal_file",
                    "resolved_goal_scope", "successful_repo_read_count",
                    "verified_content_read_count", "minimum_read_coverage",
                    "coverage_satisfied", "covered_owner_paths",
                    "missing_owner_paths", "planner_may_choose_final",
                    "required_next_progress",
                ),
                "path_fields": (
                    "successful_repo_read_paths", "read_admissible_paths",
                    "validator_admissible_repo_read_paths", "failed_repo_read_paths",
                    "failed_repo_list_files_paths",
                ),
                "contract_fields": (
                    "core_discovery_status", "code_product_contract",
                    "finalization_contract", "initial_orientation_surface",
                ),
            }.get(group_name, ())
            for key in keys:
                value = contract.get(key)
                if value not in (None, "", [], {}):
                    compact[key] = prompt_clip_value(value, text_limit=text_limit, list_limit=list_limit)
        # Special list-only fields with different limits
        for field, field_limit in (
            ("candidate_next_actions", 6),
            ("core_discovery_candidates", 4),
        ):
            candidates = contract.get(field)
            if isinstance(candidates, list) and candidates:
                compact[field] = prompt_clip_value(candidates, text_limit=260 if field == "candidate_next_actions" else 220, list_limit=field_limit)
        # Nested operational_notes extraction
        operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
        if operational:
            compact["operational_notes"] = {
                "final_allowed": operational.get("final_allowed"),
                "next_instruction": _prompt_clip_text(operational.get("next_instruction"), 320),
                "candidate_next_actions": prompt_clip_value(
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
        from .context_windows import evidence_contract_continuation_action as _eca
        continuation = _eca(
            compact,
            history=history or [],
            window_chars=window_chars,
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact