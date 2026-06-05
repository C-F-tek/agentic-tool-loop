"""
aicarmine_broker.planner
========================
The controlled 30B planner loop.

Responsibilities:
- Post requests to 11434 (PLANNER_URL) with streaming
- Detect degenerate / role-boundary-contaminated output
- Ask Vulkan/GPU0 11435 for explicit IA repair when planner output is malformed or a tool decision is invalid
- Run the multi-step agentic loop ``run_agentic_planner_job``
- Manage job lifecycle transitions

No FastAPI routes or HTTP server code here.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path
from typing import Any

from .config import (
    AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT,
    AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
    AGENTIC_PLANNER_NATIVE_TOOLS,
    AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS,
    AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_NUM_CTX_REQUESTED,
    AGENTIC_PLANNER_NUM_PREDICT,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
    AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    AGENTIC_RESULT_COMPACT_CHARS,
    AGENTIC_PLANNER_TEMPERATURE,
    AGENT_DEFAULT_MAX_STEPS,
    AGENT_MAX_STEPS,
    LAB_REPO,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TASK_MODEL,
    OLLAMA_TASK_URL,
    PLANNER_MODEL,
    PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
    PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
    PLANNER_INTRINSIC_RAG_TOP_K,
    PLANNER_RAG_DB,
    PLANNER_RAG_EMBEDDING_BATCH_SIZE,
    PLANNER_RAG_EXTERNAL_RERANKER_URL,
    PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
    PLANNER_RAG_RERANKING_ENGINE,
    PLANNER_RAG_RERANKING_MODEL,
    PLANNER_URL,
    VALID_INTERNAL_TOOLS,
    internal_tool_prompt,
    internal_tools_list,
    ollama_options,
)
from .job_store import (
    agent_job_planner_stream_path,
    agent_job_root,
    append_agent_event,
    load_agent_job_state,
    write_agent_job_state,
    write_json,
)
from .memory_tools import (
    planner_composed_answer,
    planner_memory_surface,
    planner_prompt_context_store_window,
    runtime_sqlite_memory_write,
)
from .code_edit_proposal_contract import validate_unified_diff_text
from .planner_intrinsic_context import build_planner_intrinsic_context
from .repo_tools import safe_rel_path, terminal_environment_contract


# ---------------------------------------------------------------------------
# Planner JSON/HTTP helpers
# ---------------------------------------------------------------------------

from .planner_core.json_io import (
    _parse_strict_json_object,
    post_json,
    post_json_stream_to_file,
)
from .application.planner.decision_normalizer import (
    _final_answer_from_content_field,
    _native_tool_calls_decision,
    _normalize_final_answer_from_content,
    _normalize_final_answer_lines,
    _normalize_terminal_planner_decision,
    _single_embedded_json_decision,
    normalize_planner_decision,
)
from .application.prompt.available_tools import (
    available_tools_window_pack as _available_tools_window_pack_impl,
)
from .application.controller.diagnostics import agent_flow_diagnostics as _agent_flow_diagnostics_impl
from .application.prompt.context_windows import (
    evidence_contract_continuation_action as _evidence_contract_continuation_action_impl,
    forbidden_repeated_prompt_window_calls as _forbidden_repeated_prompt_window_calls_impl,
    planner_scratchpad_next_window_action_from_history as _planner_scratchpad_next_window_action_from_history_impl,
    prompt_context_continuation_from_payload as _prompt_context_continuation_from_payload_impl,
    prompt_context_continue_action as _prompt_context_continue_action_impl,
    prompt_window_consumed_offsets as _prompt_window_consumed_offsets_impl,
    prompt_window_tracking_metadata_errors as _prompt_window_tracking_metadata_errors_impl,
    required_working_set_continuation_action as _required_working_set_continuation_action_impl,
)
from .application.evidence.required_working_set import (
    latest_code_product_for_prompt as _latest_code_product_for_prompt_impl,
    repo_read_items_for_prompt as _repo_read_items_for_prompt_impl,
    required_working_set_for_prompt as _required_working_set_for_prompt_impl,
)
from .application.prompt.pack_builder import build_planner_user_payload as _build_planner_user_payload_impl
from .application.prompt.evidence_contract import (
    compact_evidence_contract_for_prompt as _compact_evidence_contract_for_prompt_impl,
    hard_budget_evidence_contract_summary as _hard_budget_evidence_contract_summary,
)
from .application.evidence.builder import planner_evidence_contract as _planner_evidence_contract_impl
from .application.planner.loop import run_agentic_planner_job as _run_agentic_planner_job_impl
from .application.planner.system_prompt import planner_system_for_current_mode as _planner_system_for_current_mode_impl
from .application.planner.turn import planner_decision as _planner_decision_impl
from .application.planner.validator import validate_planner_decision_against_evidence as _validate_planner_decision_against_evidence_impl
from .application.public_payload.final_state_result import compact_final_state_result as _compact_final_state_result_impl
from .application.evidence.execution_digest import (
    execution_evidence_digest_text as _execution_evidence_digest_text_impl,
    repo_read_content_views as _repo_read_content_views_impl,
)
from .application.evidence.initial_orientation import (
    initial_orientation_surface_from_history as _initial_orientation_surface_from_history_impl,
)
from .application.public_payload.openwebui_terminal_answer import (
    answer_for_openwebui as _answer_for_openwebui_impl,
    next_action_for_openwebui as _next_action_for_openwebui_impl,
)
from .application.public_payload.openwebui_tool_context import build_tool_context_for_30b as _build_tool_context_for_30b_impl
from .application.tool_surface.candidate_actions import (
    candidate_actions_from_evidence as _candidate_actions_from_evidence_impl,
    decision_matches_prompt_context_continuation as _decision_matches_prompt_context_continuation_impl,
    final_composition_tool_names_from_candidates as _final_composition_tool_names_from_candidates,
    preserve_required_next_tool_call_for_prompt as _preserve_required_next_tool_call_for_prompt_impl,
    required_next_tool_call_from_action as _required_next_tool_call_from_action_impl,
)
from .application.controller.guards import (
    controller_guard_count as _controller_guard_count_impl,
    controller_guard_rejection_signature as _controller_guard_rejection_signature_impl,
    controller_guard_rejection_signature_count as _controller_guard_rejection_signature_count_impl,
    recoverable_planner_block as _recoverable_planner_block_impl,
)
from .application.controller.memory import (
    controller_memory_lesson_text as _controller_memory_lesson_text_impl,
    loop_turn_memory_text as _loop_turn_memory_text_impl,
    write_controller_memory_lesson as _write_controller_memory_lesson_impl,
    write_loop_turn_memory as _write_loop_turn_memory_impl,
)
from .application.controller.preseed import (
    controller_initial_area_list_plans as _controller_initial_area_list_plans_impl,
    controller_initial_area_read_plan as _controller_initial_area_read_plan_impl,
    controller_initial_doc_preseed_plan as _controller_initial_doc_preseed_plan_impl,
    initial_area_file_sort_key as _initial_area_file_sort_key_impl,
    initial_area_sort_key as _initial_area_sort_key_impl,
    initial_doc_sort_key as _initial_doc_sort_key_impl,
    list_result_file_paths as _list_result_file_paths_impl,
    root_surface_dir_paths as _root_surface_dir_paths_impl,
    root_surface_entries as _root_surface_entries_impl,
    root_surface_file_paths as _root_surface_file_paths_impl,
)
from .application.evidence.core_discovery import (
    add_core_discovery_candidate as _add_core_discovery_candidate_impl,
    core_discovery_candidates_from_intrinsic as _core_discovery_candidates_from_intrinsic_impl,
    core_discovery_read_paths as _core_discovery_read_paths_impl,
)
from .application.code_product.state import (
    CODE_PRODUCT_BUILD_STATE_KIND,
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
    code_product_action_has_complete_payload as _code_product_action_has_complete_payload,
    code_product_build_state_has_collecting_progress as _code_product_build_state_has_collecting_progress,
    code_product_build_state_parse as _code_product_build_state_parse,
    code_product_build_state_ready_payload as _code_product_build_state_ready_payload,
    code_product_build_state_section as _code_product_build_state_section,
    code_product_payload_violations as _code_product_payload_violations,
    copyable_example_text as _copyable_example_text,
    goal_exact_text_block as _goal_exact_text_block,
)
from .application.code_product.public_outputs import (
    best_partial_product_for_30b as _best_partial_product_for_30b_impl,
    code_product_answer_text as _code_product_answer_text_impl,
    latest_code_product_payload as _latest_code_product_payload_impl,
    partial_product_answer_text as _partial_product_answer_text_impl,
    partial_product_clean_text as _partial_product_clean_text_impl,
    partial_products_for_30b as _partial_products_for_30b_impl,
)
from .application.code_product.history import (
    CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS as _CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS_IMPL,
    apply_duplicate_window_replan_contract as _apply_duplicate_window_replan_contract_impl,
    code_product_build_state_duplicate_write as _code_product_build_state_duplicate_write_impl,
    code_product_build_state_from_result as _code_product_build_state_from_result_impl,
    code_product_build_state_propose_action as _code_product_build_state_propose_action_impl,
    code_product_build_state_read_action as _code_product_build_state_read_action_impl,
    code_product_build_state_write_action as _code_product_build_state_write_action_impl,
    code_product_candidate_action as _code_product_candidate_action_impl,
    code_product_low_signal_target as _code_product_low_signal_target_impl,
    code_product_payload_rejection_count as _code_product_payload_rejection_count_impl,
    code_product_source_window_candidate as _code_product_source_window_candidate_impl,
    code_product_source_windows_from_reads as _code_product_source_windows_from_reads_impl,
    latest_code_product_build_state as _latest_code_product_build_state_impl,
    strip_duplicate_window_candidate as _strip_duplicate_window_candidate_impl,
    successful_repo_read_window_ranges as _successful_repo_read_window_ranges_impl,
    successful_window_signatures as _successful_window_signatures_impl,
)
from .application.evidence.goal_classifier import (
    final_answer_has_inline_code_product as _final_answer_has_inline_code_product,
    final_answer_is_action_plan_without_code_product as _final_answer_is_action_plan_without_code_product,
    goal_is_tool_envelope as _goal_is_tool_envelope,
    goal_requests_apply,
    goal_requests_code_product,
    has_any as _has_any,
    input_error_goal as _input_error_goal,
    semantic_goal_classification as _classify_goal_deliverable,
    semantic_goal_low as _semantic_goal_low,
    semantic_goal_text as _semantic_goal_text,
)
from .application.evidence.goal_scope import (
    extract_existing_goal_path as _extract_existing_goal_path_impl,
    goal_requested_repo_scope as _goal_requested_repo_scope_impl,
    requested_file_limit_from_goal as _requested_file_limit_from_goal_impl,
)
from .application.shared.history_queries import (
    failed_code_edit_proposal_validation_row as _failed_code_edit_proposal_validation_row,
    history_tool_result as _history_tool_result_impl,
    history_has_tool,
    successful_code_edit_proposals,
)
from .application.shared.clean_values import drop_empty_dict_values as _drop_empty_dict_values_impl
from .application.shared.history_ledger import (
    history_item_ollama_turn as _history_item_ollama_turn_impl,
    planner_history_ledger as _planner_history_ledger_impl,
    planner_ollama_turn_from_decision as _planner_ollama_turn_from_decision_impl,
)
from .application.prompt.history_messages import (
    LOCAL_ARTIFACT_KEYS as _LOCAL_ARTIFACT_KEYS_IMPL,
    OLLAMA_STREAM_META_KEYS as _OLLAMA_STREAM_META_KEYS_IMPL,
    PLANNER_HISTORY_NOISE_KEYS as _PLANNER_HISTORY_NOISE_KEYS_IMPL,
    clean_planner_history_value as _clean_planner_history_value_impl,
    planner_controller_guard_history_payload as _planner_controller_guard_history_payload_impl,
    planner_history_arguments as _planner_history_arguments_impl,
    planner_history_evidence_payload as _planner_history_evidence_payload_impl,
    planner_history_item_messages as _planner_history_item_messages_impl,
    planner_history_messages_for_ollama as _planner_history_messages_for_ollama_impl,
    planner_history_reason as _planner_history_reason_impl,
    planner_history_summary as _planner_history_summary_impl,
    planner_tool_result_message_payload as _planner_tool_result_message_payload_impl,
)
from .application.public_payload.tool_context import (
    PUBLIC_LOCAL_REFERENCE_KEYS as _PUBLIC_LOCAL_REFERENCE_KEYS_IMPL,
    decision_for_turn_memory as _decision_for_turn_memory_impl,
    final_summary_with_ollama_done_reasons as _final_summary_with_ollama_done_reasons_impl,
    ollama_turn_rows as _ollama_turn_rows_impl,
    ollama_turn_summary_text as _ollama_turn_summary_text_impl,
    planner_turn_memory as _planner_turn_memory_impl,
    public_tool_artifact_rows as _public_tool_artifact_rows_impl,
    public_tool_context_limits as _public_tool_context_limits_impl,
    public_tool_response as _public_tool_response_impl,
    strip_public_artifact_paths as _strip_public_artifact_paths_impl,
    strip_public_local_references as _strip_public_local_references_impl,
    successful_tool_turns as _successful_tool_turns_impl,
)
from .application.public_payload.terminal_sanitizer import (
    PUBLIC_TERMINAL_POINTER_KEYS as _PUBLIC_TERMINAL_POINTER_KEYS_IMPL,
    public_terminal_content_key as _public_terminal_content_key_impl,
    public_terminal_sanitize_text as _public_terminal_sanitize_text_impl,
    public_terminal_sanitize_value as _public_terminal_sanitize_value_impl,
)
from .application.public_payload.terminal_result import (
    public_terminal_history_ledger as _public_terminal_history_ledger_impl,
    public_terminal_result_for_30b as _public_terminal_result_for_30b_impl,
)
from .application.public_payload.terminal_context_rows import (
    executed_tool_rows as _executed_tool_rows_impl,
    planner_decision_rows as _planner_decision_rows_impl,
    terminal_context_alias as _terminal_context_alias_impl,
    validation_rejection_rows as _validation_rejection_rows_impl,
)
from .application.prompt.history_contract import (
    compact_history_for_prompt as _compact_history_for_prompt_impl,
)
from .application.prompt.intrinsic_context import (
    compact_intrinsic_context_for_prompt as _compact_intrinsic_context_for_prompt_impl,
)
from .application.shared.path_tokens import repo_rel_token as _repo_rel_token
from .application.planner.status import (
    planner_done_token as _planner_done_token_impl,
    summarize_history_artifacts as _summarize_history_artifacts_impl,
)
from .application.prompt.budget import (
    planner_token_generation_reserve as _planner_token_generation_reserve,
    prompt_budget_report as _prompt_budget_report_impl,
    prompt_compaction_threshold as _prompt_compaction_threshold,
    prompt_generation_headroom_char_budget as _prompt_generation_headroom_char_budget,
    prompt_window_chars as _prompt_window_chars,
    report_exceeds_generation_headroom as _report_exceeds_generation_headroom_impl,
)
from .application.prompt.values import (
    prompt_clip_text as _prompt_clip_text,
    prompt_clip_value as _prompt_clip_value,
    text_hash as _text_hash,
)
from .application.evidence.repo_path_policy import (
    dynamic_read_candidate_paths as _dynamic_read_candidate_paths_impl,
    low_signal_top_dir as _low_signal_top_dir_impl,
    meaningful_read_candidates_from_evidence as _meaningful_read_candidates_from_evidence_impl,
    path_under_scope as _path_under_scope_impl,
    read_candidate_sort_key as _read_candidate_sort_key_impl,
    repo_code_file as _repo_code_file_impl,
    repo_doc_or_config as _repo_doc_or_config_impl,
    repo_existing_dir as _repo_existing_dir_impl,
    repo_existing_file as _repo_existing_file_impl,
    repo_path_kind as _repo_path_kind_impl,
    repo_readable_evidence_file as _repo_readable_evidence_file_impl,
    scope_candidate_source_paths as _scope_candidate_source_paths_impl,
    scope_read_candidates_from_evidence as _scope_read_candidates_from_evidence_impl,
    top_dir as _top_dir_impl,
)
from .application.evidence.repo_history import (
    append_unique as _append_unique_impl,
    extract_headings as _extract_headings_impl,
    extract_key_lines as _extract_key_lines_impl,
    extract_mentioned_paths as _extract_mentioned_paths_impl,
    failed_repo_list_files_paths as _failed_repo_list_files_paths_impl,
    file_memory_from_history as _file_memory_from_history_impl,
    rank_core_candidates as _rank_core_candidates_impl,
    read_items_from_history as _read_items_from_history_impl,
    repo_list_evidence as _repo_list_evidence_impl,
)
from .application.evidence.scope_conflict_resolution import (
    SCOPE_CONFLICT_RATIONALE_TERMS as _SCOPE_CONFLICT_RATIONALE_TERMS_IMPL,
    target_scope_conflict_resolved as _target_scope_conflict_resolved_impl,
)
from .application.prompt.context_windows import (
    PROMPT_CONTEXT_WINDOW_COMPACT_KEYS as _PROMPT_CONTEXT_WINDOW_COMPACT_KEYS_IMPL,
    PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS as _PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS_IMPL,
    compact_prompt_context_window_item as _compact_prompt_context_window_item_impl,
)
from .application.prompt.text_windows import diff_chunks as _diff_chunks, window_text as _window_text
from .application.tool_surface.manifest_builder import (
    compact_tool_manifest_for_prompt as _compact_tool_manifest_for_prompt,
    filter_tool_manifest_for_names as _filter_tool_manifest_for_names,
    json_char_len as _json_char_len,
    native_tools_schema_for_planner as _native_tools_schema_for_planner,
    tool_schema_name as _tool_schema_name,
)
from .application.prompt.tool_contract import (
    available_tools_for_user_payload as _available_tools_for_user_payload_impl,
    tool_shape_examples_for_prompt as _tool_shape_examples_for_prompt_impl,
)
from .application.tool_surface.result_digest import planner_last_result_digest as _planner_last_result_digest_impl
from .application.tool_surface.result_compaction import compact_tool_result_for_planner as _compact_tool_result_for_planner_impl
from .application.tool_surface.turn_surface_policy import (
    apply_turn_surface_policy as _apply_turn_surface_policy_impl,
    contract_final_required_now as _contract_final_required_now,
    tool_surface_names_for_turn as _tool_surface_names_for_turn_impl,
)
from .application.evidence.user_scope_claims import (
    claim_area_from_user_token as _claim_area_from_user_token_impl,
    normalize_scope_claim_text as _normalize_scope_claim_text_impl,
    scope_claim_conflict_for_path as _scope_claim_conflict_for_path_impl,
    user_scope_claims as _user_scope_claims_impl,
)
from .application.planner.validation_rejections import (
    canonical_invalid_code_product_decision_signature as _canonical_invalid_code_product_decision_signature_impl,
    compact_validation_rejections_tail as _compact_validation_rejections_tail_impl,
    disallowed_invalid_code_product_signatures as _disallowed_invalid_code_product_signatures_impl,
    invalid_code_product_decision_signature_count as _invalid_code_product_decision_signature_count_impl,
    invalid_code_product_decision_signature_from_history_item as _invalid_code_product_decision_signature_from_history_item_impl,
    invalid_decision_signature_key as _invalid_decision_signature_key_impl,
)
from .application.prompt.window_signatures import (
    decision_paths as _decision_paths,
    planner_scratchpad_window_signature as _planner_scratchpad_window_signature,
    repo_read_window_range_for_target as _repo_read_window_range_for_target,
    repo_read_window_signature as _repo_read_window_signature,
)
from .infrastructure.json_files import same_tool_artifact_payload as _same_tool_artifact_payload_impl


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------


_PROMPT_CONTEXT_WINDOW_COMPACT_KEYS = _PROMPT_CONTEXT_WINDOW_COMPACT_KEYS_IMPL
_PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS = _PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS_IMPL


def _compact_prompt_context_window_item(item: dict[str, Any]) -> dict[str, Any]:
    return _compact_prompt_context_window_item_impl(item)


def compact_tool_result_for_planner(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    return _compact_tool_result_for_planner_impl(
        tool,
        result,
        result_compact_chars=AGENTIC_RESULT_COMPACT_CHARS,
    )


def planner_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _planner_history_ledger_impl(history)


def planner_last_result_digest(result: dict[str, Any]) -> dict[str, Any]:
    return _planner_last_result_digest_impl(result)


def _ordered_tool_names(names: set[str]) -> list[str]:
    ordered = [name for name in internal_tools_list(exclude_vulkan=False) if name in names]
    ordered.extend(sorted(name for name in names if name not in ordered))
    return ordered


def _apply_turn_surface_policy(contract: dict[str, Any]) -> dict[str, Any]:
    return _apply_turn_surface_policy_impl(contract, order_tool_names=_ordered_tool_names)


def _tool_surface_names_for_turn(
    *,
    goal: str,
    evidence_contract: dict[str, Any],
    intrinsic_context: dict[str, Any],
    prompt_context_continuation_required: dict[str, Any] | None = None,
) -> list[str]:
    return _tool_surface_names_for_turn_impl(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
        order_tool_names=_ordered_tool_names,
        prompt_context_continuation_required=prompt_context_continuation_required,
    )


def _available_tools_for_user_payload(compact_tools: list[dict[str, Any]]) -> Any:
    return _available_tools_for_user_payload_impl(
        compact_tools,
        native_tools=AGENTIC_PLANNER_NATIVE_TOOLS,
    )


def _available_tools_window_pack(
    root: Path,
    *,
    goal: str,
    available_tools: Any,
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    return _available_tools_window_pack_impl(
        root,
        goal=goal,
        available_tools=available_tools,
        window_chars=window_chars,
        reason=reason,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _tool_shape_examples_for_prompt() -> dict[str, Any]:
    return _tool_shape_examples_for_prompt_impl(
        native_tools=AGENTIC_PLANNER_NATIVE_TOOLS,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _compact_history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _compact_history_for_prompt_impl(
        history,
        history_tail=AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
        ledger_builder=planner_history_ledger,
    )


def _compact_evidence_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    return _compact_evidence_contract_for_prompt_impl(
        contract,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    )


def _windowed_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
    if _json_char_len(compact_full) > summary_limit:
        compact: dict[str, Any] = {}
        for key in (
            "semantic_goal_classification",
            "goal_requests_code_product",
            "goal_requires_code_product_report",
            "goal_requests_apply",
            "action_plan_candidate",
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
                compact[key] = _prompt_clip_value(value, text_limit=300, list_limit=4)
        for key in (
            "successful_repo_read_paths",
            "read_admissible_paths",
            "validator_admissible_repo_read_paths",
            "failed_repo_read_paths",
            "failed_repo_list_files_paths",
        ):
            value = contract.get(key)
            if value not in (None, "", [], {}):
                compact[key] = _prompt_clip_value(value, text_limit=180, list_limit=20)
        for key in (
            "core_discovery_status",
            "code_product_contract",
            "finalization_contract",
            "initial_orientation_surface",
        ):
            value = contract.get(key)
            if value not in (None, "", [], {}):
                compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
        candidates = contract.get("candidate_next_actions")
        if isinstance(candidates, list) and candidates:
            compact["candidate_next_actions"] = _prompt_clip_value(
                candidates,
                text_limit=260,
                list_limit=6,
            )
        discovery_candidates = contract.get("core_discovery_candidates")
        if isinstance(discovery_candidates, list) and discovery_candidates:
            compact["core_discovery_candidates"] = _prompt_clip_value(
                discovery_candidates,
                text_limit=220,
                list_limit=4,
            )
        operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
        if operational:
            compact["operational_notes"] = {
                "final_allowed": operational.get("final_allowed"),
                "next_instruction": _prompt_clip_text(operational.get("next_instruction"), 320),
                "candidate_next_actions": _prompt_clip_value(
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
        continuation = _evidence_contract_continuation_action(
            compact,
            history=history or [],
            window_chars=window_chars,
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact


def _prompt_section_window_pack(
    root: Path,
    *,
    goal: str,
    section: str,
    value: Any,
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    window = _store_prompt_value_window(
        root,
        section=section,
        value=value,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "planner_prompt_section",
            "section": section,
            "format": "json",
            "reason": reason,
        },
    )
    out = {
        "schema": "planner_prompt_section_window.v1",
        "store": "job_local_sqlite",
        "section": section,
        "reason": reason,
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _hard_budget_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(contract, dict) or not contract:
        return {}
    window = _store_prompt_value_window(
        root,
        section="evidence_contract:hard_budget",
        value=contract,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={"kind": "evidence_contract", "format": "json", "reason": reason},
    )
    compact = _hard_budget_evidence_contract_summary(contract, reason=reason)
    compact["full_evidence_contract_window"] = window
    if window.get("document_id") and window.get("has_more_after") is True:
        compact["planner_can_request_more_evidence_contract"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
        continuation = _evidence_contract_continuation_action(
            compact,
            history=history or [],
            window_chars=max(500, int(window_chars or 1000)),
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact


def _report_exceeds_generation_headroom(report: dict[str, Any], headroom_char_budget: int) -> bool:
    return _report_exceeds_generation_headroom_impl(report, headroom_char_budget)


def _preserve_required_next_tool_call_for_prompt(
    payload: dict[str, Any],
    previous_evidence_contract: dict[str, Any],
) -> None:
    _preserve_required_next_tool_call_for_prompt_impl(payload, previous_evidence_contract)


def _compact_intrinsic_context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    return _compact_intrinsic_context_for_prompt_impl(
        context,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    )


def _windowed_optional_context_value(
    root: Path,
    *,
    goal: str,
    key: str,
    value: Any,
    window_chars: int,
) -> Any:
    if value in (None, "", [], {}):
        return value
    if _json_char_len(value) <= max(800, int(window_chars or 1000)):
        return value
    window = _store_prompt_value_window(
        root,
        section=f"optional_context:{key}",
        value=value,
        query=goal,
        max_chars=window_chars,
        metadata={"kind": "optional_context", "key": key, "format": "json"},
    )
    out = {
        "schema": "planner_optional_context_window.v1",
        "source_key": key,
        "store": "job_local_sqlite",
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return out


def _optional_context_window_pack(
    root: Path,
    *,
    goal: str,
    optional_context: dict[str, Any],
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    source_keys = [
        str(key)
        for key, value in (optional_context or {}).items()
        if value not in (None, "", [], {})
    ]
    successful_payload_windows = (
        optional_context.get("successful_tool_payload_windows")
        if isinstance(optional_context.get("successful_tool_payload_windows"), list)
        else []
    )
    window_source = dict(optional_context or {})
    if successful_payload_windows:
        window_source.pop("successful_tool_payload_windows", None)
    window = _store_prompt_value_window(
        root,
        section="optional_context:hard_budget_pack",
        value=window_source,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "optional_context_hard_budget_pack",
            "format": "json",
            "reason": reason,
            "source_keys": source_keys,
        },
    )
    out = {
        "schema": "planner_optional_context_window_pack.v1",
        "store": "job_local_sqlite",
        "reason": reason,
        "source_keys": source_keys,
        "serialized_json_window": window,
    }
    if successful_payload_windows:
        out["successful_tool_payload_windows"] = successful_payload_windows
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _optional_context_for_prompt(
    *,
    root: Path,
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    compact_mode: bool,
    window_chars: int,
) -> dict[str, Any]:
    optional = {
        "planner_memory": _prompt_clip_value(planner_memory, text_limit=360, list_limit=4),
        "intrinsic_context": _compact_intrinsic_context_for_prompt(intrinsic_context),
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        optional["history_transport"] = {
            "schema": "planner_history_transport.v1",
            "tool_history_and_results": "ollama_messages",
            "tool_result_payloads": "sqlite_windows",
            "read_more_tool": "planner_scratchpad_read",
            "history_items_available": len(history if isinstance(history, list) else []),
        }
    else:
        optional.update({
            "history_tail": _compact_history_for_prompt(history),
            "turn_memory": _prompt_clip_value(_planner_turn_memory(history), list_limit=8),
            "last_tool_result_digest": _prompt_clip_value(
                planner_last_result_digest(last_tool_result),
                text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
                list_limit=8,
            ),
        })
    if not compact_mode:
        return optional
    tool_payload_windows: list[dict[str, Any]] = []
    for row in reversed(history if isinstance(history, list) else []):
        result = _history_tool_result(row)
        if not result.get("ok"):
            continue
        if result.get("tool") == "controller_guard":
            continue
        raw_payload = _same_tool_artifact_payload(result)
        if not isinstance(raw_payload, dict):
            continue
        raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
        if not raw_text.strip():
            continue
        window = _store_prompt_text_window(
            root,
            section=f"tool_result:{row.get('step')}:{result.get('tool')}",
            text=raw_text,
            query=goal,
            max_chars=window_chars,
            metadata={
                "kind": "successful_tool_result_payload",
                "step": row.get("step"),
                "tool": result.get("tool"),
                "format": "json",
            },
        )
        item = {
            "step": row.get("step"),
            "tool": result.get("tool"),
            "window": window,
        }
        if window.get("document_id") and window.get("has_more_after") is True:
            item["planner_can_request_more"] = {
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": "prompt_context_window",
                    "document_id": window.get("document_id"),
                    "offset": window.get("window_end"),
                    "max_chars": window_chars,
                },
            }
        tool_payload_windows.append(item)
        if len(tool_payload_windows) >= 4:
            break
    if tool_payload_windows:
        optional["successful_tool_payload_windows"] = list(reversed(tool_payload_windows))
    return {
        key: (
            value
            if key == "successful_tool_payload_windows"
            else _windowed_optional_context_value(
                root,
                goal=goal,
                key=key,
                value=value,
                window_chars=window_chars,
            )
        )
        for key, value in optional.items()
    }


def _prompt_budget_report(
    user_payload: dict[str, Any],
    *,
    system_prompt: str = "",
    extra_prompt_sections: dict[str, int] | None = None,
) -> dict[str, Any]:
    return _prompt_budget_report_impl(
        user_payload,
        system_prompt=system_prompt,
        extra_prompt_sections=extra_prompt_sections,
    )


def _read_json_file(path: str) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _repo_read_file_content_from_repo(item: dict[str, Any], known_prefix: str = "") -> tuple[str, dict[str, Any]]:
    path = _repo_rel_token(item.get("path") or "")
    meta: dict[str, Any] = {"source": "repo_file_rehydrate_unavailable", "path": path}
    if not path:
        meta["error"] = "missing_path"
        return "", meta
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        if not full.exists() or not full.is_file():
            meta["error"] = "file_not_found"
            return "", meta
        text = full.read_text(encoding="utf-8-sig", errors="replace")
        prefix = str(known_prefix or "")
        if prefix and not text.startswith(prefix):
            meta.update(
                {
                    "source": "repo_file_rehydrate_prefix_mismatch",
                    "error": "repo_file_no_longer_matches_repo_read_prefix",
                    "known_prefix_chars": len(prefix),
                    "file_chars": len(text),
                }
            )
            return "", meta
        meta.update(
            {
                "source": "repo_file_rehydrated_for_prompt_window",
                "file_chars": len(text),
                "known_prefix_matched": bool(prefix),
            }
        )
        return text, meta
    except Exception as exc:
        meta.update({"error": "repo_file_rehydrate_failed", "error_type": type(exc).__name__})
        return "", meta


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    meta = {"source": "tool_result_inline"}
    artifact = str(item.get("artifact") or "")
    content = item.get("content")
    loaded = _read_json_file(artifact)
    artifact_content = loaded.get("content")
    preview = item.get("content_preview")
    known_prefix = (
        content if isinstance(content, str)
        else artifact_content if isinstance(artifact_content, str)
        else preview if isinstance(preview, str)
        else ""
    )
    if isinstance(artifact_content, str) and artifact_content:
        inline_prefix = content if isinstance(content, str) else preview if isinstance(preview, str) else ""
        if not inline_prefix or artifact_content.startswith(inline_prefix):
            meta.update(
                {
                    "source": "repo_read_artifact_rehydrated_for_prompt",
                    "artifact": artifact,
                    "artifact_chars": len(artifact_content),
                    "inline_prefix_matched": bool(inline_prefix),
                }
            )
            return artifact_content, meta
    if item.get("truncated") is True:
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, known_prefix)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
    if isinstance(content, str) and item.get("truncated") is not True:
        return content, meta
    if isinstance(known_prefix, str) and known_prefix:
        if item.get("truncated") is True:
            meta.update(
                {
                    "source": "tool_result_inline_truncated_prefix_only",
                    "artifact": artifact,
                }
            )
        return known_prefix, meta
    if isinstance(preview, str):
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, preview)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
        meta.update({"source": "content_preview_only", "artifact": artifact})
        return preview, meta
    return "", meta


def _store_prompt_text_window(
    root: Path,
    *,
    section: str,
    text: str,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return planner_prompt_context_store_window(
        root,
        section=section,
        text=str(text or ""),
        query=query,
        max_chars=max(500, int(max_chars or 1000)),
        metadata=metadata or {},
    )


def _store_prompt_value_window(
    root: Path,
    *,
    section: str,
    value: Any,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return _store_prompt_text_window(
        root,
        section=section,
        text=text,
        query=query,
        max_chars=max_chars,
        metadata=metadata,
    )


def _prompt_window_consumed_offsets(history: list[dict[str, Any]]) -> dict[str, int]:
    return _prompt_window_consumed_offsets_impl(
        history,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _prompt_window_tracking_metadata_errors(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _prompt_window_tracking_metadata_errors_impl(
        history,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _prompt_context_continue_action(window: dict[str, Any], *, max_chars: int, reason: str) -> dict[str, Any] | None:
    return _prompt_context_continue_action_impl(
        window,
        max_chars=max_chars,
        reason=reason,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _planner_scratchpad_next_window_action_from_history(
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return _planner_scratchpad_next_window_action_from_history_impl(
        args,
        history,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _repo_read_items_for_prompt(
    history: list[dict[str, Any]],
    paths: set[str],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> list[dict[str, Any]]:
    return _repo_read_items_for_prompt_impl(
        history,
        paths,
        job_root=job_root,
        goal=goal,
        window_chars=window_chars,
        compact_mode=compact_mode,
        history_tool_result=_history_tool_result,
        repo_rel_token=_repo_rel_token,
        repo_read_item_full_content=_repo_read_item_full_content,
        store_prompt_text_window=_store_prompt_text_window,
        window_text=_window_text,
    )


def _latest_code_product_for_prompt(
    history: list[dict[str, Any]],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> dict[str, Any]:
    return _latest_code_product_for_prompt_impl(
        history,
        job_root=job_root,
        goal=goal,
        window_chars=window_chars,
        compact_mode=compact_mode,
        store_prompt_text_window=_store_prompt_text_window,
        text_hash=_text_hash,
    )


def _required_working_set_for_prompt(
    goal: str,
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    job_root: Path,
    window_chars: int,
    compact_mode: bool,
) -> dict[str, Any]:
    return _required_working_set_for_prompt_impl(
        goal,
        history,
        contract,
        job_root=job_root,
        window_chars=window_chars,
        compact_mode=compact_mode,
        repo_rel_token=_repo_rel_token,
        goal_target_file=_goal_target_file,
        latest_code_product_build_state=_latest_code_product_build_state,
        history_tool_result=_history_tool_result,
        repo_read_item_full_content=_repo_read_item_full_content,
        store_prompt_text_window=_store_prompt_text_window,
        window_text=_window_text,
        text_hash=_text_hash,
    )


def _required_working_set_continuation_action(
    required_working_set: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    return _required_working_set_continuation_action_impl(
        required_working_set,
        history=history,
        window_chars=window_chars,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _evidence_contract_continuation_action(
    evidence_contract: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    return _evidence_contract_continuation_action_impl(
        evidence_contract,
        history=history,
        window_chars=window_chars,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _prompt_context_continuation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _prompt_context_continuation_from_payload_impl(
        payload,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    return _decision_matches_prompt_context_continuation_impl(decision, continuation)


def _required_next_tool_call_from_action(action: dict[str, Any]) -> dict[str, Any]:
    return _required_next_tool_call_from_action_impl(action)


def _forbidden_repeated_prompt_window_calls(
    history: list[dict[str, Any]],
    continuation_action: dict[str, Any],
) -> list[dict[str, Any]]:
    return _forbidden_repeated_prompt_window_calls_impl(
        history,
        continuation_action,
        history_tool_result=_history_tool_result,
        required_next_tool_call_from_action=_required_next_tool_call_from_action,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _native_history_message_reserve_chars(history: list[dict[str, Any]], window_chars: int) -> int:
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        return 0
    if not any(_history_tool_result(item) for item in (history if isinstance(history, list) else [])):
        return 0
    window = max(2500, int(window_chars or 0))
    return max(6000, window + 3000)


def _build_planner_user_payload(
    *,
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    tool_manifest: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    native_tools_schema: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _build_planner_user_payload_impl(
        job_id=job_id,
        state=state,
        step=step,
        history=history,
        tool_manifest=tool_manifest,
        evidence_contract=evidence_contract,
        planner_memory=planner_memory,
        intrinsic_context=intrinsic_context,
        last_tool_result=last_tool_result,
        native_tools_schema=native_tools_schema,
        deps={
            "available_tools_for_user_payload": _available_tools_for_user_payload,
            "available_tools_window_pack": _available_tools_window_pack,
            "compact_evidence_contract_for_prompt": _compact_evidence_contract_for_prompt,
            "compact_tool_manifest_for_prompt": _compact_tool_manifest_for_prompt,
            "forbidden_repeated_prompt_window_calls": _forbidden_repeated_prompt_window_calls,
            "hard_budget_evidence_contract_for_prompt": _hard_budget_evidence_contract_for_prompt,
            "json_char_len": _json_char_len,
            "native_history_message_reserve_chars": _native_history_message_reserve_chars,
            "optional_context_for_prompt": _optional_context_for_prompt,
            "optional_context_window_pack": _optional_context_window_pack,
            "planner_system_for_current_mode": _planner_system_for_current_mode,
            "preserve_required_next_tool_call_for_prompt": _preserve_required_next_tool_call_for_prompt,
            "prompt_budget_report": _prompt_budget_report,
            "prompt_compaction_threshold": _prompt_compaction_threshold,
            "prompt_generation_headroom_char_budget": _prompt_generation_headroom_char_budget,
            "prompt_window_chars": _prompt_window_chars,
            "report_exceeds_generation_headroom": _report_exceeds_generation_headroom,
            "required_next_tool_call_from_action": _required_next_tool_call_from_action,
            "required_working_set_continuation_action": _required_working_set_continuation_action,
            "required_working_set_for_prompt": _required_working_set_for_prompt,
            "tool_shape_examples_for_prompt": _tool_shape_examples_for_prompt,
            "windowed_evidence_contract_for_prompt": _windowed_evidence_contract_for_prompt,
            "agent_job_root": agent_job_root,
            "internal_tool_prompt": internal_tool_prompt,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "AGENTIC_PLANNER_NUM_CTX": AGENTIC_PLANNER_NUM_CTX,
            "AGENTIC_PLANNER_NUM_CTX_CAP": AGENTIC_PLANNER_NUM_CTX_CAP,
            "AGENTIC_PLANNER_NUM_CTX_REQUESTED": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
            "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO": AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
            "LAB_REPO": LAB_REPO,
        },
    )


_OLLAMA_STREAM_META_KEYS = _OLLAMA_STREAM_META_KEYS_IMPL
_LOCAL_ARTIFACT_KEYS = _LOCAL_ARTIFACT_KEYS_IMPL

_PUBLIC_LOCAL_REFERENCE_KEYS = _PUBLIC_LOCAL_REFERENCE_KEYS_IMPL


def _drop_empty_dict_values(value: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty_dict_values_impl(value)


def _planner_ollama_turn_from_decision(
    decision: dict[str, Any] | None,
    *,
    step: Any = None,
) -> dict[str, Any]:
    return _planner_ollama_turn_from_decision_impl(decision, step=step)


def _history_item_ollama_turn(item: dict[str, Any]) -> dict[str, Any]:
    return _history_item_ollama_turn_impl(item)


def _history_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    return _history_tool_result_impl(item)


_PLANNER_HISTORY_NOISE_KEYS = _PLANNER_HISTORY_NOISE_KEYS_IMPL


def _planner_history_summary(value: Any) -> str:
    return _planner_history_summary_impl(value)


def _clean_planner_history_value(value: Any) -> Any:
    return _clean_planner_history_value_impl(value)


def _planner_history_arguments(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return _planner_history_arguments_impl(item, result)


def _planner_history_reason(item: dict[str, Any], result: dict[str, Any]) -> str:
    return _planner_history_reason_impl(item, result)


def _planner_controller_guard_history_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return _planner_controller_guard_history_payload_impl(item, result)


def _planner_history_evidence_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return _planner_history_evidence_payload_impl(item, result)


def _planner_tool_result_message_payload(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> dict[str, Any]:
    return _planner_tool_result_message_payload_impl(
        item,
        result,
        root=root,
        goal=goal,
        window_chars=window_chars,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _planner_history_item_messages(
    item: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> list[dict[str, Any]]:
    return _planner_history_item_messages_impl(
        item,
        root=root,
        goal=goal,
        window_chars=window_chars,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _planner_history_messages_for_ollama(
    history: list[dict[str, Any]],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _planner_history_messages_for_ollama_impl(
        history,
        root=root,
        goal=goal,
        window_chars=window_chars,
        max_chars=max_chars,
        native_tools_enabled=AGENTIC_PLANNER_NATIVE_TOOLS,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _decision_for_turn_memory(decision: dict[str, Any] | None) -> dict[str, Any]:
    return _decision_for_turn_memory_impl(decision)


def _strip_public_artifact_paths(value: Any) -> Any:
    return _strip_public_artifact_paths_impl(value)


def _strip_public_local_references(value: Any) -> Any:
    return _strip_public_local_references_impl(value)


def _same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    return _same_tool_artifact_payload_impl(result)


def _public_tool_response(tool_result: dict[str, Any]) -> dict[str, Any]:
    return _public_tool_response_impl(
        tool_result,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _successful_tool_turns(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _successful_tool_turns_impl(
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _public_tool_artifact_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _public_tool_artifact_rows_impl(
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _public_tool_context_limits(artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _public_tool_context_limits_impl(artifact_rows)


def _ollama_turn_rows(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _ollama_turn_rows_impl(history, terminal_decision)


def _planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _planner_turn_memory_impl(
        history,
        terminal_decision,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _ollama_turn_summary_text(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> str:
    return _ollama_turn_summary_text_impl(history, terminal_decision)


def _final_summary_with_ollama_done_reasons(
    status: str,
    final_summary: str,
    result: dict[str, Any],
) -> str:
    return _final_summary_with_ollama_done_reasons_impl(status, final_summary, result)


# ---------------------------------------------------------------------------
# Controller guards / loop integrity helpers
# ---------------------------------------------------------------------------


def _normalize_tool_name(value: str) -> str:
    from .tool_contract import normalize_tool_name  # noqa: PLC0415 (lazy)
    return normalize_tool_name(value)


from .planner_core.cache import (
    _cached_tool_result,
    _tool_cache_hit,
    _tool_cache_key,
    _cached_vulkan_repair_result,
    _repair_cache_key,
    repeated_tool_call_count,
)


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    return _controller_guard_count_impl(history, kind)


def _controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return _controller_guard_rejection_signature_impl(validation, decision)


def _controller_guard_rejection_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    return _controller_guard_rejection_signature_count_impl(
        history,
        signature,
        invalid_decision_signature_key=_invalid_decision_signature_key,
    )


def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    return _recoverable_planner_block_impl(decision)


def semantic_goal_classification(goal: str) -> dict[str, Any]:
    return _classify_goal_deliverable(goal, repo_analysis=_repo_analysis_goal(goal))


def goal_requires_code_product_report(goal: str) -> bool:
    classification = semantic_goal_classification(goal)
    return bool(classification.get("must_produce_code_product"))


def goal_has_write_intent(goal: str) -> bool:
    return goal_requests_apply(goal)


def _code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    return _code_product_build_state_duplicate_write_impl(
        history,
        target_file=target_file,
        text=text,
    )


def _code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
    return _code_product_build_state_from_result_impl(result)


def _latest_code_product_build_state(
    history: list[dict[str, Any]],
    target_file: str = "",
) -> dict[str, Any]:
    return _latest_code_product_build_state_impl(history, target_file)


def _code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    return _code_product_build_state_read_action_impl(state, target_file)


def _code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return _code_product_source_windows_from_reads_impl(
        history,
        target_file,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        limit=limit,
    )


def _code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _code_product_build_state_write_action_impl(
        target_file,
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
    )


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    return _code_product_build_state_propose_action_impl(state, latest_violations)


def _code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    return _code_product_candidate_action_impl(
        target_file=target_file,
        latest_violations=latest_violations,
        goal=goal,
    )


_CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS = _CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS_IMPL

def _successful_window_signatures(history: list[dict[str, Any]], tool: str) -> set[str]:
    return _successful_window_signatures_impl(history, tool)


def _successful_repo_read_window_ranges(history: list[dict[str, Any]], target_file: str) -> list[tuple[int, int]]:
    return _successful_repo_read_window_ranges_impl(history, target_file)


def _code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    return _code_product_payload_rejection_count_impl(validation_rejections, target_file)


def _code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _code_product_source_window_candidate_impl(
        target_file,
        line_count=line_count,
        history=history,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def _strip_duplicate_window_candidate(
    actions: list[dict[str, Any]],
    *,
    tool: str,
    signature: str,
) -> list[dict[str, Any]]:
    return _strip_duplicate_window_candidate_impl(actions, tool=tool, signature=signature)


def _apply_duplicate_window_replan_contract(
    contract: dict[str, Any],
    *,
    violation: str,
    tool: str,
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return _apply_duplicate_window_replan_contract_impl(
        contract,
        violation=violation,
        tool=tool,
        args=args,
        history=history,
        planner_scratchpad_next_window_action_from_history=_planner_scratchpad_next_window_action_from_history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    return _code_product_low_signal_target_impl(path, contract)


def _canonical_invalid_code_product_decision_signature(
    decision: dict[str, Any],
    violations: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    return _canonical_invalid_code_product_decision_signature_impl(decision, violations)


def _invalid_decision_signature_key(signature: dict[str, Any]) -> str:
    return _invalid_decision_signature_key_impl(signature)


def _invalid_code_product_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    return _invalid_code_product_decision_signature_from_history_item_impl(item)


def _invalid_code_product_decision_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    return _invalid_code_product_decision_signature_count_impl(history, signature)


def _disallowed_invalid_code_product_signatures(
    validation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _disallowed_invalid_code_product_signatures_impl(validation_rejections)


def _compact_validation_rejections_tail(
    validation_rejections: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    return _compact_validation_rejections_tail_impl(validation_rejections, limit=limit)


def summarize_history_artifacts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _summarize_history_artifacts_impl(history)


def planner_done_token(raw_text: str) -> bool:
    return _planner_done_token_impl(raw_text)


def extract_existing_goal_path(goal: str) -> str:
    return _extract_existing_goal_path_impl(goal, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)



# ---------------------------------------------------------------------------
# Planner evidence contract / validation gate
# ---------------------------------------------------------------------------


def requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    return _requested_file_limit_from_goal_impl(goal, default)


def goal_requested_repo_scope(goal: str) -> str:
    return _goal_requested_repo_scope_impl(goal, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def goal_requests_python_file_review(goal: str) -> bool:
    low = _semantic_goal_low(goal)
    wants_python_files = _has_any(low, ("python", ".py", "file py", "files py", "file python"))
    wants_read = _has_any(low, ("leggi", "read", "analizza", "analizzare", "descrivi", "dimmi", "serve", "servono"))
    wants_explain = _has_any(low, ("comportamento", "funzionamento", "cosa serv", "miglior", "improvement", "describe", "purpose"))
    return wants_python_files and wants_read and wants_explain


def _paths_from_result(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    raw_paths = result.get("paths_preview") or result.get("paths")
    if isinstance(raw_paths, list):
        paths.extend(str(x) for x in raw_paths if str(x).strip())
    files = result.get("files_preview") or result.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
    entries = result.get("entries_preview") or result.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
            elif isinstance(item, str) and item.strip():
                paths.append(item)
    items = result.get("items") if isinstance(result.get("items"), list) else []
    for item in items:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item.get("path")))
    out: list[str] = []
    for path in paths:
        n = _repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def _paths_from_list_rows(list_rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in list_rows if isinstance(list_rows, list) else []:
        if not isinstance(row, dict):
            continue
        for raw in row.get("paths_preview") or []:
            p = _repo_rel_token(raw)
            if p and p not in out:
                out.append(p)
    return out


def latest_file_list_result(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history):
        result = _history_tool_result(item)
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok"):
            return result
    return {}


def successful_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in history:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read":
            continue
        for sub in result.get("items") or []:
            if isinstance(sub, dict) and sub.get("ok") and sub.get("path"):
                path = _repo_rel_token(sub.get("path"))
                if path not in out:
                    out.append(path)
    return out


def _verified_repo_read_content_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repo reads whose real content is present in the same successful result.

    Compact history may contain only path metadata or content_preview. The final
    gate must count only read evidence that can be transported to OpenWebUI as a
    real tool result: either the row already has ``content`` or the same
    successful repo_read result's artifact reloads to rows with ``content``.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = _repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if not path or path == ".":
                continue
            text, content_meta = _repo_read_item_full_content(sub)
            if text in (None, ""):
                content = sub.get("content")
                text = str(content or "")
            if not text:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(_drop_empty_dict_values({
                "path": path,
                "line_count": sub.get("line_count"),
                "truncated": sub.get("truncated"),
                "content_chars": len(text),
                "source": content_meta.get("source") or "repo_read_tool_result",
            }))
    return out


def failed_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in history:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read":
            continue
        for sub in result.get("items") or []:
            if isinstance(sub, dict) and sub.get("ok") is False and sub.get("path"):
                path = str(sub.get("path"))
                if path not in out:
                    out.append(path)
    return out


def _repo_reference_mentioned(low: str) -> bool:
    return any(term in low for term in ("repo", "repository", "progetto", "project"))


def _repo_analysis_intent_mentioned(low: str) -> bool:
    return any(term in low for term in (
        "analizza", "anlizza", "analisi", "analyze", "analyse", "analysis",
        "inspect", "inspection", "esplora", "scansiona", "struttura", "structure",
        "overview", "mappa",
    ))


def _repo_analysis_goal(goal: str) -> bool:
    low = _semantic_goal_low(goal)
    repo_terms = (
        "analyze the repository", "analizza la repo", "analizza il repo",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "repository structure", "repo structure", "struttura repo",
        "analyze repo", "analisi repo", "structure and content",
        "project inspection", "local project evidence",
        "documentation", "documentazione", "docs", "examples", "diagrams",
        "gpu coordination", "heap pointer", "recovery turns",
        "deferred evidence", "packet_review_only", "gpu1", "gpu0",
        "npu sidecar",
    )
    scoped_terms = (
        "analyze the ", "analyse the ", "analizza ", "analisi ",
        "directory", "cartella", "folder", "path",
    )
    write_terms = ("patch", "fix", "modifica", "correggi", "apply", "write", "edit")
    if any(t in low for t in write_terms):
        return False
    if _input_error_goal(goal):
        return False
    if any(t in low for t in repo_terms):
        return True
    if _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low):
        return True
    # Scoped inspection requests such as "analyze the ai_carmine directory" are
    # repository-analysis goals even if they do not say "repository".  Without
    # this, final_allowed falls through to the generic default after one root
    # repo_tree and produces the repeated template answer.
    if goal_requested_repo_scope(goal) and any(t in low for t in scoped_terms):
        return True
    return False


def _should_preseed_root_surface(goal: str, original_args: dict[str, Any]) -> bool:
    """Decide whether the controller should expose root surface evidence first.

    This is deterministic evidence collection for clear, sparse repo-analysis
    goals. It does not choose the next planner action and does not finalize.
    """
    args = original_args if isinstance(original_args, dict) else {}
    requested_function = str(args.get("function") or "").strip()
    if requested_function == "repo_tree":
        return True
    if _input_error_goal(goal) or goal_has_write_intent(goal):
        return False
    low = _semantic_goal_low(goal)
    generic_repo_terms = (
        "analizza la repo", "analizza il repo", "analizza la repository",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "analisi repo", "analisi della repo", "analisi della repository",
        "analyze repo", "analyze the repo", "analyze the repository",
        "repository analysis", "repo analysis", "repo structure",
        "repository structure", "struttura repo", "struttura della repo",
        "struttura della repository", "project structure", "surface project",
        "suggerimenti implementativi", "implementation suggestions",
        "dai suggerimenti", "find problems", "trova problemi",
    )
    return any(term in low for term in generic_repo_terms) or (
        _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low)
    )


def _goal_target_file(goal: str) -> str:
    return extract_existing_goal_path(goal)


def _goal_target_scope(goal: str) -> str:
    if _goal_target_file(goal):
        return ""
    return _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)


def _goal_target_kind(goal: str) -> str:
    if _goal_target_file(goal):
        return "file"
    if _goal_target_scope(goal):
        return "directory"
    if _repo_analysis_goal(goal):
        return "repository"
    return "other"


def _controller_memory_target_key(goal: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    target_file = str(contract.get("resolved_goal_file") or _goal_target_file(goal) or "")
    if target_file:
        return "file:" + _repo_rel_token(target_file)
    target_scope = str(contract.get("resolved_goal_scope") or _goal_target_scope(goal) or "")
    if target_scope:
        return "scope:" + _repo_rel_token(target_scope)
    return "repo:root" if _repo_analysis_goal(goal) else "goal:general"


def _single_file_prompt_read_chars() -> int:
    return max(2000, min(10000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000) // 2))


def _multi_file_prompt_read_chars() -> int:
    return max(2000, min(6000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000) // 4))


def _controller_preseed_plan(goal: str, original_args: dict[str, Any]) -> dict[str, Any] | None:
    target_file = _goal_target_file(goal)
    if target_file:
        return {
            "event": "controller_preseed_file_surface",
            "result_event": "controller_preseed_file_surface_result",
            "tool": "repo_read",
            "arguments": {"path": target_file, "max_chars": _single_file_prompt_read_chars()},
            "reason": "explicit_file_request_needs_file_surface",
            "artifact_suffix": "file_surface-repo_read",
        }
    target_scope = _goal_target_scope(goal)
    if target_scope:
        return {
            "event": "controller_preseed_scope_surface",
            "result_event": "controller_preseed_scope_surface_result",
            "tool": "repo_list_files",
            "arguments": {"path": target_scope, "limit": 120},
            "reason": "explicit_directory_request_needs_scope_surface",
            "artifact_suffix": "scope_surface-repo_list_files",
        }
    if _should_preseed_root_surface(goal, original_args):
        return {
            "event": "controller_preseed_root_surface",
            "result_event": "controller_preseed_root_surface_result",
            "tool": "repo_tree",
            "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
            "reason": "generic_repo_request_needs_root_surface",
            "artifact_suffix": "root_surface-repo_tree",
            "dynamic_initial_orientation": True,
        }
    return None


def _controller_file_code_product_orientation_preseed_plan(goal: str) -> dict[str, Any] | None:
    if not _goal_target_file(goal) or not goal_requires_code_product_report(goal):
        return None
    return {
        "event": "controller_preseed_file_code_product_orientation",
        "result_event": "controller_preseed_file_code_product_orientation_result",
        "tool": "repo_tree",
        "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
        "reason": "file_code_product_request_needs_dynamic_repo_orientation",
        "artifact_suffix": "file_code_product_orientation-repo_tree",
        "dynamic_initial_orientation": True,
    }


SCOPED_CONCRETE_READ_TARGET = 10
REPO_CONCRETE_READ_TARGET = 20

_NAMED_READ_PRIORITY = {
    "agents.md": 0,
    "readme.md": 1,
}

_INITIAL_DOC_NAME_PRIORITY = {
    "AGENTS.md": 0,
    "README.md": 1,
}

_GENERIC_READABLE_SUFFIXES = (
    ".bat", ".c", ".cfg", ".cmd", ".cpp", ".cs", ".csv", ".go", ".h",
    ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".md", ".ps1", ".py",
    ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
)


def _repo_existing_file(path: str) -> bool:
    return _repo_existing_file_impl(path, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def _repo_existing_dir(path: str) -> bool:
    return _repo_existing_dir_impl(path, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def _root_surface_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    return _root_surface_entries_impl(result, repo_root=LAB_REPO)


def _root_surface_file_paths(result: dict[str, Any]) -> list[str]:
    return _root_surface_file_paths_impl(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def _root_surface_dir_paths(result: dict[str, Any]) -> list[str]:
    return _root_surface_dir_paths_impl(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def _initial_doc_sort_key(path: str) -> tuple[int, int, str]:
    return _initial_doc_sort_key_impl(path, named_read_priority=_NAMED_READ_PRIORITY)


def _controller_initial_doc_preseed_plan(root_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return _controller_initial_doc_preseed_plan_impl(
        root_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        initial_doc_name_priority=_INITIAL_DOC_NAME_PRIORITY,
        scoped_concrete_read_target=SCOPED_CONCRETE_READ_TARGET,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars(),
    )


def _initial_area_sort_key(path: str) -> tuple[int, str]:
    return _initial_area_sort_key_impl(path)


def _controller_initial_area_list_plans(root_result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _controller_initial_area_list_plans_impl(
        root_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )


def _list_result_file_paths(result: dict[str, Any]) -> list[str]:
    return _list_result_file_paths_impl(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def _initial_area_file_sort_key(path: str) -> tuple[int, int, str]:
    return _initial_area_file_sort_key_impl(
        path,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
    )


def _controller_initial_area_read_plan(list_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return _controller_initial_area_read_plan_impl(
        list_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def _repo_path_kind(path: str) -> str:
    return _repo_path_kind_impl(path, repo_root=LAB_REPO)


def _repo_doc_or_config(path: str) -> bool:
    return _repo_doc_or_config_impl(path, repo_root=LAB_REPO)


def _repo_code_file(path: str) -> bool:
    return _repo_code_file_impl(path)


def _repo_readable_evidence_file(path: str) -> bool:
    return _repo_readable_evidence_file_impl(
        path,
        repo_root=LAB_REPO,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def _read_candidate_sort_key(path: str) -> tuple[int, int, int, int, str]:
    return _read_candidate_sort_key_impl(
        path,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
    )


def _dynamic_read_candidate_paths(
    paths: list[str],
    *,
    read_ok: set[str] | None = None,
    target_scope: str = "",
) -> list[str]:
    return _dynamic_read_candidate_paths_impl(
        paths,
        read_ok=read_ok,
        target_scope=target_scope,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def _scope_candidate_source_paths(list_rows: list[dict[str, Any]], target_scope: str) -> list[str]:
    return _scope_candidate_source_paths_impl(list_rows, target_scope)


def _scope_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    target_scope: str,
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    return _scope_read_candidates_from_evidence_impl(
        list_rows,
        target_scope,
        read_ok=read_ok,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def _meaningful_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    return _meaningful_read_candidates_from_evidence_impl(
        list_rows,
        read_ok=read_ok,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def _scoped_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(SCOPED_CONCRETE_READ_TARGET, len(available_candidates))


def _repo_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(REPO_CONCRETE_READ_TARGET, len(available_candidates))


def _top_dir(path: str) -> str:
    return _top_dir_impl(path)


def _low_signal_top_dir(path: str) -> bool:
    return _low_signal_top_dir_impl(path)


def _append_unique(seq: list[Any], value: Any) -> None:
    _append_unique_impl(seq, value)


def _read_items_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _read_items_from_history_impl(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def _extract_headings(content: str) -> list[str]:
    return _extract_headings_impl(content)


def _extract_key_lines(content: str) -> list[str]:
    return _extract_key_lines_impl(content)


def _extract_mentioned_paths(content: str) -> list[str]:
    return _extract_mentioned_paths_impl(content)


def _file_memory_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _file_memory_from_history_impl(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def _repo_list_evidence(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _repo_list_evidence_impl(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def failed_repo_list_files_paths(history: list[dict[str, Any]]) -> list[str]:
    return _failed_repo_list_files_paths_impl(history)


def _rank_core_candidates(file_memory: list[dict[str, Any]], list_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _rank_core_candidates_impl(
        file_memory,
        list_rows,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )


def _normalize_scope_claim_text(text: str) -> str:
    return _normalize_scope_claim_text_impl(text)


def _claim_area_from_user_token(raw_area: str, target_scope: str = "") -> str:
    return _claim_area_from_user_token_impl(
        raw_area,
        target_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
    )


def _user_scope_claims(goal: str, target_scope: str = "") -> list[dict[str, Any]]:
    return _user_scope_claims_impl(
        goal,
        target_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
    )


def _scope_claim_conflict_for_path(path: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    return _scope_claim_conflict_for_path_impl(path, claims)


def _add_core_discovery_candidate(
    out: list[dict[str, Any]],
    seen: set[str],
    *,
    path: str,
    source: str,
    rank: int,
    reason: str,
    read_ok: set[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
    score: Any = None,
    ranking_source: str = "",
) -> bool:
    return _add_core_discovery_candidate_impl(
        out,
        seen,
        path=path,
        source=source,
        rank=rank,
        reason=reason,
        read_ok=read_ok,
        target_scope=target_scope,
        user_scope_claims=user_scope_claims,
        lab_repo_label=str(LAB_REPO),
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=_repo_readable_evidence_file,
        score=score,
        ranking_source=ranking_source,
    )


def _core_discovery_candidates_from_intrinsic(
    *,
    intrinsic_context: dict[str, Any] | None,
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return _core_discovery_candidates_from_intrinsic_impl(
        intrinsic_context=intrinsic_context,
        list_rows=list_rows,
        read_ok=read_ok,
        target_scope=target_scope,
        user_scope_claims=user_scope_claims,
        lab_repo_label=str(LAB_REPO),
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=_repo_readable_evidence_file,
        scope_read_candidates_from_evidence=lambda rows, scope, read_ok_set: _scope_read_candidates_from_evidence(
            rows,
            scope,
            read_ok=read_ok_set,
        ),
        meaningful_read_candidates_from_evidence=lambda rows, read_ok_set: _meaningful_read_candidates_from_evidence(
            rows,
            read_ok=read_ok_set,
        ),
    )


def _core_discovery_read_paths(
    candidates: list[dict[str, Any]] | None,
    *,
    read_ok: set[str],
    target_scope: str,
    limit: int,
) -> list[str]:
    return _core_discovery_read_paths_impl(
        candidates,
        read_ok=read_ok,
        target_scope=target_scope,
        limit=limit,
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=_repo_readable_evidence_file,
    )


_SCOPE_CONFLICT_RATIONALE_TERMS = _SCOPE_CONFLICT_RATIONALE_TERMS_IMPL


def _target_scope_conflict_resolved(path: str, args: dict[str, Any], contract: dict[str, Any]) -> bool:
    return _target_scope_conflict_resolved_impl(path, args, contract)


def _candidate_actions_from_evidence(
    goal: str,
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    final_allowed: bool,
    failed_list_paths: list[str] | None = None,
    core_discovery_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _candidate_actions_from_evidence_impl(
        goal,
        file_memory,
        list_rows,
        read_ok,
        final_allowed,
        failed_list_paths=failed_list_paths,
        core_discovery_candidates=core_discovery_candidates,
        repo_rel_token=_repo_rel_token,
        repo_analysis_goal=_repo_analysis_goal,
        repo_doc_or_config=_repo_doc_or_config,
        low_signal_top_dir=_low_signal_top_dir,
        rank_core_candidates=_rank_core_candidates,
        path_exists_repo_relative=_path_exists_repo_relative,
        goal_target_scope=_goal_target_scope,
        input_error_goal=_input_error_goal,
        path_under_scope=_path_under_scope,
        core_discovery_read_paths=_core_discovery_read_paths,
        scoped_concrete_read_target=SCOPED_CONCRETE_READ_TARGET,
        repo_concrete_read_target=REPO_CONCRETE_READ_TARGET,
        scope_read_candidates_from_evidence=_scope_read_candidates_from_evidence,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars,
        meaningful_read_candidates_from_evidence=_meaningful_read_candidates_from_evidence,
        single_file_prompt_read_chars=_single_file_prompt_read_chars,
        repo_code_file=_repo_code_file,
    )



def _final_answer_too_shallow(final_answer: str, contract: dict[str, Any]) -> bool:
    text = str(final_answer or "")
    low = text.lower()
    if not text.strip():
        return True
    memory = contract.get("file_memory") if isinstance(contract, dict) else []
    notebook = contract.get("operational_notes") if isinstance(contract, dict) else {}
    if not isinstance(memory, list) or not memory:
        return len(text.strip()) < 500

    required_words = ("workflow", "entrypoint", "core", "proble", "limit")
    if any(w not in low for w in required_words):
        return True

    evidence_paths: list[str] = []
    for item in memory:
        if not isinstance(item, dict):
            continue
        _append_unique(evidence_paths, item.get("path"))
        for p in item.get("mentioned_paths") or []:
            _append_unique(evidence_paths, p)
    concrete_hits = sum(1 for p in evidence_paths if p and p in text)
    read_hit = any((item.get("path") in text) for item in memory if isinstance(item, dict))
    generic_loop = (
        "core directories are" in low
        and low.count("strong candidate") >= 2
        and concrete_hits < 4
    )
    return generic_loop or concrete_hits < 4 or not read_hit or len(text.strip()) < 1000


def _build_operational_notebook(goal: str, contract: dict[str, Any]) -> dict[str, Any]:
    memory = contract.get("file_memory") if isinstance(contract, dict) else []
    list_rows = contract.get("repo_list_files_evidence") if isinstance(contract, dict) else []
    core = contract.get("ranked_core_candidate_dirs") or []
    final_allowed = bool((contract.get("finalization_contract") or {}).get("final_allowed")) if isinstance(contract, dict) else False
    return {
        "schema": "agentic_loop_operational_notes.v1",
        "goal": goal,
        "final_allowed": final_allowed,
        "next_instruction": (
            "Quality gate is satisfied. Stop navigation/listing and produce final from read_notes, "
            "mentioned_paths, core_candidates, workflow/problems evidence, and limits."
            if final_allowed else
            "Continue only with one evidence-bound unread doc/code candidate. Do not repeat prior tool calls."
        ),
        "read_notes": [
            {
                "path": item.get("path"),
                "headings": (item.get("headings") or [])[:8],
                "key_lines": (item.get("key_lines") or [])[:10],
                "mentioned_paths": (item.get("mentioned_paths") or [])[:14],
                "excerpt": str(item.get("content_excerpt") or "")[:700],
            }
            for item in memory[:18] if isinstance(item, dict)
        ],
        "list_notes": list_rows[-8:] if isinstance(list_rows, list) else [],
        "core_candidates": core[:8] if isinstance(core, list) else [],
        "candidate_next_actions": contract.get("candidate_next_actions") or [],
        "recent_rejections": (contract.get("validation_rejections_tail") or [])[-8:] if isinstance(contract.get("validation_rejections_tail"), list) else [],
        "known_problem": (
            "Do not reduce this job to path counters or directory names. Use read_notes as the working scratchpad "
            "and cite concrete evidence from them."
        ),
    }


def _initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _initial_orientation_surface_from_history_impl(
        history,
        skipped,
        repo_rel_token=_repo_rel_token,
        repo_doc_or_config=_repo_doc_or_config,
        low_signal_top_dir=_low_signal_top_dir,
        path_under_scope=_path_under_scope,
    )


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _planner_evidence_contract_impl(
        goal,
        history,
        intrinsic_context,
        deps={
            "agentic_v2_decision_paths": _agentic_v2_decision_paths,
            "agentic_v2_enrich_evidence_contract": _agentic_v2_enrich_evidence_contract,
            "agentic_v2_goal_scope": _agentic_v2_goal_scope,
            "apply_turn_surface_policy": _apply_turn_surface_policy,
            "build_operational_notebook": _build_operational_notebook,
            "candidate_actions_from_evidence": _candidate_actions_from_evidence,
            "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
            "code_product_action_has_complete_payload": _code_product_action_has_complete_payload,
            "code_product_build_state_propose_action": _code_product_build_state_propose_action,
            "code_product_build_state_read_action": _code_product_build_state_read_action,
            "code_product_build_state_write_action": _code_product_build_state_write_action,
            "code_product_candidate_action": _code_product_candidate_action,
            "code_product_payload_rejection_count": _code_product_payload_rejection_count,
            "code_product_payload_violations": _code_product_payload_violations,
            "code_product_source_window_candidate": _code_product_source_window_candidate,
            "compact_validation_rejections_tail": _compact_validation_rejections_tail,
            "core_discovery_candidates_from_intrinsic": _core_discovery_candidates_from_intrinsic,
            "disallowed_invalid_code_product_signatures": _disallowed_invalid_code_product_signatures,
            "failed_code_edit_proposal_validation_row": _failed_code_edit_proposal_validation_row,
            "file_memory_from_history": _file_memory_from_history,
            "goal_exact_text_block": _goal_exact_text_block,
            "goal_target_file": _goal_target_file,
            "goal_target_kind": _goal_target_kind,
            "initial_orientation_surface_from_history": _initial_orientation_surface_from_history,
            "input_error_goal": _input_error_goal,
            "latest_code_product_build_state": _latest_code_product_build_state,
            "low_signal_top_dir": _low_signal_top_dir,
            "meaningful_read_candidates_from_evidence": _meaningful_read_candidates_from_evidence,
            "path_under_scope": _path_under_scope,
            "paths_from_list_rows": _paths_from_list_rows,
            "paths_from_result": _paths_from_result,
            "rank_core_candidates": _rank_core_candidates,
            "repo_analysis_goal": _repo_analysis_goal,
            "repo_code_file": _repo_code_file,
            "repo_doc_or_config": _repo_doc_or_config,
            "repo_list_evidence": _repo_list_evidence,
            "repo_readable_evidence_file": _repo_readable_evidence_file,
            "repo_rel_token": _repo_rel_token,
            "repo_required_read_count": _repo_required_read_count,
            "scope_read_candidates_from_evidence": _scope_read_candidates_from_evidence,
            "scoped_required_read_count": _scoped_required_read_count,
            "user_scope_claims": _user_scope_claims,
            "verified_repo_read_content_rows": _verified_repo_read_content_rows,
            "goal_requested_repo_scope": goal_requested_repo_scope,
            "goal_requests_apply": goal_requests_apply,
            "goal_requests_code_product": goal_requests_code_product,
            "goal_requests_python_file_review": goal_requests_python_file_review,
            "history_has_tool": history_has_tool,
            "latest_file_list_result": latest_file_list_result,
            "requested_file_limit_from_goal": requested_file_limit_from_goal,
            "semantic_goal_classification": semantic_goal_classification,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "successful_repo_read_paths": successful_repo_read_paths,
            "failed_repo_read_paths": failed_repo_read_paths,
            "failed_repo_list_files_paths": failed_repo_list_files_paths,
        },
        config={
            "CODE_PRODUCT_BUILD_STATE_KIND": CODE_PRODUCT_BUILD_STATE_KIND,
            "LAB_REPO": LAB_REPO,
            "REPO_CONCRETE_READ_TARGET": REPO_CONCRETE_READ_TARGET,
            "SCOPED_CONCRETE_READ_TARGET": SCOPED_CONCRETE_READ_TARGET,
        },
    )

def _path_exists_repo_relative(path: str) -> bool:
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists()
    except Exception:
        return False


def _path_under_scope(path: str, scope: str) -> bool:
    return _path_under_scope_impl(path, scope)

# --- agentic-loop-v2 progress/scope helpers ---
def _agentic_v2_alias_repo_path(path: Any) -> str:
    # Normalize repo-relative paths and map the user's ai_carmine alias.
    # The repository directory visible in evidence is ia_carmine. Users and the
    # outer model often say ai_carmine. Do not silently execute a different tool
    # path; use this only for validation/evidence guidance so the planner is told
    # which real path exists.
    p = _repo_rel_token(path)
    try:
        if (p == "ai_carmine" or p.startswith("ai_carmine/")) and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine" + p[len("ai_carmine"):]
    except Exception:
        pass
    return p


def _agentic_v2_goal_scope(goal: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    scope = _repo_rel_token(contract.get("resolved_goal_scope") or "")
    if scope and scope != ".":
        return scope
    low = _semantic_goal_low(goal).replace("\\", "/")
    try:
        if "ai_carmine" in low and (LAB_REPO / "ia_carmine").is_dir() and not (LAB_REPO / "ai_carmine").exists():
            return "ia_carmine"
        if "ia_carmine" in low:
            return "ia_carmine"
    except Exception:
        if "ai_carmine" in low or "ia_carmine" in low:
            return "ia_carmine"
    return ""


def _agentic_v2_decision_paths(tool: str, args: dict[str, Any]) -> list[str]:
    args = args if isinstance(args, dict) else {}
    paths: list[str] = []

    def add(value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for key in ("path", "file", "filename", "target_file", "target_path"):
                if value.get(key):
                    add(value.get(key))
            return
        p = _agentic_v2_alias_repo_path(value)
        if p and p not in paths:
            paths.append(p)

    if tool in {"repo_list_files", "repo_tree", "repo_search"}:
        add(args.get("path") or ".")
    elif tool == "repo_read":
        add(args.get("path"))
        add(args.get("paths"))
        add(args.get("file"))
        add(args.get("files"))
        add(args.get("item"))
        add(args.get("items"))
    elif tool in {"repo_write_file", "repo_apply_patch", "repo_propose_code_edit"}:
        add(args.get("path"))
        add(args.get("paths"))
        add(args.get("target_file"))
        add(args.get("target_path"))
    return paths


def _agentic_v2_read_has_window(args: dict[str, Any]) -> bool:
    args = args if isinstance(args, dict) else {}
    return any(k in args for k in (
        "start", "start_line", "end", "end_line", "offset", "limit",
        "line", "line_start", "line_count", "before", "after",
        "max_chars", "window", "chunk", "range",
    ))


def _agentic_v2_repo_list_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = _history_tool_result(item)
        if result.get("tool") != "repo_list_files" or not result.get("ok"):
            continue
        paths: list[str] = []
        for key in ("paths", "paths_preview"):
            value = result.get(key)
            if isinstance(value, list):
                for raw in value:
                    if isinstance(raw, dict):
                        raw = raw.get("path")
                    p = _agentic_v2_alias_repo_path(raw)
                    if p and p not in paths:
                        paths.append(p)
        rows.append({
            "step": item.get("step"),
            "path": _agentic_v2_alias_repo_path(result.get("path") or "."),
            "total_matches": result.get("total_matches"),
            "limit": result.get("limit"),
            "truncated": result.get("truncated"),
            "paths": paths,
        })
    return rows


def _agentic_v2_successful_read_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    try:
        for p in _extract_successful_repo_read_paths(history):
            n = _agentic_v2_alias_repo_path(p)
            if n and n not in paths:
                paths.append(n)
    except Exception:
        pass
    if paths:
        return paths
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        for value in (result.get("paths"), result.get("path")):
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                for raw in value:
                    if raw in (None, "", [], {}):
                        continue
                    n = _agentic_v2_alias_repo_path(raw)
                    if n and n not in paths:
                        paths.append(n)
            else:
                n = _agentic_v2_alias_repo_path(value)
                if n and n not in paths:
                    paths.append(n)
        for read_item in result.get("items") or []:
            if isinstance(read_item, dict) and read_item.get("ok") and read_item.get("path") not in (None, "", [], {}):
                n = _agentic_v2_alias_repo_path(read_item.get("path"))
                if n and n not in paths:
                    paths.append(n)
    return paths


def _agentic_v2_enrich_evidence_contract(contract: dict[str, Any], goal: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        contract = {}
    history = history if isinstance(history, list) else []
    scope = _agentic_v2_goal_scope(goal, contract)
    list_rows = _agentic_v2_repo_list_rows(history)
    successful_reads = _agentic_v2_successful_read_paths(history)

    known_all: list[str] = []
    for row in list_rows:
        for p in row.get("paths") or []:
            if p not in known_all:
                known_all.append(p)

    in_scope: list[str] = []
    if scope:
        for p in known_all:
            if _path_under_scope(p, scope) and p not in in_scope:
                in_scope.append(p)

    latest_in_scope = next((row for row in reversed(list_rows) if scope and _path_under_scope(row.get("path") or ".", scope)), None)
    latest_any = list_rows[-1] if list_rows else None
    already_read = set(successful_reads)
    unread_in_scope = _dynamic_read_candidate_paths(in_scope, read_ok=already_read, target_scope=scope)

    contract["resolved_goal_scope"] = scope or contract.get("resolved_goal_scope")
    contract["path_aliases"] = {"ai_carmine": "ia_carmine"} if scope == "ia_carmine" else contract.get("path_aliases", {})
    contract["repo_list_files_evidence"] = [
        {k: v for k, v in {
            "step": row.get("step"),
            "path": row.get("path"),
            "total_matches": row.get("total_matches"),
            "limit": row.get("limit"),
            "truncated": row.get("truncated"),
            "paths_preview": (row.get("paths") or [])[:20],
        }.items() if v not in (None, "", [], {})}
        for row in list_rows[-8:]
    ]
    if scope:
        scoped_latest_paths = list((latest_in_scope or {}).get("paths") or in_scope)
        if scoped_latest_paths:
            # Keep the legacy field useful for the existing validator/prompt:
            # prefer the latest in-scope list over a later accidental root list.
            contract["known_paths_from_latest_repo_list_files"] = scoped_latest_paths[:80]
            contract["known_paths_total_in_latest_digest"] = len(scoped_latest_paths)
    contract["known_in_scope_paths_from_repo_list_files"] = in_scope[:80]
    contract["known_in_scope_paths_total"] = len(in_scope)
    contract["latest_in_scope_repo_list_path"] = latest_in_scope.get("path") if latest_in_scope else None
    contract["latest_repo_list_path"] = latest_any.get("path") if latest_any else None
    contract["successful_repo_read_paths"] = successful_reads
    contract["forbidden_repeated_repo_read_paths"] = successful_reads[:40]
    contract["unread_in_scope_candidate_paths"] = unread_in_scope[:40]

    guidance: list[str] = []
    if scope:
        guidance.append(f"Stay under resolved_goal_scope={scope}; do not call repo_list_files with path='.' or omitted path.")
    if successful_reads:
        guidance.append("Do not repo_read already successful paths: " + ", ".join(successful_reads[:8]))
    if unread_in_scope:
        guidance.append("Next valid progress can be repo_read one unread in-scope candidate or repo_list_files a new subdirectory under scope: " + ", ".join(unread_in_scope[:8]))
    elif latest_in_scope:
        guidance.append("If current in-scope evidence is enough, choose final and cite the read/list evidence already in history.")
    guidance.append("Controller validates only; planner must decide the next tool or final from these evidence-bound candidates.")
    contract["required_next_progress"] = " ".join(guidance)
    return contract



def _argument_value_present(args: dict[str, Any], key: str) -> bool:
    value = (args if isinstance(args, dict) else {}).get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _argument_group_present(args: dict[str, Any], keys: list[str] | tuple[str, ...]) -> bool:
    return all(_argument_value_present(args, str(key)) for key in keys)


def _any_argument_group_present(args: dict[str, Any], groups: list[list[str]] | tuple[tuple[str, ...], ...]) -> bool:
    return any(_argument_group_present(args, [str(key) for key in group]) for group in groups)


def _planner_scratchpad_read_selector_present(args: dict[str, Any]) -> bool:
    args = args if isinstance(args, dict) else {}
    kind = str(args.get("kind") or "")
    if kind in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
        return _any_argument_group_present(
            args,
            [["document_id"], ["section"], ["tag"], ["query"], ["target_file"]],
        )
    return _any_argument_group_present(
        args,
        [["document_id"], ["section"], ["tag"], ["query"], ["kind"]],
    )


def _repo_read_selector_present(args: dict[str, Any]) -> bool:
    return _any_argument_group_present(
        args if isinstance(args, dict) else {},
        [["path"], ["paths"], ["item"], ["items"]],
    )


def _native_required_tool_decision_has_transport_provenance(decision: dict[str, Any]) -> bool:
    if decision.get("native_tool_call") is not True:
        return False
    return isinstance(decision.get("raw_native_tool_call"), dict)


def _native_required_repaired_tool_decision_disallowed(decision: dict[str, Any]) -> bool:
    action = str((decision if isinstance(decision, dict) else {}).get("action") or "").strip().lower()
    return bool(
        AGENTIC_PLANNER_NATIVE_TOOLS
        and action == "tool"
    )


def _verified_repo_read_contents_for_path(history: list[dict[str, Any]], target_file: str) -> list[str]:
    target = _repo_rel_token(target_file)
    if not target or target == ".":
        return []
    out: list[str] = []
    seen_hashes: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = _history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = _repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = _repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = _text_hash(text)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            out.append(text)
    return out


def _old_text_verified_by_repo_read(history: list[dict[str, Any]], target_file: str, old_text: Any) -> bool:
    if not isinstance(old_text, str) or not old_text:
        return False
    return any(old_text in content for content in _verified_repo_read_contents_for_path(history, target_file))


def _apply_unverified_old_text_replan_contract(
    contract: dict[str, Any],
    *,
    target_file: str,
    violation: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    target = _repo_rel_token(target_file)
    def admissible_replan_candidate(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        tool_name = str(item.get("tool") or "")
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        if tool_name == "planner_scratchpad_read":
            return True
        if tool_name == "repo_read":
            return target in {
                _repo_rel_token(path)
                for path in _agentic_v2_decision_paths(tool_name, arguments)
            }
        if tool_name == "planner_scratchpad_write" and arguments.get("kind") == CODE_PRODUCT_BUILD_STATE_KIND:
            text = str(arguments.get("text") or arguments.get("content") or "")
            state = _code_product_build_state_parse(text)
            return bool(
                state
                and (
                    _code_product_build_state_has_collecting_progress(state)
                    or _code_product_build_state_ready_payload(state)
                    or (
                        str(state.get("status") or "") == "blocked_incomplete"
                        and str(state.get("blocker") or "").strip()
                    )
                )
            )
        if item.get("action") == "block":
            return True
        return False

    existing = [
        item for item in (contract.get("candidate_next_actions") or [])
        if admissible_replan_candidate(item)
    ]
    preferred: list[dict[str, Any]] = []
    for item in existing:
        tool_name = str(item.get("tool") or "")
        if tool_name == "planner_scratchpad_read":
            preferred.append(item)
        elif tool_name == "repo_read" and target in {
            _repo_rel_token(path)
            for path in _agentic_v2_decision_paths(
                tool_name,
                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
            )
        }:
            preferred.append(item)
    route_candidate = _code_product_source_window_candidate(target, history=history)
    if route_candidate:
        preferred.insert(0, route_candidate)
    if not preferred:
        preferred.append(
            {
                "action": "block",
                "reason": "code_product_old_text_not_verifiable",
                "final_answer": (
                    f"{violation}: old_text is not verified in repo_read content for {target}. "
                    "No further source window is available; cannot build a valid diff."
                ),
            }
        )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*preferred, *existing]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    contract["candidate_next_actions"] = merged[:15]
    contract["required_next_progress"] = (
        f"{violation}. Change decision now: use a real planner_scratchpad_read window from "
        "required_working_set/candidate_next_actions if available, otherwise read a useful target "
        "window or return a typed block. Do not repeat placeholder old_text/new_text."
    )
    return contract


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
) -> dict[str, Any]:
    return _validate_planner_decision_against_evidence_impl(
        goal,
        decision,
        history,
        require_native_tool_call=require_native_tool_call,
        deps={
            "agentic_v2_decision_paths": _agentic_v2_decision_paths,
            "agentic_v2_goal_scope": _agentic_v2_goal_scope,
            "agentic_v2_read_has_window": _agentic_v2_read_has_window,
            "agentic_v2_successful_read_paths": _agentic_v2_successful_read_paths,
            "any_argument_group_present": _any_argument_group_present,
            "apply_duplicate_window_replan_contract": _apply_duplicate_window_replan_contract,
            "apply_unverified_old_text_replan_contract": _apply_unverified_old_text_replan_contract,
            "argument_value_present": _argument_value_present,
            "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
            "code_product_build_state_duplicate_write": _code_product_build_state_duplicate_write,
            "code_product_build_state_has_collecting_progress": _code_product_build_state_has_collecting_progress,
            "code_product_build_state_parse": _code_product_build_state_parse,
            "code_product_build_state_ready_payload": _code_product_build_state_ready_payload,
            "code_product_low_signal_target": _code_product_low_signal_target,
            "code_product_payload_violations": _code_product_payload_violations,
            "contract_final_required_now": _contract_final_required_now,
            "copyable_example_text": _copyable_example_text,
            "decision_matches_prompt_context_continuation": _decision_matches_prompt_context_continuation,
            "decision_paths": _decision_paths,
            "final_answer_is_action_plan_without_code_product": _final_answer_is_action_plan_without_code_product,
            "final_composition_tool_names_from_candidates": _final_composition_tool_names_from_candidates,
            "invalid_code_product_decision_signature_count": _invalid_code_product_decision_signature_count,
            "invalid_decision_signature_key": _invalid_decision_signature_key,
            "native_required_tool_decision_has_transport_provenance": _native_required_tool_decision_has_transport_provenance,
            "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
            "normalize_tool_name": _normalize_tool_name,
            "old_text_verified_by_repo_read": _old_text_verified_by_repo_read,
            "path_exists_repo_relative": _path_exists_repo_relative,
            "path_under_scope": _path_under_scope,
            "planner_scratchpad_read_selector_present": _planner_scratchpad_read_selector_present,
            "planner_scratchpad_window_signature": _planner_scratchpad_window_signature,
            "prompt_window_consumed_offsets": _prompt_window_consumed_offsets,
            "prompt_window_tracking_metadata_errors": _prompt_window_tracking_metadata_errors,
            "repo_analysis_goal": _repo_analysis_goal,
            "repo_path_kind": _repo_path_kind,
            "repo_read_selector_present": _repo_read_selector_present,
            "repo_read_window_signature": _repo_read_window_signature,
            "repo_readable_evidence_file": _repo_readable_evidence_file,
            "repo_rel_token": _repo_rel_token,
            "repeated_tool_call_count": repeated_tool_call_count,
            "scope_claim_conflict_for_path": _scope_claim_conflict_for_path,
            "successful_window_signatures": _successful_window_signatures,
            "target_scope_conflict_resolved": _target_scope_conflict_resolved,
            "latest_file_list_result": latest_file_list_result,
            "planner_evidence_contract": planner_evidence_contract,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "validate_unified_diff_text": validate_unified_diff_text,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "CODE_PRODUCT_BUILD_STATE_KIND": CODE_PRODUCT_BUILD_STATE_KIND,
            "VALID_INTERNAL_TOOLS": VALID_INTERNAL_TOOLS,
        },
    )



def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
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
    """Count the current consecutive planner-repeat streak.

    The retry budget is for the active bad-output streak, not for the whole job.
    A successful tool result, cached evidence delivery, validation guard of a
    different kind, or any other progress starts a new agentic segment and must
    not consume retry budget for later planner emissions.
    """
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
    """Classify raw planner output for planner retry vs GPU0 repair.

    ``plain_text_non_json`` and ``mixed_prose_with_embedded_json`` are handled by
    asking the planner to repeat a pure JSON decision. Vulkan/GPU0 repair is
    reserved for JSON-shaped or tool-call shaped emissions that are broken but
    still structurally related to the loop protocol.
    """
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
    """Detect explicit pseudo-tool invocations such as ``SAVE_FILE: ...``.

    This is intentionally narrower than the full alias table. Generic words
    like ``read`` or ``run`` are allowed in prose and must not route ordinary
    text to GPU0. Alias-shaped tool emissions with underscores are controller
    protocol attempts, so they belong on the structured repair path.
    """
    raw = str(text or "")
    if not raw.strip():
        return False
    try:
        from .tool_contract import TOOL_ALIASES  # noqa: PLC0415
    except Exception:
        TOOL_ALIASES = {}
    generic_aliases = {
        "capabilities", "tools", "status", "diff", "search", "grep", "rg",
        "read", "patch", "edit", "validate", "validation", "smoke",
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
        if isinstance(decoded, dict):
            spans.append((match.start(), match.start() + end))
    if len(spans) != 1:
        return False
    start, end = spans[0]
    outside = (raw[:start] + raw[end:]).strip()
    return bool(outside)


def _raw_planner_text_retries_on_gpu1(text: str) -> bool:
    return _raw_planner_text_classification(text) in {
        "plain_text_non_json",
        "mixed_prose_with_embedded_json",
        "markdown_fenced_json_non_json",
        "long_mixed_json_examples",
        "native_notebook_cell_output",
    }


def _raw_planner_text_looks_like_tool_request(text: str) -> bool:
    """Detect malformed-but-recognizable tool/JSON requests for GPU0 repair."""
    return _raw_planner_text_classification(text) in {
        "corrupt_json",
        "tool_like_malformed",
    }


def _should_retry_incomprehensible_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    """Retry only raw non-JSON planner output, without inventing a controller action."""
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    reason = str(decision.get("reason") or "")
    retryable_reason = (
        reason == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE"
        or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        or "timeout" in reason.lower()
        or "non_json" in reason.lower()
        or "no_json" in reason.lower()
        or "non-json" in reason.lower()
    )
    if not retryable_reason:
        return False
    raw_planner_text = _decision_raw_planner_text(decision)
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    if int(retry_limit or 0) <= 0:
        return False
    return _planner_incomprehensible_retry_count(history) < int(retry_limit)


def _is_unrecoverable_plain_text_planner_output(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    retry_limit: int,
) -> bool:
    decision = decision if isinstance(decision, dict) else {}
    if str(decision.get("action") or "").strip().lower() != "block":
        return False
    raw_planner_text = _decision_raw_planner_text(decision)
    if not raw_planner_text.strip():
        return False
    if not _raw_planner_text_retries_on_gpu1(raw_planner_text):
        return False
    reason = str(decision.get("reason") or "").lower()
    relevant_reason = (
        "invalid_planner_output_non_json" in reason
        or "non-json" in reason
        or "non_json" in reason
        or "no_json" in reason
        or "degenerate" in reason
        or "timeout" in reason
    )
    if not relevant_reason:
        return False
    if int(retry_limit or 0) > 0:
        return _planner_incomprehensible_retry_count(history) >= int(retry_limit)
    return True


def _compact_repair_history(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        rows.append({
            "step": item.get("step"),
            "decision": {
                k: decision.get(k)
                for k in ("action", "tool", "arguments", "reason", "final_answer")
                if decision.get(k) not in (None, "", [], {})
            },
            "tool_result": {
                k: result.get(k)
                for k in ("tool", "ok", "summary", "path", "count", "total_matches", "truncated", "violations")
                if result.get(k) not in (None, "", [], {})
            },
        })
    return rows


def _compact_vulkan_repair_evidence_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    compact: dict[str, Any] = {"schema": "vulkan_repair_evidence_contract.v1"}
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
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    for key in (
        "known_paths_from_latest_repo_list_files",
        "successful_repo_read_paths",
        "read_admissible_paths",
        "validator_admissible_repo_read_paths",
        "failed_repo_read_paths",
        "failed_repo_list_files_paths",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=140, list_limit=16)
    for key in (
        "code_product_contract",
        "finalization_contract",
        "core_discovery_status",
    ):
        value = contract.get(key)
        if value not in (None, "", [], {}):
            compact[key] = _prompt_clip_value(value, text_limit=260, list_limit=4)
    candidates = contract.get("candidate_next_actions")
    if isinstance(candidates, list) and candidates:
        compact["candidate_next_actions"] = _prompt_clip_value(
            candidates,
            text_limit=260,
            list_limit=4,
        )
    rejections = contract.get("validation_rejections_tail")
    if isinstance(rejections, list) and rejections:
        compact["validation_rejections_tail"] = _prompt_clip_value(
            rejections,
            text_limit=260,
            list_limit=4,
        )
    return _prompt_clip_value(compact, text_limit=500, list_limit=16)


def _should_attempt_vulkan_repair(
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
) -> bool:
    """Allow explicit IA repair, but no controller fallback/normalization.

    Vulkan/GPU0 11435 may be asked once to convert the planner's own malformed
    emission or invalid tool proposal into a valid loop JSON decision. The
    original planner text remains visible in events/history/wrapper; the
    controller does not invent a substitute action.
    """
    if _vulkan_repair_seen(history) >= 1:
        return False
    decision = decision if isinstance(decision, dict) else {}
    action = str(decision.get("action") or "").strip().lower()
    reason = str(decision.get("reason") or "")
    contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
    semantic = contract.get("semantic_goal_classification") if isinstance(contract.get("semantic_goal_classification"), dict) else {}
    if (
        contract.get("goal_requests_code_product")
        or contract.get("goal_requires_code_product_report")
        or bool(semantic.get("must_produce_code_product"))
    ):
        return False
    if action == "block":
        raw_planner_text = _decision_raw_planner_text(decision)
        reason_low = reason.lower()
        if raw_planner_text and _raw_planner_text_looks_like_tool_request(raw_planner_text) and (
            "invalid_planner_output_non_json" in reason_low
            or "non-json" in reason_low
            or "no_json" in reason_low
            or "degenerate" in reason_low
            or "timeout" in reason_low
            or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        ):
            return True
        return False
    if action == "tool":
        tool = _normalize_tool_name(str(decision.get("tool") or ""))
        violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
        if tool == "repo_propose_code_edit":
            return False
        if any(
            str(violation).startswith((
                "repo_propose_code_edit_",
                "code_product_",
                "missing_code_product_candidate",
                "invalid_code_product_candidate",
                "prompt_context_continuation_required",
                "prompt_context_window_",
                "planner_scratchpad_window_",
                "planner_scratchpad_read_missing_selector",
                "repo_read_window_",
                "non_existing_path:",
                "repo_read_already_successful:",
                "repo_read_path_not_from_prior_file_evidence:",
                "repo_read_path_outside_requested_scope:",
                "repo_list_files_on_file_path_use_repo_read:",
                "repo_list_files_scope_mismatch:",
                "repo_list_files_limit_mismatch:",
                "repo_list_files_suffix_not_python:",
                "repeated_repo_list_files_after_useful_file_list",
                "tool_not_in_turn_surface",
                "native_tool_not_in_turn_surface",
                "final_required_tool_call_disallowed",
            ))
            for violation in violations
        ):
            return False
        if "repeated_same_tool_arguments_without_progress" in violations:
            return False
        return True
    return False


def vulkan_repair_invalid_planner_decision(
    *,
    goal: str,
    step: int,
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Ask Vulkan/GPU0 11435 for one explicit repair of the planner emission.

    This is not a hidden controller fallback. 11435 receives the original
    planner emission/proposal and must return one pure JSON decision. The raw
    planner output is preserved and surfaced even when repair succeeds.
    """
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = _repair_cache_key(raw_planner_text)
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
                    "oggetto JSON puro con action=tool|final|block. "
                    "Se la emissione contiene una risposta naturale utile, mettila dentro "
                    "final_answer. Se contiene una tool call utile, correggi solo il JSON. "
                    "Se non puoi riparare senza inventare, ritorna action=block con final_answer."
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
                    "evidence_contract": _compact_vulkan_repair_evidence_contract(
                        validation.get("evidence_contract")
                    ),
                    "evidence_contract_bounded_for_repair": True,
                    "history_tail": _compact_repair_history(history),
                    "available_tools": internal_tool_prompt(exclude_vulkan=False),
                    "rules": [
                        "Return pure JSON only; no markdown fences, no prose outside JSON.",
                        "Do not invent paths or claim files were read if evidence does not show it.",
                        "A natural-language answer is allowed only inside final_answer.",
                        "A tool call is allowed only if action=tool, tool is valid, and arguments are explicit.",
                        "Expose uncertainty in final_answer rather than hiding it.",
                    ],
                }, ensure_ascii=False, default=str),
            },
        ],
        "options": ollama_options(num_predict=1600),
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
    repaired = _parse_strict_json_object(raw_text)
    if not isinstance(repaired, dict) or not repaired:
        return {
            "ok": False,
            "error": "vulkan_repair_no_pure_json_decision",
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


def controller_guard_result_for_validation(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
    guard = {
        "tool": "controller_guard",
        "ok": True,
        "guard_type": "planner_decision_validation",
        "summary": (
            "planner_decision_validation_failed: " + "; ".join(str(v) for v in violations)
            if violations else "planner_decision_validation_failed"
        ),
        "violations": violations,
        "evidence_contract": contract,
        "rejected_decision": {
            k: (
                _prompt_clip_text(decision.get(k), 12000)
                if k == "final_answer" else decision.get(k)
            )
            for k in (
                "action", "tool", "arguments", "reason", "selected_by_3572",
                "coerced_by_3572", "planner_stream_meta", "final_answer",
            )
            if decision.get(k) not in (None, "", [], {})
        },
        "ollama_turn": _planner_ollama_turn_from_decision(decision),
    }
    if validation.get("semantic_goal_classification") not in (None, "", [], {}):
        guard["semantic_goal_classification"] = validation.get("semantic_goal_classification")
    if validation.get("invalid_decision_signature") not in (None, "", [], {}):
        guard["invalid_decision_signature"] = validation.get("invalid_decision_signature")
    if validation.get("invalid_decision_repeat_count") not in (None, "", [], {}):
        guard["invalid_decision_repeat_count"] = validation.get("invalid_decision_repeat_count")
    required_next_progress = str(contract.get("required_next_progress") or "").strip()
    if required_next_progress:
        guard["next_instruction"] = required_next_progress
    candidate_next_actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    if candidate_next_actions:
        guard["candidate_next_actions"] = candidate_next_actions[:6]
    if validation.get("action_plan_candidate") not in (None, "", [], {}):
        guard["action_plan_candidate"] = _prompt_clip_text(
            validation.get("action_plan_candidate"),
            12000,
        )
        if not guard.get("next_instruction"):
            guard["next_instruction"] = (
                "Treat action_plan_candidate as an intermediate plan only. "
                "Do not final with it. Use it to choose repo_read evidence and then "
                "repo_propose_code_edit with a complete inline diff/ops payload."
            )
    return guard


# ---------------------------------------------------------------------------
# Planner decision (single step)
# ---------------------------------------------------------------------------

def _planner_system_for_current_mode() -> str:
    return _planner_system_for_current_mode_impl(
        native_tools=AGENTIC_PLANNER_NATIVE_TOOLS,
    )


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return _planner_decision_impl(
        job_id,
        state,
        step,
        history,
        deps={
            "build_planner_user_payload": _build_planner_user_payload,
            "controller_memory_target_key": _controller_memory_target_key,
            "filter_tool_manifest_for_names": _filter_tool_manifest_for_names,
            "history_tool_result": _history_tool_result,
            "input_error_goal": _input_error_goal,
            "native_tool_calls_decision": _native_tool_calls_decision,
            "native_tools_schema_for_planner": _native_tools_schema_for_planner,
            "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
            "parse_strict_json_object": _parse_strict_json_object,
            "planner_history_messages_for_ollama": _planner_history_messages_for_ollama,
            "planner_system_for_current_mode": _planner_system_for_current_mode,
            "planner_token_generation_reserve": _planner_token_generation_reserve,
            "prompt_context_continuation_from_payload": _prompt_context_continuation_from_payload,
            "prompt_generation_headroom_char_budget": _prompt_generation_headroom_char_budget,
            "prompt_window_chars": _prompt_window_chars,
            "tool_surface_names_for_turn": _tool_surface_names_for_turn,
            "agent_job_planner_stream_path": agent_job_planner_stream_path,
            "agent_job_root": agent_job_root,
            "append_agent_event": append_agent_event,
            "build_planner_intrinsic_context": build_planner_intrinsic_context,
            "goal_has_write_intent": goal_has_write_intent,
            "goal_requires_code_product_report": goal_requires_code_product_report,
            "history_has_tool": history_has_tool,
            "internal_tools_list": internal_tools_list,
            "normalize_planner_decision": normalize_planner_decision,
            "planner_done_token": planner_done_token,
            "planner_evidence_contract": planner_evidence_contract,
            "planner_memory_surface": planner_memory_surface,
            "post_json_stream_to_file": post_json_stream_to_file,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "summarize_history_artifacts": summarize_history_artifacts,
            "write_json": write_json,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "AGENTIC_PLANNER_NUM_CTX": AGENTIC_PLANNER_NUM_CTX,
            "AGENTIC_PLANNER_NUM_CTX_CAP": AGENTIC_PLANNER_NUM_CTX_CAP,
            "AGENTIC_PLANNER_NUM_CTX_REQUESTED": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "AGENTIC_PLANNER_NUM_PREDICT": AGENTIC_PLANNER_NUM_PREDICT,
            "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
            "AGENTIC_PLANNER_STEP_TIMEOUT": AGENTIC_PLANNER_STEP_TIMEOUT,
            "AGENTIC_PLANNER_TEMPERATURE": AGENTIC_PLANNER_TEMPERATURE,
            "OLLAMA_KEEP_ALIVE": OLLAMA_KEEP_ALIVE,
            "PLANNER_INTRINSIC_CONTEXT_MAX_CHARS": PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
            "PLANNER_INTRINSIC_RAG_CHAR_BUDGET": PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
            "PLANNER_INTRINSIC_RAG_TOP_K": PLANNER_INTRINSIC_RAG_TOP_K,
            "PLANNER_MODEL": PLANNER_MODEL,
            "PLANNER_RAG_DB": PLANNER_RAG_DB,
            "PLANNER_RAG_EMBEDDING_BATCH_SIZE": PLANNER_RAG_EMBEDDING_BATCH_SIZE,
            "PLANNER_RAG_EXTERNAL_RERANKER_URL": PLANNER_RAG_EXTERNAL_RERANKER_URL,
            "PLANNER_RAG_RERANKING_ENGINE": PLANNER_RAG_RERANKING_ENGINE,
            "PLANNER_RAG_RERANKING_MODEL": PLANNER_RAG_RERANKING_MODEL,
            "PLANNER_RAG_RERANK_TIMEOUT_SECONDS": PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
            "PLANNER_URL": PLANNER_URL,
        },
    )


# ---------------------------------------------------------------------------
# Full agentic loop
# ---------------------------------------------------------------------------


def _compact_final_state_result(result: dict[str, Any] | None) -> dict[str, Any]:
    return _compact_final_state_result_impl(
        result,
        history_ledger_builder=planner_history_ledger,
    )


_PUBLIC_TERMINAL_POINTER_KEYS = _PUBLIC_TERMINAL_POINTER_KEYS_IMPL


def _public_terminal_content_key(key: Any) -> bool:
    return _public_terminal_content_key_impl(key)


def _public_terminal_sanitize_text(value: Any, *, content: bool = False) -> str:
    return _public_terminal_sanitize_text_impl(value, content=content)


def _public_terminal_sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    return _public_terminal_sanitize_value_impl(value, key=key, depth=depth)


def _public_terminal_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _public_terminal_history_ledger_impl(
        history,
        repo_read_item_full_content=_repo_read_item_full_content,
    )


def _public_terminal_result_for_30b(result: dict[str, Any] | None) -> dict[str, Any]:
    return _public_terminal_result_for_30b_impl(
        result,
        repo_read_item_full_content=_repo_read_item_full_content,
    )


def _terminal_context_alias() -> dict[str, Any]:
    return _terminal_context_alias_impl()



def _planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _planner_decision_rows_impl(history)


def _validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _validation_rejection_rows_impl(history)


def _executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _executed_tool_rows_impl(history)


def _repo_read_content_views(
    history: list[dict[str, Any]],
    *,
    per_item_limit: int = 60000,
    total_limit: int = 180000,
) -> list[dict[str, Any]]:
    return _repo_read_content_views_impl(
        history,
        repo_read_item_full_content=_repo_read_item_full_content,
        per_item_limit=per_item_limit,
        total_limit=total_limit,
    )


def _execution_evidence_digest_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    return _execution_evidence_digest_text_impl(
        result,
        repo_read_item_full_content=_repo_read_item_full_content,
        extract_key_lines=_extract_key_lines,
        limit=limit,
    )


def _latest_code_product_payload(history: list[dict[str, Any]]) -> dict[str, Any]:
    return _latest_code_product_payload_impl(history)


def _code_product_answer_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    return _code_product_answer_text_impl(result, limit=limit)


def _partial_product_clean_text(value: Any, limit: int = 40000) -> str:
    return _partial_product_clean_text_impl(value, limit)


def _partial_products_for_30b(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return _partial_products_for_30b_impl(
        history,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        limit=limit,
    )


def _best_partial_product_for_30b(history: list[dict[str, Any]]) -> dict[str, Any]:
    return _best_partial_product_for_30b_impl(
        history,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _partial_product_answer_text(result: dict[str, Any] | None, limit: int = 60000) -> str:
    return _partial_product_answer_text_impl(
        result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        limit=limit,
    )


def _agent_flow_diagnostics(
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _agent_flow_diagnostics_impl(
        goal,
        history,
        planner_memory,
        native_tools_enabled=AGENTIC_PLANNER_NATIVE_TOOLS,
        evidence_contract_builder=planner_evidence_contract,
        planner_incomprehensible_retry_count=_planner_incomprehensible_retry_count,
    )



def answer_for_openwebui(status: str, final_summary: str, result: dict[str, Any] | None) -> str:
    return _answer_for_openwebui_impl(
        status,
        final_summary,
        result,
        code_product_answer_text=_code_product_answer_text,
        execution_evidence_digest_text=_execution_evidence_digest_text,
        partial_product_answer_text=_partial_product_answer_text,
    )


def next_action_for_openwebui(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    return _next_action_for_openwebui_impl(status, result)


def build_tool_context_for_30b(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    return _build_tool_context_for_30b_impl(
        job_id,
        state,
        status,
        final_summary,
        result,
        planner_model=PLANNER_MODEL,
        planner_url=PLANNER_URL,
        job_root_for_id=agent_job_root,
        planner_composed_answer=planner_composed_answer,
        agent_flow_diagnostics=_agent_flow_diagnostics,
        partial_products_for_30b=_partial_products_for_30b,
        best_partial_product_for_30b=_best_partial_product_for_30b,
        answer_for_openwebui=answer_for_openwebui,
        execution_evidence_digest_text=_execution_evidence_digest_text,
        repo_read_content_views=_repo_read_content_views,
        next_action_for_openwebui=next_action_for_openwebui,
        initial_orientation_surface_from_history=_initial_orientation_surface_from_history,
        planner_decision_rows=_planner_decision_rows,
        validation_rejection_rows=_validation_rejection_rows,
        executed_tool_rows=_executed_tool_rows,
        planner_turn_memory=_planner_turn_memory,
        compact_final_state_result=_compact_final_state_result,
        public_tool_artifact_rows=_public_tool_artifact_rows,
        public_tool_context_limits=_public_tool_context_limits,
        planner_evidence_contract=planner_evidence_contract,
        planner_history_ledger=planner_history_ledger,
        strip_public_local_references=_strip_public_local_references,
    )


def _controller_memory_lesson_text(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    return _controller_memory_lesson_text_impl(
        job_id,
        state,
        status,
        final_summary,
        result,
        contract,
        target_key,
    )


def _write_controller_memory_lesson(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    return _write_controller_memory_lesson_impl(
        job_id,
        state,
        status,
        final_summary,
        result,
        root,
        planner_evidence_contract=planner_evidence_contract,
        controller_memory_target_key=_controller_memory_target_key,
        runtime_sqlite_memory_write=runtime_sqlite_memory_write,
    )


def _loop_turn_memory_text(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    return _loop_turn_memory_text_impl(
        job_id,
        state,
        row,
        contract,
        target_key,
        prompt_clip_value=_prompt_clip_value,
    )


def _write_loop_turn_memory(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    root: Path,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return _write_loop_turn_memory_impl(
        job_id,
        state,
        row,
        root,
        history,
        planner_evidence_contract=planner_evidence_contract,
        controller_memory_target_key=_controller_memory_target_key,
        runtime_sqlite_memory_write=runtime_sqlite_memory_write,
        prompt_clip_value=_prompt_clip_value,
    )


def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = agent_job_root(job_id)
    result = dict(result or {})
    final_summary_with_turns = _final_summary_with_ollama_done_reasons(status, final_summary, result)
    controller_memory = _write_controller_memory_lesson(
        job_id, state, status, final_summary_with_turns, result, root
    )
    result["controller_memory_write"] = controller_memory
    state["controller_memory_last_write"] = controller_memory
    tool_context = build_tool_context_for_30b(job_id, state, status, final_summary_with_turns, result)
    if tool_context.get("partial_products_for_30b") not in (None, "", [], {}):
        result["partial_products_for_30b"] = tool_context.get("partial_products_for_30b")
    if tool_context.get("best_partial_product_for_30b") not in (None, "", [], {}):
        result["best_partial_product_for_30b"] = tool_context.get("best_partial_product_for_30b")
    public_result = _public_terminal_result_for_30b(result)
    answer = tool_context.get("answer_for_30b") or final_summary_with_turns
    public_final_summary = (
        answer
        if status == "completed" and _latest_code_product_payload(result.get("history") if isinstance(result.get("history"), list) else [])
        else final_summary_with_turns
    )
    next_action = tool_context.get("next_action_for_30b") or {}
    final = {
        "ok": status == "completed",
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "answer_for_30b": answer,
        "message_for_30b": answer,
        "next_action_for_30b": next_action,
        "result": public_result,
        "agent_flow_diagnostics": tool_context.get("agent_flow_diagnostics"),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": _terminal_context_alias(),
        "structured_context_for_30b": _terminal_context_alias(),
        "structured_result_for_30b": _terminal_context_alias(),
        "events_path": str(root / "events.ndjson"),
    }
    write_json(root / "final.json", final)
    (root / "final.md").write_text(answer, encoding="utf-8")
    state = load_agent_job_state(job_id) or state
    state.update({
        "status": status,
        "final_path": str(root / "final.json"),
        "final_markdown_path": str(root / "final.md"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "answer_for_30b": answer,
        "message_for_30b": answer,
        "next_action_for_30b": next_action,
        "result": _compact_final_state_result(public_result),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": _terminal_context_alias(),
        "structured_context_for_30b": _terminal_context_alias(),
        "structured_result_for_30b": _terminal_context_alias(),
    })
    write_agent_job_state(state)
    append_agent_event(
        job_id, "job_finished", f"Job finished status={status}.", {"status": status},
        step=state.get("current_step"),
    )
    return final


def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    return _run_agentic_planner_job_impl(
        job_id,
        deps={
            "agent_flow_diagnostics": _agent_flow_diagnostics,
            "agentic_tool_allowed": _agentic_tool_allowed,
            "cached_tool_result": _cached_tool_result,
            "cached_vulkan_repair_result": _cached_vulkan_repair_result,
            "controller_file_code_product_orientation_preseed_plan": _controller_file_code_product_orientation_preseed_plan,
            "controller_guard_rejection_signature": _controller_guard_rejection_signature,
            "controller_guard_rejection_signature_count": _controller_guard_rejection_signature_count,
            "controller_initial_area_list_plans": _controller_initial_area_list_plans,
            "controller_initial_area_read_plan": _controller_initial_area_read_plan,
            "controller_initial_doc_preseed_plan": _controller_initial_doc_preseed_plan,
            "controller_memory_target_key": _controller_memory_target_key,
            "controller_preseed_plan": _controller_preseed_plan,
            "decision_memory_claim_text": _decision_memory_claim_text,
            "decision_raw_planner_text": _decision_raw_planner_text,
            "initial_orientation_surface_from_history": _initial_orientation_surface_from_history,
            "is_unrecoverable_plain_text_planner_output": _is_unrecoverable_plain_text_planner_output,
            "native_required_repaired_tool_decision_disallowed": _native_required_repaired_tool_decision_disallowed,
            "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
            "planner_incomprehensible_retry_count": _planner_incomprehensible_retry_count,
            "planner_memory_false_unavailable_claim": _planner_memory_false_unavailable_claim,
            "raw_planner_text_classification": _raw_planner_text_classification,
            "should_attempt_vulkan_repair": _should_attempt_vulkan_repair,
            "should_retry_incomprehensible_planner_output": _should_retry_incomprehensible_planner_output,
            "tool_cache_hit": _tool_cache_hit,
            "tool_cache_key": _tool_cache_key,
            "write_loop_turn_memory": _write_loop_turn_memory,
            "agent_job_root": agent_job_root,
            "append_agent_event": append_agent_event,
            "compact_tool_result_for_planner": compact_tool_result_for_planner,
            "controller_guard_count": controller_guard_count,
            "controller_guard_result_for_validation": controller_guard_result_for_validation,
            "finalize_agentic_job": finalize_agentic_job,
            "goal_has_write_intent": goal_has_write_intent,
            "history_has_tool": history_has_tool,
            "load_agent_job_state": load_agent_job_state,
            "planner_decision": planner_decision,
            "planner_evidence_contract": planner_evidence_contract,
            "planner_history_ledger": planner_history_ledger,
            "planner_memory_surface": planner_memory_surface,
            "repeated_tool_call_count": repeated_tool_call_count,
            "validate_planner_decision_against_evidence": validate_planner_decision_against_evidence,
            "vulkan_repair_invalid_planner_decision": vulkan_repair_invalid_planner_decision,
            "write_agent_job_state": write_agent_job_state,
            "write_json": write_json,
        },
        config={
            "AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES": AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
            "AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
            "AGENT_DEFAULT_MAX_STEPS": AGENT_DEFAULT_MAX_STEPS,
            "AGENT_MAX_STEPS": AGENT_MAX_STEPS,
            "OLLAMA_TASK_MODEL": OLLAMA_TASK_MODEL,
            "OLLAMA_TASK_URL": OLLAMA_TASK_URL,
            "PLANNER_MODEL": PLANNER_MODEL,
            "PLANNER_URL": PLANNER_URL,
            "VALID_INTERNAL_TOOLS": VALID_INTERNAL_TOOLS,
        },
    )


def _agentic_tool_allowed(
    tool: str, args: dict[str, Any], approval_mode: str
) -> tuple[bool, str]:
    mode = str(approval_mode or "safe_write_lab").lower()
    readonly_modes = {"read_only", "readonly", "no_write", "dry_run"}
    if tool in {"repo_apply_patch", "repo_write_file"} and mode in {
        "read_only", "readonly", "no_write", "dry_run"
    }:
        return False, f"{tool} blocked by read_only approval_mode"
    if (
        tool == "runtime_sqlite_memory_cleanup"
        and bool(args.get("apply"))
        and mode in readonly_modes
    ):
        return False, "runtime_sqlite_memory_cleanup apply blocked by read_only approval_mode"
    if tool == "repo_command":
        from .repo_tools import dangerous_command  # noqa: PLC0415
        if mode in readonly_modes and dangerous_command(
            str(args.get("command") or "")
        ):
            return False, "dangerous repo_command blocked by read_only approval_mode"
    return True, ""
