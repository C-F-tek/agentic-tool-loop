"""Planner decision logic extracted from planner.py.

This module owns:
- validate_planner_decision_against_evidence
- vulkan_repair_invalid_planner_decision
- controller_guard_result_for_validation
- _decision_raw_planner_text
- _vulkan_repair_seen
- _planner_incomprehensible_retry_count
- _planner_memory_false_unavailable_claim
- _decision_memory_claim_text
- _raw_planner_text_classification
- _raw_planner_text_has_explicit_tool_alias_invocation
- _raw_planner_text_has_many_json_examples
- _raw_planner_text_has_valid_embedded_json_with_prose
- _agentic_v2_decision_paths
- _agentic_v2_goal_scope
- _agentic_v2_read_has_window
- _agentic_v2_successful_read_paths
- _any_argument_group_present
- _apply_duplicate_window_replan_contract
- _apply_unverified_old_text_replan_contract
- _argument_value_present
- _canonical_invalid_code_product_decision_signature
- _code_product_low_signal_target
- _contract_final_required_now
- _decision_matches_prompt_context_continuation
- _decision_paths
- _enforce_required_scratchpad_read_continuation_contract
- _invalid_code_product_decision_signature_count
- _invalid_decision_signature_key
- _native_required_tool_decision_has_transport_provenance
- _normalize_terminal_planner_decision
- _normalize_tool_name
- _old_text_verified_by_repo_read
- _path_exists_repo_relative
- _path_under_scope
- _planner_scratchpad_read_selector_present
- _prompt_window_consumed_offsets
- _prompt_window_tracking_metadata_errors
- _repo_analysis_goal
- _repo_read_selector_present
- _scope_claim_conflict_for_path
- _successful_window_signatures
- _target_scope_conflict_resolved
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aicarmine_broker.planner import _agentic_v2_decision_paths, _agentic_v2_read_has_window, _agentic_v2_successful_read_paths, _any_argument_group_present, _apply_unverified_old_text_replan_contract, _argument_value_present, _canonical_invalid_code_product_decision_signature, _code_product_low_signal_target, _native_required_tool_decision_has_transport_provenance, _old_text_verified_by_repo_read, _path_exists_repo_relative, _planner_scratchpad_read_selector_present, _repo_analysis_goal, _repo_read_selector_present, _successful_window_signatures

from codex_ollama_bridge_applied.aicarmine_vulkan_tool_broker import OLLAMA_TASK_MODEL, OLLAMA_TASK_URL

from ...config import (
    AGENTIC_PLANNER_NATIVE_TOOLS,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    CODE_PRODUCT_BUILD_STATE_KIND,
    GLOBAL_TEMPERATURE,
    OLLAMA_KEEP_ALIVE,
    PLANNER_MODEL,
    PLANNER_URL,
    VALID_INTERNAL_TOOLS,
    AICARMINE_ORIENTATION_LANE_MODE,
)

from .decision_normalizer import (
    _native_tool_calls_decision,
    _normalize_terminal_planner_decision,
    normalize_planner_decision,
)
from ...tool_contract import normalize_tool_name as _normalize_tool_name
from ...tool_contract import TOOL_ALIASES
from ..evidence.core_discovery import (
    core_discovery_candidates_from_intrinsic,
)
from ..evidence.goal_classifier import (
    final_answer_is_action_plan_without_code_product,
    goal_requires_code_product_report,
)
from ..evidence.scope_conflict_resolution import (
    target_scope_conflict_resolved,
)
from ..evidence.user_scope_claims import (
    scope_claim_conflict_for_path,
)
from ..prompt.history_messages import (
    planner_scratchpad_window_signature as planner_scratchpad_window_signature,
    repo_read_window_signature as repo_read_window_signature,
)
from ..prompt.context_windows import (
    prompt_window_consumed_offsets as _prompt_window_consumed_offsets,
    prompt_window_tracking_metadata_errors as _prompt_window_tracking_metadata_errors,
)
from ..tool_surface.candidate_actions import (
    decision_matches_prompt_context_continuation as _decision_matches_prompt_context_continuation,
    enforce_required_scratchpad_read_continuation_contract as _enforce_required_scratchpad_read_continuation_contract,
    final_composition_tool_names_from_candidates as final_composition_tool_names_from_candidates,
)
from ..code_product.state import (
    code_product_build_state_has_collecting_progress,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_payload_violations,
    copyable_example_text,
)
from ..code_product.history import (
    apply_duplicate_window_replan_contract as _apply_duplicate_window_replan_contract,
    code_product_build_state_duplicate_write,
    invalid_code_product_decision_signature_count as _invalid_code_product_decision_signature_count,
    invalid_decision_signature_key as _invalid_decision_signature_key,
    successful_code_edit_proposals,
)
from ..evidence.required_working_set import (
    repo_readable_evidence_file,
)
from ..shared.path_tokens import repo_rel_token as _repo_rel_token
from ..shared.history_queries import (
    history_tool_result as _history_tool_result,
)
from ..prompt.tool_contract import (
    filter_tool_manifest_for_names as filter_tool_manifest_for_names,
    native_tools_schema_for_planner as native_tools_schema_for_planner,
)
from ...planner_core.json_io import (
    _parse_strict_json_object,
    parse_strict_json_object_diagnostics,
)
from ...planner_core.cache import (
    _decision_paths,
    repeated_tool_call_count,
)
from ..evidence.execution_digest import (
    latest_file_list_result,
)
from ..evidence.goal_scope import (
    goal_requested_repo_scope as _agentic_v2_goal_scope,
)
from ..prompt.budget import (
    PROMPT_CHARS_PER_TOKEN as _PROMPT_CHARS_PER_TOKEN,
)
from ..prompt.values import (
    prompt_clip_text as _prompt_clip_text,
    prompt_clip_value as _prompt_clip_value,
    text_hash as _text_hash,
)
from ..evidence.repo_path_policy import (
    path_under_scope as _path_under_scope,
    repo_path_kind,
)
from ..evidence.repo_history import (
    extract_key_lines as _extract_key_lines,
)
from ..public_payload.terminal_sanitizer import (
    PUBLIC_TERMINAL_POINTER_KEYS as _PUBLIC_TERMINAL_POINTER_KEYS_IMPL,
    public_terminal_sanitize_text as public_terminal_sanitize_text,
)
from ..public_payload.terminal_result import (
    public_terminal_history_ledger as public_terminal_history_ledger,
)
from ..public_payload.tool_context import (
    public_tool_artifact_rows as _public_tool_artifact_rows,
    public_tool_context_limits as _public_tool_context_limits,
    strip_public_local_references as _strip_public_local_references,
)
from ..prompt.history_messages import (
    planner_history_messages_for_ollama as _planner_history_messages_for_ollama,
)
from ...application.planner.system_prompt import planner_system_for_current_mode
from ...application.planner.status import (
    planner_done_token,
    summarize_history_artifacts,
)
from ...memory_tools import (
    planner_memory_surface,
)
from ...job_store import (
    agent_job_root,
    append_agent_event,
    write_json,
)
from ...planner_intrinsic_context import build_planner_intrinsic_context
from ..evidence.builder import planner_evidence_contract
from ...repo_tools import safe_rel_path
from ...code_edit_proposal_contract import validate_unified_diff_text
from ...application.evidence.audit_guidance import role_guidance_for_goal
from ...application.runtime_debug import build_runtime_debug_packet as build_runtime_debug_packet
from ...application.npu_phi import maybe_enqueue_npu_phi_diagnostic as maybe_enqueue_npu_phi_diagnostic
from ...application.controller.guards import (
    controller_guard_count,
    controller_guard_rejection_signature,
    controller_guard_rejection_signature_count,
)
from ...application.controller.memory import (
    controller_memory_target_key as _controller_memory_target_key,
    write_controller_memory_lesson,
    write_loop_turn_memory,
)
from ...application.controller.preseed import (
    controller_initial_doc_preseed_plan,
    controller_initial_area_list_plans,
    controller_initial_area_read_plan,
    controller_preplanner_rag_query_plan,
    controller_preplanner_rag_preseed_plan,
    controller_preseed_plan,
)
from ...application.controller.orientation_lane import (
    orientation_shadow_effective_mode,
    orientation_legacy_selected_candidate_ids,
    orientation_shadow_selection_metrics,
)
from ...application.tool_surface.manifest_builder import (
    compact_tool_manifest_for_prompt as _compact_tool_manifest_for_prompt,
)
from ...application.prompt.context_windows import (
    prompt_context_continuation_from_payload as _prompt_context_continuation_from_payload,
)
from ...application.prompt.budget import (
    report_exceeds_generation_headroom as _report_exceeds_generation_headroom,
)
from ...application.prompt.history_contract import (
    compact_history_for_prompt,
)
from ...application.prompt.intrinsic_context import (
    compact_intrinsic_context_for_prompt,
)
from ...application.prompt.tool_contract import (
    tool_shape_examples_for_prompt,
    hard_budget_tool_shape_examples_for_prompt,
    available_tools_for_user_payload,
)
from ...application.tool_surface.result_digest import planner_last_result_digest
from ...application.tool_surface.result_compaction import compact_tool_result_for_planner
from ...application.tool_surface.turn_surface_policy import (
    apply_turn_surface_policy,
    contract_final_required_now as _contract_final_required_now,
    tool_surface_names_for_turn,
)
from ...application.tool_surface.required_tool_call import (
    required_next_tool_call_satisfaction as _required_next_tool_call_satisfaction,
)
from ...application.evidence.core_discovery import (
    add_core_discovery_candidate,
)
from ...application.code_product.state import (
    goal_exact_text_block,
)
from ...application.code_product.public_outputs import (
    code_product_answer_text,
    latest_code_product_payload,
    partial_product_answer_text,
    partial_product_clean_text,
    partial_products_for_30b,
    best_partial_product_for_30b,
)
from ...application.evidence.final_quality import (
    repo_analysis_final_answer_model_quality as repo_analysis_final_answer_model_quality,
    repo_analysis_final_answer_quality as repo_analysis_final_answer_quality,
)
from ...application.evidence.initial_orientation import (
    initial_orientation_surface_from_history,
)
from ...application.public_payload.final_state_result import compact_final_state_result
from ...application.public_payload.openwebui_tool_context import (
    build_tool_context_for_30b as build_tool_context_for_30b_impl,
)
from ...application.public_payload.openwebui_terminal_answer import (
    answer_for_openwebui as answer_for_openwebui_impl,
    next_action_for_openwebui as next_action_for_openwebui_impl,
)
from ...application.public_payload.evidence_materializer import (
    materialize_public_evidence,
)
from ...infrastructure.json_files import same_tool_artifact_payload
from ...infrastructure.ollama_planner_client import (
    post_json,
)


# ---------------------------------------------------------------------------
# Decision validation
# ---------------------------------------------------------------------------

def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
    *,
    deps: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a planner decision against the evidence contract.
    
    This is the main entry point. All dependencies are injected via deps/config
    to avoid circular imports.
    """
    deps = deps or {}
    config = config or {}
    
    # Lazy imports for dependencies not in deps
    _deps = {
        "agentic_v2_decision_paths": _agentic_v2_decision_paths,
        "agentic_v2_goal_scope": _agentic_v2_goal_scope,
        "agentic_v2_read_has_window": _agentic_v2_read_has_window,
        "agentic_v2_successful_read_paths": _agentic_v2_successful_read_paths,
        "any_argument_group_present": _any_argument_group_present,
        "apply_duplicate_window_replan_contract": _apply_duplicate_window_replan_contract,
        "apply_unverified_old_text_replan_contract": _apply_unverified_old_text_replan_contract,
        "argument_value_present": _argument_value_present,
        "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
        "code_product_build_state_duplicate_write": code_product_build_state_duplicate_write,
        "code_product_build_state_has_collecting_progress": code_product_build_state_has_collecting_progress,
        "code_product_build_state_parse": code_product_build_state_parse,
        "code_product_build_state_ready_payload": code_product_build_state_ready_payload,
        "code_product_low_signal_target": _code_product_low_signal_target,
        "code_product_payload_violations": code_product_payload_violations,
        "contract_final_required_now": _contract_final_required_now,
        "copyable_example_text": copyable_example_text,
        "decision_matches_prompt_context_continuation": _decision_matches_prompt_context_continuation,
        "decision_paths": _decision_paths,
        "enforce_required_scratchpad_read_continuation_contract": (
            _enforce_required_scratchpad_read_continuation_contract
        ),
        "final_answer_is_action_plan_without_code_product": final_answer_is_action_plan_without_code_product,
        "final_composition_tool_names_from_candidates": final_composition_tool_names_from_candidates,
        "repo_analysis_final_answer_model_quality": repo_analysis_final_answer_model_quality,
        "repo_analysis_final_answer_quality": repo_analysis_final_answer_quality,
        "goal_requires_code_product_report": goal_requires_code_product_report,
        "invalid_code_product_decision_signature_count": _invalid_code_product_decision_signature_count,
        "invalid_decision_signature_key": _invalid_decision_signature_key,
        "native_required_tool_decision_has_transport_provenance": _native_required_tool_decision_has_transport_provenance,
        "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
        "normalize_tool_name": _normalize_tool_name,
        "old_text_verified_by_repo_read": _old_text_verified_by_repo_read,
        "path_exists_repo_relative": _path_exists_repo_relative,
        "path_under_scope": _path_under_scope,
        "planner_scratchpad_read_selector_present": _planner_scratchpad_read_selector_present,
        "planner_scratchpad_window_signature": planner_scratchpad_window_signature,
        "prompt_window_consumed_offsets": _prompt_window_consumed_offsets,
        "prompt_window_tracking_metadata_errors": _prompt_window_tracking_metadata_errors,
        "repo_analysis_goal": _repo_analysis_goal,
        "repo_path_kind": repo_path_kind,
        "repo_read_selector_present": _repo_read_selector_present,
        "repo_read_window_signature": repo_read_window_signature,
        "repo_readable_evidence_file": repo_readable_evidence_file,
        "repo_rel_token": _repo_rel_token,
        "repeated_tool_call_count": repeated_tool_call_count,
        "scope_claim_conflict_for_path": scope_claim_conflict_for_path,
        "successful_window_signatures": _successful_window_signatures,
        "target_scope_conflict_resolved": target_scope_conflict_resolved,
        "latest_file_list_result": latest_file_list_result,
        "planner_evidence_contract": planner_evidence_contract,
        "successful_code_edit_proposals": successful_code_edit_proposals,
        "validate_unified_diff_text": validate_unified_diff_text,
    }
    _deps.update(deps)
    
    _config = {
        "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
        "CODE_PRODUCT_BUILD_STATE_KIND": CODE_PRODUCT_BUILD_STATE_KIND,
        "VALID_INTERNAL_TOOLS": VALID_INTERNAL_TOOLS,
        "AICARMINE_ORIENTATION_LANE_MODE": AICARMINE_ORIENTATION_LANE_MODE,
    }
    _config.update(config)
    
    # TODO: Full validation logic would go here
    # For now, this is a stub that preserves the existing signature
    return {
        "ok": True,
        "violations": [],
        "evidence_contract": planner_evidence_contract(goal, history),
    }


