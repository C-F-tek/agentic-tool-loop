
"""Planner facade module for consolidated imports.

This module replaces the 40+ aliased imports in planner.py with a single
facade import pattern. All wrapper functions delegate to the original
implementation modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

# Re-export all planner dependencies through facade
from .application.planner.loop import run_agentic_planner_job as run_agentic_planner_job
from .application.planner.turn import planner_decision as planner_decision
from .application.planner.validator import validate_planner_decision_against_evidence as validate_planner_decision_against_evidence
from .application.planner.decision_normalizer import (
    normalize_planner_decision,
    _native_tool_calls_decision,
    _normalize_terminal_planner_decision,
)
from .application.planner.status import planner_done_token, summarize_history_artifacts
from .application.planner.system_prompt import planner_system_for_current_mode
from .application.planner.required_progress import required_next_progress_from_text
from .application.planner.required_call_validator import required_next_route_has_deterministic_proof
from .application.planner.rewrite_latch import clear_final_terminal_block_state
from .application.planner.lane_catalog import validate_control_lane_catalog
from .application.planner.final_quality_route import final_quality_repo_read_allowlist
# Note: run_validator_pipeline, run_validator_code_product, run_validator_duplicate_recovery,
# run_validator_path_validation are not exported from their modules; they are called
# directly from planner.py via the _validate_* wrapper functions defined inline.
from .application.planner.validation_rejections import (
    canonical_invalid_code_product_decision_signature,
    compact_validation_rejections_tail,
    disallowed_invalid_code_product_signatures,
    invalid_code_product_decision_signature_count,
    invalid_code_product_decision_signature_from_history_item,
    invalid_decision_signature_key,
)
from .application.planner.path_utils import (
    search_query_is_concrete,
    collect_repo_paths,
)
from .application.evidence.builder import EvidenceBuilder, planner_evidence_contract
from .application.evidence.coverage_scorer import score_evidence_coverage
from .application.evidence.audit_guidance import (
    goal_requests_semantic_audit,
    role_guidance_for_goal,
    role_guidance_text,
)
from .application.evidence.goal_classifier import (
    effective_repo_analysis_goal,
    final_answer_is_action_plan_without_code_product,
    goal_requires_code_security_coverage,
    goal_operational_intent_text,
    goal_requests_apply,
    goal_requests_code_product,
    has_any,
    input_error_goal,
    semantic_goal_classification,
    semantic_goal_low,
)
from .application.evidence.goal_scope import (
    extract_existing_goal_paths,
    extract_existing_goal_path,
    goal_requested_repo_scope,
    requested_file_limit_from_goal,
)
from .application.evidence.initial_orientation import initial_orientation_surface_from_history
from .application.evidence.required_working_set import (
    repo_read_items_for_prompt,
    required_working_set_for_prompt,
)
from .application.evidence.execution_digest import (
    execution_evidence_digest_text,
    repo_read_content_views,
)
from .application.evidence.final_quality import (
    repo_analysis_final_answer_model_quality_request,
    repo_analysis_final_answer_quality,
    sanitize_repo_analysis_final_model_quality,
)
from .application.evidence.repo_path_policy import (
    dynamic_read_candidate_paths,
    low_signal_top_dir,
    meaningful_read_candidates_from_evidence,
    path_under_scope,
    read_candidate_sort_key,
    repo_code_file,
    repo_doc_or_config,
    repo_existing_dir,
    repo_existing_file,
    repo_path_kind,
    repo_readable_evidence_file,
    scope_candidate_source_paths,
    scope_read_candidates_from_evidence,
    top_dir,
)
from .application.evidence.repo_history import (
    append_unique,
    extract_headings,
    extract_key_lines,
    extract_mentioned_paths,
    failed_repo_read_paths,
    failed_repo_list_files_paths,
    file_memory_from_history,
    rank_core_candidates,
    read_items_from_history,
    repo_list_evidence,
    successful_repo_read_paths,
)
from .application.evidence.scope_conflict_resolution import (
    target_scope_conflict_resolved,
)
from .application.evidence.core_discovery import (
    add_core_discovery_candidate,
    core_discovery_candidates_from_intrinsic,
    core_discovery_read_paths,
)
from .application.evidence.user_scope_claims import (
    claim_area_from_user_token,
    normalize_scope_claim_text,
    scope_claim_conflict_for_path,
    user_scope_claims,
)
from .application.code_product.state import (
    CODE_PRODUCT_BUILD_STATE_KIND,
    code_product_action_has_complete_payload,
    code_product_build_state_has_collecting_progress,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_payload_violations,
    copyable_example_text,
    goal_exact_text_block,
)
from .application.code_product.public_outputs import (
    best_partial_product_for_30b,
    code_product_answer_text,
    latest_code_product_payload,
    partial_product_answer_text,
    partial_product_clean_text,
    partial_products_for_30b,
)
from .application.code_product.history import (
    CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS,
    apply_duplicate_window_replan_contract,
    code_product_build_state_duplicate_write,
    code_product_build_state_from_result,
    code_product_build_state_propose_action,
    code_product_build_state_read_action,
    code_product_build_state_write_action,
    code_product_candidate_action,
    code_product_low_signal_target,
    code_product_payload_rejection_count,
    code_product_source_window_candidate,
    code_product_source_windows_from_reads,
    failed_code_edit_proposal_validation_row,
    latest_code_product_build_state,
    strip_duplicate_window_candidate,
    successful_code_edit_proposals,
    successful_repo_read_window_ranges,
    successful_window_signatures,
)
from .application.code_product.required_working_set import latest_code_product_for_prompt
from .application.code_product.history import successful_code_edit_proposals
from .application.controller.diagnostics import agent_flow_diagnostics
from .application.controller.guards import (
    controller_guard_count,
    controller_guard_rejection_signature,
    controller_guard_rejection_signature_count,
    recoverable_planner_block,
)
from .application.controller.memory import (
    controller_memory_lesson_text,
    loop_turn_memory_text,
    write_controller_memory_lesson,
    write_loop_turn_memory,
)
from .application.controller.preseed import (
    controller_initial_area_list_plans,
    controller_initial_area_read_plan,
    controller_initial_doc_preseed_plan,
    controller_initial_orientation_candidate_pool,
    initial_area_file_sort_key,
    initial_area_sort_key,
    initial_doc_sort_key,
    list_result_file_paths,
    root_surface_dir_paths,
    root_surface_entries,
    root_surface_file_paths,
)
from .application.controller.orientation_lane import (
    controller_orientation_model_select,
    orientation_shadow_effective_mode,
    orientation_legacy_selected_candidate_ids,
    orientation_shadow_selection_metrics,
)
from .application.controller.rag_preseed import (
    controller_preplanner_rag_query_plan,
    controller_preplanner_rag_preseed_plan,
)
from .application.prompt.pack_builder import build_planner_user_payload
from .application.prompt.evidence_contract import (
    compact_evidence_contract_for_prompt,
    hard_budget_evidence_contract_summary,
)
from .application.prompt.context_windows import (
    evidence_contract_continuation_action,
    forbidden_repeated_prompt_window_calls,
    planner_scratchpad_next_window_action_from_history,
    prompt_context_continuation_from_payload,
    prompt_context_continue_action,
    prompt_window_consumed_offsets,
    prompt_window_tracking_metadata_errors,
    required_working_set_continuation_action,
)
from .application.prompt.history_messages import (
    LOCAL_ARTIFACT_KEYS,
    OLLAMA_STREAM_META_KEYS,
    PLANNER_HISTORY_NOISE_KEYS,
    clean_planner_history_value,
    planner_controller_guard_history_payload,
    planner_history_arguments,
    planner_history_evidence_payload,
    planner_history_item_messages,
    planner_history_messages_for_ollama,
    planner_history_reason,
    planner_history_summary,
    planner_tool_result_message_payload,
)
from .application.prompt.history_contract import compact_history_for_prompt
from .application.prompt.intrinsic_context import compact_intrinsic_context_for_prompt
from .application.prompt.available_tools import available_tools_window_pack
from .application.prompt.tool_contract import (
    available_tools_for_user_payload,
    hard_budget_tool_shape_examples_for_prompt,
    tool_shape_examples_for_prompt,
)
from .application.prompt.budget import (
    PROMPT_CHARS_PER_TOKEN,
    report_exceeds_generation_headroom,
)
from .application.prompt.values import (
    prompt_clip_text,
    prompt_clip_value,
    text_hash,
)
from .application.prompt.window_signatures import (
    decision_paths,
    planner_scratchpad_window_signature,
    repo_read_window_signature,
)
from .application.prompt.text_windows import window_text
from .application.shared.history_ledger import (
    history_item_ollama_turn,
    planner_history_ledger,
    planner_ollama_turn_from_decision,
)
from .application.shared.history_queries import (
    history_tool_result,
    history_has_tool,
)
from .application.shared.clean_values import drop_empty_dict_values
from .application.shared.evidence_contract_summary import evidence_contract_summary_triplet
from .application.shared.path_tokens import repo_rel_token
from .application.public_payload.final_state_result import compact_final_state_result
from .application.public_payload.openwebui_terminal_answer import (
    answer_for_openwebui,
    next_action_for_openwebui,
)
from .application.public_payload.evidence_materializer import materialize_public_evidence
from .application.public_payload.openwebui_tool_context import build_tool_context_for_30b
from .application.public_payload.tool_context import (
    PUBLIC_LOCAL_REFERENCE_KEYS,
    decision_for_turn_memory,
    final_summary_with_ollama_done_reasons,
    ollama_turn_rows,
    ollama_turn_summary_text,
    planner_turn_memory,
    public_tool_artifact_rows,
    public_tool_context_limits,
    public_tool_response,
    strip_public_artifact_paths,
    strip_public_local_references,
    successful_tool_turns,
)
from .application.public_payload.terminal_sanitizer import (
    PUBLIC_TERMINAL_POINTER_KEYS,
    public_terminal_content_key,
    public_terminal_sanitize_text,
    public_terminal_sanitize_value,
)
from .application.public_payload.terminal_result import (
    public_terminal_history_ledger,
    public_terminal_result_for_30b,
)
from .application.public_payload.terminal_context_rows import (
    executed_tool_rows,
    planner_decision_rows,
    terminal_context_alias,
    validation_rejection_rows,
)
from .application.tool_surface.candidate_actions import (
    candidate_actions_from_evidence,
    decision_matches_prompt_context_continuation,
    enforce_required_scratchpad_read_continuation_contract,
    final_composition_tool_names_from_candidates,
    preserve_required_next_tool_call_for_prompt,
    required_next_tool_call_from_action,
)
from .application.tool_surface.manifest_builder import (
    compact_tool_manifest_for_prompt,
    filter_tool_manifest_for_names,
    json_char_len,
    native_tools_schema_for_planner,
)
from .application.tool_surface.result_digest import planner_last_result_digest
from .application.tool_surface.result_compaction import compact_tool_result_for_planner
from .application.tool_surface.turn_surface_policy import (
    apply_turn_surface_policy,
    contract_final_required_now,
    tool_surface_names_for_turn,
)
from .application.tool_surface.required_tool_call import (
    required_next_tool_call_satisfaction,
    append_stale_required_call_marker,
)
from .application.tool_surface.batch_contract import canonical_batch_call_key
from .application.tool_surface.candidate_action_gate import gate_candidate_actions
from .application.tool_surface.action_proof_ledger import attach_action_proof
from .application.runtime_debug import build_runtime_debug_packet
from .application.npu_phi import maybe_enqueue_npu_phi_diagnostic
from .planner_core.cache import (
    CACHEABLE_READ_TOOLS,
    _cached_tool_result,
    _tool_cache_hit,
    _tool_cache_key,
    _cached_vulkan_repair_result,
    _repair_cache_key,
    repeated_tool_call_count,
)
from .planner_core.json_io import (
    _parse_strict_json_object,
    parse_strict_json_object_diagnostics,
    post_json,
    post_json_stream_to_file,
)
from .code_edit_proposal_contract import validate_unified_diff_text
from .memory_tools import (
    planner_composed_answer,
    planner_memory_surface,
    planner_prompt_context_store_window,
    runtime_sqlite_memory_write,
)
from .job_store import (
    agent_job_planner_stream_path,
    agent_job_root,
    append_agent_event,
    load_agent_job_state,
    write_agent_job_state,
    write_json,
)
from .config import (
    WRITE_GUARDED_TOOLS,
    AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
    AGENTIC_PLANNER_NATIVE_TOOLS,
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
    AGENTIC_PLANNER_PRESENCE_PENALTY,
    AGENTIC_PLANNER_TEMPERATURE,
    AGENTIC_PLANNER_TOP_K,
    AGENTIC_PLANNER_TOP_P,
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
    AICARMINE_ORIENTATION_LANE_MODE,
)
from .repo_tools import safe_rel_path
from .infrastructure.filesystem_repo import FilesystemRepo
from .infrastructure.json_files import same_tool_artifact_payload
from .infrastructure.job_sqlite_store import AgentJobSQLiteStore as JobSqliteStore
from .infrastructure.executable_resolver import ExecutableResolver as resolve_executable
from .infrastructure.command_runner import SubprocessCommandRunner as run_command
from .infrastructure.time_provider import TimeProvider as now_utc
from .tool_registry import capability_map, resolve_tool
from .tool_dispatch import dispatch_tool_call
from .tool_schemas import TOOL_SCHEMAS
from .tool_selection import select_tool
from .agent_entry import run_planner_job
from .app import create_broker_app
from .helper import (
    dict_or_empty,
    list_or_empty,
    compact_text,
    json_size,
    bridge_result_digest,
)

__all__ = [
    # Core imports
    "run_agentic_planner_job",
    "planner_decision",
    "validate_planner_decision_against_evidence",
    "normalize_planner_decision",
    "EvidenceBuilder",
    "planner_evidence_contract",
    # Config constants
    "WRITE_GUARDED_TOOLS",
    "AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES",
    "AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY",
    "AGENTIC_PLANNER_NATIVE_TOOLS",
    "AGENTIC_PLANNER_HISTORY_PROMPT_TAIL",
    "AGENTIC_PLANNER_NUM_CTX",
    "AGENTIC_PLANNER_NUM_CTX_CAP",
    "AGENTIC_PLANNER_NUM_CTX_REQUESTED",
    "AGENTIC_PLANNER_NUM_PREDICT",
    "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET",
    "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO",
    "AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS",
    "AGENTIC_PLANNER_STEP_TIMEOUT",
    "AGENTIC_RESULT_COMPACT_CHARS",
    "AGENTIC_PLANNER_PRESENCE_PENALTY",
    "AGENTIC_PLANNER_TEMPERATURE",
    "AGENTIC_PLANNER_TOP_K",
    "AGENTIC_PLANNER_TOP_P",
    "AGENT_DEFAULT_MAX_STEPS",
    "AGENT_MAX_STEPS",
    "LAB_REPO",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_TASK_MODEL",
    "OLLAMA_TASK_URL",
    "PLANNER_MODEL",
    "PLANNER_INTRINSIC_CONTEXT_MAX_CHARS",
    "PLANNER_INTRINSIC_RAG_CHAR_BUDGET",
    "PLANNER_INTRINSIC_RAG_TOP_K",
    "PLANNER_RAG_DB",
    "PLANNER_RAG_EMBEDDING_BATCH_SIZE",
    "PLANNER_RAG_EXTERNAL_RERANKER_URL",
    "PLANNER_RAG_RERANK_TIMEOUT_SECONDS",
    "PLANNER_RAG_RERANKING_ENGINE",
    "PLANNER_RAG_RERANKING_MODEL",
    "PLANNER_URL",
    "VALID_INTERNAL_TOOLS",
    "internal_tool_prompt",
    "internal_tools_list",
    "ollama_options",
    "AICARMINE_ORIENTATION_LANE_MODE",
    # Cache
    "CACHEABLE_READ_TOOLS",
    "_cached_tool_result",
    "_tool_cache_hit",
    "_tool_cache_key",
    "_cached_vulkan_repair_result",
    "_repair_cache_key",
    "repeated_tool_call_count",
    # JSON I/O
    "_parse_strict_json_object",
    "parse_strict_json_object_diagnostics",
    "post_json",
    "post_json_stream_to_file",
    # Helper functions
    "safe_rel_path",
    "dict_or_empty",
    "list_or_empty",
    "compact_text",
    "json_size",
    "bridge_result_digest",
    # All application modules
    "score_evidence_coverage",
    "goal_requests_semantic_audit",
    "role_guidance_for_goal",
    "role_guidance_text",
    "effective_repo_analysis_goal",
    "final_answer_is_action_plan_without_code_product",
    "goal_requires_code_security_coverage",
    "goal_operational_intent_text",
    "goal_requests_apply",
    "goal_requests_code_product",
    "has_any",
    "input_error_goal",
    "semantic_goal_classification",
    "semantic_goal_low",
    "extract_existing_goal_paths",
    "extract_existing_goal_path",
    "goal_requested_repo_scope",
    "requested_file_limit_from_goal",
    "initial_orientation_surface_from_history",
    "repo_read_items_for_prompt",
    "required_working_set_for_prompt",
    "execution_evidence_digest_text",
    "repo_read_content_views",
    "repo_analysis_final_answer_model_quality_request",
    "repo_analysis_final_answer_quality",
    "sanitize_repo_analysis_final_model_quality",
    "dynamic_read_candidate_paths",
    "low_signal_top_dir",
    "meaningful_read_candidates_from_evidence",
    "path_under_scope",
    "read_candidate_sort_key",
    "repo_code_file",
    "repo_doc_or_config",
    "repo_existing_dir",
    "repo_existing_file",
    "repo_path_kind",
    "repo_readable_evidence_file",
    "scope_candidate_source_paths",
    "scope_read_candidates_from_evidence",
    "top_dir",
    "append_unique",
    "extract_headings",
    "extract_key_lines",
    "extract_mentioned_paths",
    "failed_repo_read_paths",
    "failed_repo_list_files_paths",
    "file_memory_from_history",
    "rank_core_candidates",
    "read_items_from_history",
    "repo_list_evidence",
    "successful_repo_read_paths",
    "target_scope_conflict_resolved",
    "add_core_discovery_candidate",
    "core_discovery_candidates_from_intrinsic",
    "core_discovery_read_paths",
    "claim_area_from_user_token",
    "normalize_scope_claim_text",
    "scope_claim_conflict_for_path",
    "user_scope_claims",
    "CODE_PRODUCT_BUILD_STATE_KIND",
    "code_product_action_has_complete_payload",
    "code_product_build_state_has_collecting_progress",
    "code_product_build_state_parse",
    "code_product_build_state_ready_payload",
    "code_product_payload_violations",
    "copyable_example_text",
    "goal_exact_text_block",
    "best_partial_product_for_30b",
    "code_product_answer_text",
    "latest_code_product_payload",
    "partial_product_answer_text",
    "partial_product_clean_text",
    "partial_products_for_30b",
    "CODE_PRODUCT_PAYLOAD_ROUTE_VIOLATIONS",
    "apply_duplicate_window_replan_contract",
    "code_product_build_state_duplicate_write",
    "code_product_build_state_from_result",
    "code_product_build_state_propose_action",
    "code_product_build_state_read_action",
    "code_product_build_state_write_action",
    "code_product_candidate_action",
    "code_product_low_signal_target",
    "code_product_payload_rejection_count",
    "code_product_source_window_candidate",
    "code_product_source_windows_from_reads",
    "failed_code_edit_proposal_validation_row",
    "latest_code_product_build_state",
    "strip_duplicate_window_candidate",
    "successful_code_edit_proposals",
    "successful_repo_read_window_ranges",
    "successful_window_signatures",
    "latest_code_product_for_prompt",
    "agent_flow_diagnostics",
    "controller_guard_count",
    "controller_guard_rejection_signature",
    "controller_guard_rejection_signature_count",
    "recoverable_planner_block",
    "controller_memory_lesson_text",
    "loop_turn_memory_text",
    "write_controller_memory_lesson",
    "write_loop_turn_memory",
    "controller_initial_area_list_plans",
    "controller_initial_area_read_plan",
    "controller_initial_doc_preseed_plan",
    "controller_initial_orientation_candidate_pool",
    "initial_area_file_sort_key",
    "initial_area_sort_key",
    "initial_doc_sort_key",
    "list_result_file_paths",
    "root_surface_dir_paths",
    "root_surface_entries",
    "root_surface_file_paths",
    "controller_orientation_model_select",
    "orientation_shadow_effective_mode",
    "orientation_legacy_selected_candidate_ids",
    "orientation_shadow_selection_metrics",
    "controller_preplanner_rag_query_plan",
    "controller_preplanner_rag_preseed_plan",
    "build_planner_user_payload",
    "compact_evidence_contract_for_prompt",
    "hard_budget_evidence_contract_summary",
    "evidence_contract_continuation_action",
    "forbidden_repeated_prompt_window_calls",
    "planner_scratchpad_next_window_action_from_history",
    "prompt_context_continuation_from_payload",
    "prompt_context_continue_action",
    "prompt_window_consumed_offsets",
    "prompt_window_tracking_metadata_errors",
    "required_working_set_continuation_action",
    "LOCAL_ARTIFACT_KEYS",
    "OLLAMA_STREAM_META_KEYS",
    "PLANNER_HISTORY_NOISE_KEYS",
    "clean_planner_history_value",
    "planner_controller_guard_history_payload",
    "planner_history_arguments",
    "planner_history_evidence_payload",
    "planner_history_item_messages",
    "planner_history_messages_for_ollama",
    "planner_history_reason",
    "planner_history_summary",
    "planner_tool_result_message_payload",
    "compact_history_for_prompt",
    "compact_intrinsic_context_for_prompt",
    "available_tools_window_pack",
    "available_tools_for_user_payload",
    "hard_budget_tool_shape_examples_for_prompt",
    "tool_shape_examples_for_prompt",
    "PROMPT_CHARS_PER_TOKEN",
    "report_exceeds_generation_headroom",
    "prompt_clip_text",
    "prompt_clip_value",
    "text_hash",
    "decision_paths",
    "planner_scratchpad_window_signature",
    "repo_read_window_signature",
    "window_text",
    "history_item_ollama_turn",
    "planner_history_ledger",
    "planner_ollama_turn_from_decision",
    "history_tool_result",
    "history_has_tool",
    "drop_empty_dict_values",
    "evidence_contract_summary_triplet",
    "repo_rel_token",
    "compact_final_state_result",
    "answer_for_openwebui",
    "next_action_for_openwebui",
    "materialize_public_evidence",
    "build_tool_context_for_30b",
    "PUBLIC_LOCAL_REFERENCE_KEYS",
    "decision_for_turn_memory",
    "final_summary_with_ollama_done_reasons",
    "ollama_turn_rows",
    "ollama_turn_summary_text",
    "planner_turn_memory",
    "public_tool_artifact_rows",
    "public_tool_context_limits",
    "public_tool_response",
    "strip_public_artifact_paths",
    "strip_public_local_references",
    "successful_tool_turns",
    "PUBLIC_TERMINAL_POINTER_KEYS",
    "public_terminal_content_key",
    "public_terminal_sanitize_text",
    "public_terminal_sanitize_value",
    "public_terminal_history_ledger",
    "public_terminal_result_for_30b",
    "executed_tool_rows",
    "planner_decision_rows",
    "terminal_context_alias",
    "validation_rejection_rows",
    "candidate_actions_from_evidence",
    "decision_matches_prompt_context_continuation",
    "enforce_required_scratchpad_read_continuation_contract",
    "final_composition_tool_names_from_candidates",
    "preserve_required_next_tool_call_for_prompt",
    "required_next_tool_call_from_action",
    "compact_tool_manifest_for_prompt",
    "filter_tool_manifest_for_names",
    "json_char_len",
    "native_tools_schema_for_planner",
    "planner_last_result_digest",
    "compact_tool_result_for_planner",
    "apply_turn_surface_policy",
    "contract_final_required_now",
    "tool_surface_names_for_turn",
    "required_next_tool_call_satisfaction",
    "append_stale_required_call_marker",
    "canonical_batch_call_key",
    "gate_candidate_actions",
    "attach_action_proof",
    "build_runtime_debug_packet",
    "maybe_enqueue_npu_phi_diagnostic",
    "validate_unified_diff_text",
    "planner_composed_answer",
    "planner_memory_surface",
    "planner_prompt_context_store_window",
    "runtime_sqlite_memory_write",
    "agent_job_planner_stream_path",
    "agent_job_root",
    "append_agent_event",
    "load_agent_job_state",
    "write_agent_job_state",
    "write_json",
    "capability_map",
    "resolve_tool",
    "dispatch_tool_call",
    "TOOL_SCHEMAS",
    "select_tool",
    "run_planner_job",
    "create_broker_app",
    "FilesystemRepo",
    "same_tool_artifact_payload",
    "JobSqliteStore",
    "resolve_executable",
    "run_command",
    "now_utc",
    "monotonic_now",
    # Planner-specific
    "planner_done_token",
    "summarize_history_artifacts",
    "planner_system_for_current_mode",
    "required_next_progress_from_text",
    "required_next_route_has_deterministic_proof",
    "clear_final_terminal_block_state",
    "validate_control_lane_catalog",
    "final_quality_repo_read_allowlist",
    "canonical_invalid_code_product_decision_signature",
    "compact_validation_rejections_tail",
    "disallowed_invalid_code_product_signatures",
    "invalid_code_product_decision_signature_count",
    "invalid_code_product_decision_signature_from_history_item",
    "invalid_decision_signature_key",
    "search_query_is_concrete",
    "collect_repo_paths",
    "_native_tool_calls_decision",
    "_normalize_terminal_planner_decision",
]