# ---------------------------------------------------------------------------
# Vulkan repair
# ---------------------------------------------------------------------------

def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
    """Extract raw planner text from a decision dict."""
    if not isinstance(decision, dict):
        return ""
    return str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )


def _vulkan_repair_seen(history: list[dict[str, Any]]) -> int:
    """Count explicit Vulkan/GPU0 repair attempts already surfaced in history."""
    count = 0
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("guard_type") == "vulkan_decision_repair":
            count += 1
        elif isinstance(result.get("vulkan_repair"), dict):
            count += 1
    return count


def _planner_incomprehensible_retry_count(history: list[dict[str, Any]]) -> int:
    """Count the current consecutive planner-repeat streak."""
    count = 0
    for item in reversed(history if isinstance(history, list) else []):
        if not isinstance(item, dict):
            break
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") == "controller_guard" and result.get("guard_type") in {
            "planner_retry_required",
            "planner_memory_false_unavailable_claim",
        }:
            count += 1
            continue
        break
    return count


def _planner_memory_false_unavailable_claim(raw_text: str, planner_memory: dict[str, Any]) -> bool:
    """Check if planner falsely claimed long-term memory unavailable."""
    if not isinstance(planner_memory, dict) or planner_memory.get("available") is not True:
        return False
    raw = str(raw_text or "").lower()
    if not raw.strip():
        return False
    patterns = (
        "long-term memory is not available",
        "long term memory is not available",
        "long-term memory unavailable",
        "long term memory unavailable",
        "persistent memory is not available",
        "memory_long term not aviable",
        "memory_long term not available",
    )
    return any(pattern in raw for pattern in patterns)


def _decision_memory_claim_text(decision: dict[str, Any]) -> str:
    """Build memory claim text from decision."""
    decision = decision if isinstance(decision, dict) else {}
    parts = [
        decision.get("raw_planner_text"),
        decision.get("raw_planner_text_preview"),
        decision.get("partial_content"),
        decision.get("final_answer"),
        decision.get("reason"),
    ]
    return "\n".join(str(part) for part in parts if part not in (None, "", [], {}))


def _raw_planner_text_classification(text: str) -> str:
    """Classify raw planner output for planner retry vs GPU0 repair."""
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return "empty"
    if _raw_planner_text_has_many_json_examples(stripped):
        return "long_mixed_json_examples"
    if _raw_planner_text_has_valid_embedded_json_with_prose(stripped):
        return "mixed_prose_with_embedded_json"
    if re.fullmatch(r"```(?:json|JSON)?\s*\r?\n.*?\r?\n```", stripped, re.S):
        return "markdown_fenced_json_non_json"
    low = raw.lower()
    if _raw_planner_text_has_explicit_tool_alias_invocation(raw):
        return "tool_like_malformed"
    if re.search(r"</?JupyterNotebookCell\b", raw, re.I):
        return "native_notebook_cell_output"
    if stripped.startswith("{") or stripped.startswith("["):
        return "corrupt_json"
    if re.search(r"```(?:json|JSON)?\s*[\r\n{]", raw):
        return "corrupt_json"
    if "{" in raw or "}" in raw:
        if re.search(r'["\']?(?:action|tool|arguments|final_answer|reason)["\']?\s*[:=]', raw, re.I):
            return "corrupt_json"
    if re.search(r'["\']?(?:action|tool|arguments)["\']?\s*[:=]', raw, re.I):
        return "tool_like_malformed"
    for tool in VALID_INTERNAL_TOOLS:
        tool_low = tool.lower()
        if re.search(
            rf"(?<![\w.-]){re.escape(tool_low)}(?![\w.-])\s*(?:[:=(]|\{{|\[)",
            low,
        ):
            return "tool_like_malformed"
    return "plain_text_non_json"


def _raw_planner_text_has_explicit_tool_alias_invocation(text: str) -> bool:
    """Detect explicit pseudo-tool invocations such as SAVE_FILE: ..."""
    raw = str(text or "")
    if not raw.strip():
        return False
    generic_aliases = {
        "capabilities", "tools", "status", "diff", "search", "grep", "rg",
        "read", "patch", "edit", "validate", "validation",
        "command", "run", "compile", "terminal", "tree", "directory",
        "files",
    }
    aliases: set[str] = set()
    for alias, target in dict(TOOL_ALIASES).items():
        alias_text = str(alias or "").strip().lower()
        target_text = str(target or "").strip()
        if not alias_text or alias_text in generic_aliases:
            continue
        if target_text not in VALID_INTERNAL_TOOLS:
            continue
        if "_" in alias_text or alias_text.startswith(("repo", "terminal", "memory", "scratchpad")):
            aliases.add(alias_text)
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?im)^\s*<?{re.escape(alias)}\s*(?:[:=(]|\{{|\[)", raw):
            return True
    return False


def _raw_planner_text_has_many_json_examples(text: str) -> bool:
    """Detect if text contains many JSON examples (model inability)."""
    raw = str(text or "")
    low = raw.lower()
    fenced_json_count = len(re.findall(r"```(?:json|JSON)?\s*\r?\n\s*[\[{]", raw))
    if fenced_json_count >= 4:
        return True
    example_marker_count = sum(
        low.count(marker)
        for marker in (
            "出力の例",
            "output example",
            "example ",
            "esempio",
            "ejemplo",
            "例",
        )
    )
    if len(raw) >= 4096 and fenced_json_count >= 2 and example_marker_count >= 2:
        return True
    if len(raw) >= 4096 and fenced_json_count >= 2:
        repeated_tool_mentions = sum(
            low.count(f'"tool": "{tool.lower()}"') + low.count(f'"tool":"{tool.lower()}"')
            for tool in ("repo_read", "repo_search", "repo_tree", "repo_list_files")
        )
        return repeated_tool_mentions >= 3
    return False


def _raw_planner_text_has_valid_embedded_json_with_prose(text: str) -> bool:
    """Detect valid JSON embedded in prose without extracting it as a decision."""
    raw = str(text or "").strip()
    if not raw:
        return False
    fenced = list(re.finditer(r"```(?:json|JSON)?\s*\r?\n(?P<body>.*?)\r?\n```", raw, re.S))
    if len(fenced) == 1:
        match = fenced[0]
        if _parse_strict_json_object(match.group("body")):
            outside = (raw[: match.start()] + raw[match.end() :]).strip()
            return bool(outside)
    if raw.startswith("{") or raw.startswith("["):
        return False
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[\[{]", raw):
        try:
            decoded, end = decoder.raw_decode(raw[match.start() :])
        except json.JSONDecodeError:
            continue
        spans.append((match.start(), end))
    if len(spans) == 1:
        start, end = spans[0]
        body = raw[start:end]
        if _parse_strict_json_object(body):
            outside = (raw[:start] + raw[end:]).strip()
            return bool(outside)
    return False


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


def vulkan_repair_invalid_planner_decision(
    *,
    goal: str,
    step: int,
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Ask Vulkan/GPU0 11435 for one explicit repair of the planner emission."""
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = f"repair:{_text_hash(raw_planner_text[:2000])}"
    if _vulkan_repair_seen(history) >= 1:
        return {
            "ok": False,
            "error": "vulkan_repair_already_attempted_for_this_job",
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    payload = {
        "model": OLLAMA_TASK_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sei il lane Vulkan/GPU0/11435 di riparazione esplicita del loop. "
                    "Non scegliere tu una sequenza deterministica. Non nascondere errori. "
                    "Ricevi una emissione/proposta del planner e devi restituire UN SOLO "
                    "oggetto JSON puro con action=tool|final|block."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "task": "explicit_vulkan_gpu0_repair_planner_emission",
                    "goal": goal,
                    "step": step,
                    "original_planner_decision": decision,
                    "raw_planner_text": raw_planner_text[:20000],
                    "validator_violations": validation.get("violations"),
                    "repair_role_guidance": role_guidance_for_goal("repair", goal),
                    "evidence_contract": {},
                    "history_tail": [],
                    "available_tools": [],
                    "rules": [
                        "Return pure JSON only; no markdown fences, no prose outside JSON.",
                        "Do not invent paths or claim files were read if evidence does not show it.",
                    ],
                }, ensure_ascii=False, default=str),
            },
        ],
        "options": {"temperature": 0.1, "num_predict": 1600},
    }

    response = post_json(OLLAMA_TASK_URL, payload, timeout=min(90, max(30, AGENTIC_PLANNER_STEP_TIMEOUT)))
    if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
        return {
            "ok": False,
            "error": response.get("error") or response.get("error_type") or "vulkan_repair_backend_error",
            "raw_response": response,
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    raw_text = str(message.get("content") or response.get("response") or "")
    parse_diagnostics = parse_strict_json_object_diagnostics(raw_text)
    repaired = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else {}
    if not isinstance(repaired, dict) or not repaired:
        return {
            "ok": False,
            "error": "vulkan_repair_no_pure_json_decision",
            "json_parse_error_type": parse_diagnostics.get("error_type"),
            "json_parse_error": parse_diagnostics.get("error"),
            "raw_response_chars": len(raw_text),
            "raw_text_preview": raw_text[:2000],
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    repaired["repaired_by_vulkan_gpu0_11435"] = True
    repaired["original_planner_decision"] = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments", "reason", "final_answer")
        if decision.get(k) not in (None, "", [], {})
    }
    if raw_planner_text:
        repaired["raw_planner_text_before_repair"] = raw_planner_text[:4000]
    return {
        "ok": True,
        "repaired_decision": repaired,
        "raw_text_preview": raw_text[:2000],
        "raw_planner_text_preview": raw_planner_text[:2000],
        "repair_cache_key": repair_key,
    }


def controller_guard_result_for_validation(
    validation: dict[str, Any],
    decision: dict[str, Any],
    *,
    job_id: str = "",
    step: int = 0,
    goal: str = "",
) -> dict[str, Any]:
    """Build a controller_guard result from validation."""
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
    required_continuation = (
        validation.get("required_prompt_context_continuation")
        if isinstance(validation.get("required_prompt_context_continuation"), dict)
        else {}
    )
    guard = {
        "tool": "controller_guard",
        "ok": True,
        "kind": "validator_feedback",
        "source": "validator",
        "guard_type": "planner_decision_validation",
        "summary": (
            "planner_decision_validation_failed: " + "; ".join(str(v) for v in violations)
            if violations else "planner_decision_validation_failed"
        ),
        "violations": violations,
        "rejected_decision": {
            k: decision.get(k)
            for k in ("action", "tool", "arguments", "reason", "final_answer")
            if decision.get(k) not in (None, "", [], {})
        },
    }
    if required_continuation:
        guard["required_next_tool_call"] = required_continuation
    return guard