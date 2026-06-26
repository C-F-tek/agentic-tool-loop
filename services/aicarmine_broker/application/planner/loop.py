"""Multi-step planner loop owner.
Refactored to use extracted classes:
- GuardEvaluator: All guard evaluation logic
- PlannerLoopController: Main loop execution and decision handling
- EvidenceContractManager: Centralized contract mutations
"""

from __future__ import annotations
import itertools
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping
from ..controller.rag_preseed import *
from ...config import *
from .state import *
from ..shared.evidence_contract_summary import *
from ..tool_surface.batch_contract import *
from ..tool_surface.batch_contract import *
from ..tool_surface.required_tool_call import *
from .guard_evaluator import *
from .loop_controller import *
from .evidence_contract_manager import *
from ..tool_surface.tool_dispatch import *
from ...tool_contract import *


def evaluate_initial_orientation_shadow(
    requested_mode: object,
    root_result: object,
    goal: object,
    semantic_intent: object,
    doc_plan: object,
    area_plans: object,
    candidate_pool_fn: Callable[
        [dict[str, Any]],
        list[dict[str, Any]],
    ],
    selector_fn: Callable[..., dict[str, Any]],
    effective_mode_fn: Callable[[object], str],
    legacy_selected_ids_fn: Callable[..., list[str]],
    selection_metrics_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Initial orientation shadow evaluator - pure function without wiring.
    Evaluates a single root orientation using injected dependencies only.
    Does not know job_id, state/history, execute tools directly, persist artifact,
    emit events, or modify legacy flow. Not called by runtime yet.
    """
    def bounded_text(value: object, limit: int = 32) -> str:
        """Convert value to string safely, strip, truncate."""
        text = ""
        if isinstance(value, str):
            text = value.strip()[:limit]
        elif value is None:
            pass
        else:
            try:
                text = str(value).strip()[:limit]
            except Exception:
                pass
        return text
    
    def bounded_ids(raw_ids: object, allowed_ids: set[str] | None = None, limit: int = 13) -> list[str]:
        """Sanitize IDs: must be list of strings, strip, ignore empty/oversized, dedupe first occurrence, limit count."""
        if not isinstance(raw_ids, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in raw_ids:
            if not isinstance(item, str):
                continue
            id_str = item.strip()
            if not id_str:
                continue
            if len(id_str) > 500:
                continue
            if allowed_ids is not None and id_str not in allowed_ids:
                continue
            if id_str in seen:
                continue
            if len(result) >= limit:
                break
            seen.add(id_str)
            result.append(id_str)
        return result

    def valid_candidates(pool: object) -> list[dict[str, Any]]:
        """Build private valid candidate list from raw pool."""
        if not isinstance(pool, list):
            return []
        valid: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for cand in pool:
            if not isinstance(cand, dict):
                continue
            cid = cand.get("candidate_id", "")
            if not isinstance(cid, str):
                continue
            cid_stripped = cid.strip()
            if not cid_stripped:
                continue
            if len(cid_stripped) > 500:
                continue
            if cid_stripped in seen_ids:
                continue
            new_cand = dict(cand)
            new_cand["candidate_id"] = cid_stripped
            valid.append(new_cand)
            seen_ids.add(cid_stripped)
        return valid
    
# STAGE 1 — EFFECTIVE MODE
    effective_mode_raw = effective_mode_fn(requested_mode)
    effective_mode = "shadow" if effective_mode_raw == "shadow" else "legacy"
    requested_mode_bounded = bounded_text(requested_mode, 32)
    if effective_mode != "shadow":
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": effective_mode,
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "skipped",
            "reason": "mode_not_shadow",
            "selector_called": False,
            "fallback_used": False,
            "candidate_count": 0,
            "candidate_ids": [],
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }
# STAGE 2 — ROOT RESULT GATE
    if not isinstance(root_result, dict) or root_result.get("ok") is not True:
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "skipped",
            "reason": "root_result_not_ok",
            "selector_called": False,
            "fallback_used": False,
            "candidate_count": 0,
            "candidate_ids": [],
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }
# STAGE 3 — CANDIDATE POOL
    try:
        raw_pool = candidate_pool_fn(deepcopy(root_result))
    except Exception as exc:
        error_type_name = type(exc).__name__
        error_text = str(exc)[:500]
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": "candidate_pool_exception",
            "selector_called": False,
            "fallback_used": True,
            "candidate_count": 0,
            "candidate_ids": [],
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": error_type_name,
                "error": error_text,
            },
        }
    valid_candidates_list = valid_candidates(raw_pool)
    candidate_count = len(valid_candidates_list)
    allowed_candidate_ids = {
        candidate["candidate_id"]
        for candidate in valid_candidates_list
    }
    candidate_ids = bounded_ids(
        [c["candidate_id"] for c in valid_candidates_list],
        limit=32,
    )
    if not valid_candidates_list:
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "skipped",
            "reason": "no_candidates",
            "selector_called": False,
            "fallback_used": False,
            "candidate_count": 0,
            "candidate_ids": [],
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }
# STAGE 4 — LEGACY SELECTED IDS
    try:
        legacy_result = legacy_selected_ids_fn(
            candidates=deepcopy(valid_candidates_list),
            doc_plan=deepcopy(doc_plan),
            area_plans=deepcopy(area_plans),
        )
    except Exception as exc:
        error_type_name = type(exc).__name__
        error_text = str(exc)[:500]
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": "legacy_selection_exception",
            "selector_called": False,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": error_type_name,
                "error": error_text,
            },
        }

    legacy_selected_candidate_ids = bounded_ids(
        legacy_result,
        allowed_ids=allowed_candidate_ids,
        limit=13,
    )
# STAGE 5 — SELECTOR
    try:
        goal_bounded = str(goal)[:4000] if isinstance(goal, str) else str(goal)[:4000]
        semantic_intent_copy = deepcopy(semantic_intent) if isinstance(semantic_intent, Mapping) else {}
        selector_result = selector_fn(
            goal=goal_bounded,
            semantic_intent=semantic_intent_copy,
            candidates=deepcopy(valid_candidates_list),
        )
    except Exception as exc:
        error_type_name = type(exc).__name__
        error_text = str(exc)[:500]
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": "selector_exception",
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": error_type_name,
                "error": error_text,
            },
        }
# STAGE 6 — SELECTOR RESULT VALIDATION
    if not isinstance(selector_result, dict):
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "invalid",
            "reason": "selector_result_not_dict",
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": "",
                "rationale": "",
                "confidence": None,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "TypeError",
                "error": "selector returned non-dict",
            },
        }
    selector_ok = selector_result.get("ok") is True
    selector_status = bounded_text(selector_result.get("status"), 64).lower()
    selector_ready = selector_ok and selector_status == "ready"
    rationale_bounded = bounded_text(selector_result.get("rationale"), 1000)
    error_type = selector_result.get("error_type", "")
    error_type_bounded = str(error_type)[:120] if isinstance(error_type, str) else ""
    error = selector_result.get("error", "")
    error_bounded = str(error)[:500] if isinstance(error, str) else ""
    unknown_ids = selector_result.get("unknown_candidate_ids", [])
    duplicate_ids = selector_result.get("duplicate_candidate_ids", [])
    duplicate_input_ids = selector_result.get("duplicate_input_candidate_ids", [])
# NOTE: ok_val and status_val were extracted but not used; selector_ok/status computed below
    confidence_raw = selector_result.get("confidence")
    if isinstance(confidence_raw, bool):
        confidence = None
    elif isinstance(confidence_raw, (int, float)) and 0 <= confidence_raw <= 1:
        confidence = confidence_raw
    else:
        confidence = None
    selected_ids_raw = selector_result.get("selected_candidate_ids", [])
    model_selected_candidate_ids = bounded_ids(
        selected_ids_raw,
        allowed_ids=allowed_candidate_ids,
        limit=13,
    )
    if not selector_ready:
        if selector_status == "unavailable":
            reason_selector = bounded_text(rationale_bounded or "selector_unavailable", 160)
            return {
                "schema": "orientation_shadow_evaluation.v1",
                "lane_id": "orientation.initial",
                "requested_mode": requested_mode_bounded,
                "effective_mode": "shadow",
                "diagnostic_only": True,
                "legacy_authoritative": True,
                "status": "unavailable",
                "reason": reason_selector,
                "selector_called": True,
                "fallback_used": True,
                "candidate_count": candidate_count,
                "candidate_ids": candidate_ids,
                "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
                "model_selected_candidate_ids": [],
                "selection_metrics": {
                    "legacy_count": len(legacy_selected_candidate_ids),
                    "model_count": 0,
                    "selection_overlap": [],
                    "selection_overlap_count": 0,
                    "top1_match": False,
                    "exact_match": True,
                    "would_change_selection": False,
                },
                "model_summary": {
                    "ok": False,
                    "status": "unavailable",
                    "rationale": rationale_bounded,
                    "confidence": confidence,
                    "unknown_candidate_ids": bounded_ids(unknown_ids),
                    "duplicate_candidate_ids": bounded_ids(duplicate_ids),
                    "duplicate_input_candidate_ids": bounded_ids(duplicate_input_ids),
                    "error_type": error_type_bounded,
                    "error": error_bounded,
                },
            }
        reason_invalid = bounded_text(rationale_bounded or "selector_not_ready", 160)
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "invalid",
            "reason": reason_invalid,
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": False,
                "status": selector_status,
                "rationale": rationale_bounded,
                "confidence": confidence,
                "unknown_candidate_ids": bounded_ids(unknown_ids),
                "duplicate_candidate_ids": bounded_ids(duplicate_ids),
                "duplicate_input_candidate_ids": bounded_ids(duplicate_input_ids),
                "error_type": error_type_bounded,
                "error": error_bounded,
            },
        }
# STAGE 7 — SELECTION METRICS
    try:
        metrics_result = selection_metrics_fn(
            legacy_selected_candidate_ids=deepcopy(legacy_selected_candidate_ids),
            model_selected_candidate_ids=deepcopy(model_selected_candidate_ids),
        )
    except Exception as exc:
        error_type_name = type(exc).__name__
        error_text = str(exc)[:500]
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": "selection_metrics_exception",
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": model_selected_candidate_ids,
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": len(model_selected_candidate_ids),
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": True,
                "status": "ready",
                "rationale": rationale_bounded,
                "confidence": confidence,
                "unknown_candidate_ids": bounded_ids(unknown_ids),
                "duplicate_candidate_ids": bounded_ids(duplicate_ids),
                "duplicate_input_candidate_ids": bounded_ids(duplicate_input_ids),
                "error_type": error_type_bounded,
                "error": error_bounded,
            },
        }
    if not isinstance(metrics_result, dict):
        return {
            "schema": "orientation_shadow_evaluation.v1",
            "lane_id": "orientation.initial",
            "requested_mode": requested_mode_bounded,
            "effective_mode": "shadow",
            "diagnostic_only": True,
            "legacy_authoritative": True,
            "status": "unavailable",
            "reason": "selection_metrics_result_not_dict",
            "selector_called": True,
            "fallback_used": True,
            "candidate_count": candidate_count,
            "candidate_ids": candidate_ids,
            "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
            "model_selected_candidate_ids": model_selected_candidate_ids,
            "selection_metrics": {
                "legacy_count": len(legacy_selected_candidate_ids),
                "model_count": len(model_selected_candidate_ids),
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": True,
                "status": "ready",
                "rationale": rationale_bounded,
                "confidence": confidence,
                "unknown_candidate_ids": bounded_ids(unknown_ids),
                "duplicate_candidate_ids": bounded_ids(duplicate_ids),
                "duplicate_input_candidate_ids": bounded_ids(duplicate_input_ids),
                "error_type": "TypeError",
                "error": "selection metrics returned non-dict",
            },
        }
    overlap = metrics_result.get("selection_overlap", [])
    overlap_bounded = bounded_ids(overlap, allowed_ids=allowed_candidate_ids, limit=13)
    overlap_count = len(overlap_bounded)
    legacy_count = len(legacy_selected_candidate_ids)
    model_count = len(model_selected_candidate_ids)
    top1_match_raw = metrics_result.get("top1_match")
    top1_match = (
        top1_match_raw
        if isinstance(top1_match_raw, bool)
        else False
    )
    exact_match_raw = metrics_result.get("exact_match")
    exact_match = (
        exact_match_raw
        if isinstance(exact_match_raw, bool)
        else (
            legacy_selected_candidate_ids
            == model_selected_candidate_ids
        )
    )
    would_change_raw = metrics_result.get("would_change_selection")
    would_change = (
        would_change_raw
        if isinstance(would_change_raw, bool)
        else not exact_match
    )
# SUCCESS RESULT
    return {
        "schema": "orientation_shadow_evaluation.v1",
        "lane_id": "orientation.initial",
        "requested_mode": requested_mode_bounded,
        "effective_mode": "shadow",
        "diagnostic_only": True,
        "legacy_authoritative": True,
        "status": "ready",
        "reason": "selector_ready",
        "selector_called": True,
        "fallback_used": False,
        "candidate_count": candidate_count,
        "candidate_ids": candidate_ids,
        "legacy_selected_candidate_ids": legacy_selected_candidate_ids,
        "model_selected_candidate_ids": model_selected_candidate_ids,
        "selection_metrics": {
            "legacy_count": legacy_count,
            "model_count": model_count,
            "selection_overlap": overlap_bounded,
            "selection_overlap_count": overlap_count,
            "top1_match": top1_match,
            "exact_match": exact_match,
            "would_change_selection": would_change,
        },
        "model_summary": {
            "ok": True,
            "status": "ready",
            "rationale": rationale_bounded,
            "confidence": confidence,
            "unknown_candidate_ids": bounded_ids(unknown_ids),
            "duplicate_candidate_ids": bounded_ids(duplicate_ids),
            "duplicate_input_candidate_ids": bounded_ids(duplicate_input_ids),
            "error_type": error_type_bounded,
            "error": error_bounded,
        },
    }


def run_agentic_planner_job(
    job_id: str,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES = config["AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES"]
    AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY = config["AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY"]
    AGENT_DEFAULT_MAX_STEPS = config["AGENT_DEFAULT_MAX_STEPS"]
    AGENT_MAX_STEPS = config["AGENT_MAX_STEPS"]
    OLLAMA_TASK_MODEL = config["OLLAMA_TASK_MODEL"]
    OLLAMA_TASK_URL = config["OLLAMA_TASK_URL"]
    PLANNER_MODEL = config["PLANNER_MODEL"]
    PLANNER_URL = config["PLANNER_URL"]
    AICARMINE_ORIENTATION_LANE_MODE = config["AICARMINE_ORIENTATION_LANE_MODE"]
    VALID_INTERNAL_TOOLS = config["VALID_INTERNAL_TOOLS"]
    _agent_flow_diagnostics = deps["agent_flow_diagnostics"]
    _agentic_tool_allowed = deps["agentic_tool_allowed"]
    _cached_tool_result = deps["cached_tool_result"]
    _cached_vulkan_repair_result = deps["cached_vulkan_repair_result"]
    _controller_file_code_product_orientation_preseed_plan = deps["controller_file_code_product_orientation_preseed_plan"]
    _controller_guard_rejection_signature = deps["controller_guard_rejection_signature"]
    _controller_guard_rejection_signature_count = deps["controller_guard_rejection_signature_count"]
    _controller_initial_area_list_plans = deps["controller_initial_area_list_plans"]
    _controller_initial_area_read_plan = deps["controller_initial_area_read_plan"]
    _controller_initial_doc_preseed_plan = deps["controller_initial_doc_preseed_plan"]
    _controller_initial_orientation_candidate_pool = deps["controller_initial_orientation_candidate_pool"]
    _controller_orientation_model_select = deps["controller_orientation_model_select"]
    _orientation_shadow_effective_mode = deps["orientation_shadow_effective_mode"]
    _orientation_legacy_selected_candidate_ids = deps["orientation_legacy_selected_candidate_ids"]
    _orientation_shadow_selection_metrics = deps["orientation_shadow_selection_metrics"]
    _controller_memory_target_key = deps["controller_memory_target_key"]
    _controller_preplanner_rag_query_plan = deps["controller_preplanner_rag_query_plan"]
    _controller_preplanner_rag_preseed_plan = deps["controller_preplanner_rag_preseed_plan"]
    _controller_preseed_plan = deps["controller_preseed_plan"]
    _decision_memory_claim_text = deps["decision_memory_claim_text"]
    _decision_raw_planner_text = deps["decision_raw_planner_text"]
    _initial_orientation_surface_from_history = deps["initial_orientation_surface_from_history"]
    _is_unrecoverable_plain_text_planner_output = deps["is_unrecoverable_plain_text_planner_output"]
    _native_required_repaired_tool_decision_disallowed = deps["native_required_repaired_tool_decision_disallowed"]
    _normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
    # NOTE: planner_cuda_rewrite_* deps are kept for validator.py and turn.py usage
    # but the loop-level cuda_rewrite guard has been replaced by judge_lane
    _planner_incomprehensible_retry_count = deps["planner_incomprehensible_retry_count"]
    _planner_memory_false_unavailable_claim = deps["planner_memory_false_unavailable_claim"]
    _planner_replan_specialist_for_validation = deps["planner_replan_specialist_for_validation"]
    _raw_planner_text_classification = deps["raw_planner_text_classification"]
    _should_attempt_vulkan_repair = deps["should_attempt_vulkan_repair"]
    _should_retry_incomprehensible_planner_output = deps["should_retry_incomprehensible_planner_output"]
    _specialist_route_audit = deps["specialist_route_audit"]
    _tool_cache_hit = deps["tool_cache_hit"]
    _tool_cache_key = deps["tool_cache_key"]
    _write_loop_turn_memory = deps["write_loop_turn_memory"]
    agent_job_root = deps["agent_job_root"]
    append_agent_event = deps["append_agent_event"]
    # build_runtime_debug_packet is accessed via loop_controller.build_runtime_debug_packet()
    compact_tool_result_for_planner = deps["compact_tool_result_for_planner"]
    controller_guard_count = deps["controller_guard_count"]
    controller_guard_result_for_validation = deps["controller_guard_result_for_validation"]
    finalize_agentic_job = deps["finalize_agentic_job"]
    load_agent_job_state = deps["load_agent_job_state"]
    planner_decision = deps["planner_decision"]
    planner_evidence_contract = deps["planner_evidence_contract"]
    planner_history_ledger = deps["planner_history_ledger"]
    planner_memory_surface = deps["planner_memory_surface"]
    repeated_tool_call_count = deps["repeated_tool_call_count"]
    validate_planner_decision_against_evidence = deps["validate_planner_decision_against_evidence"]
    vulkan_repair_invalid_planner_decision = deps["vulkan_repair_invalid_planner_decision"]
    write_agent_job_state = deps["write_agent_job_state"]
    write_json = deps["write_json"]

    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    root = agent_job_root(job_id)
    max_steps = max(1, min(int(state.get("max_steps") or AGENT_DEFAULT_MAX_STEPS), AGENT_MAX_STEPS))
    support_subturns_used = 0
    support_semantic_turns_used = 0
    # NOTE: support_semantic_steps_marked and support_subturn_tools were initialized but not used;
    # support_subturn logic now handled by loop_controller
    approval_mode = str(state.get("approval_mode") or "safe_write_lab")
    original_args = dict(state.get("original_args") or {})
    public_tool_name = str(state.get("public_tool_name") or "vulkan_helper")
    history: list[dict[str, Any]] = []
    loop_state = PlannerLoopState(
        _state=state,
        _history=history,
        _history_ledger=planner_history_ledger,
        _evidence_builder=lambda rows: planner_evidence_contract(str(state.get("goal") or ""), rows),
    )

    # ======================================================================
    # Instantiate extracted classes (Phase 1-3 refactoring)
    # ======================================================================
    guard_evaluator = GuardEvaluator(deps, config)
    # NOTE: evidence_contract_manager was instantiated but methods accessed via loop_controller
    loop_controller = PlannerLoopController(
        job_id=job_id,
        deps=deps,
        config=config,
        state=state,
        history=history,
        loop_state=loop_state,
        root=root,
        max_steps=max_steps,
    )

    # ======================================================================
    # Inline helpers replaced by loop_controller methods
    # ======================================================================
    # support_subturn_decision → loop_controller.support_subturn_decision()
    # semantic_step_for_physical_step → loop_controller.semantic_step_for_physical_step()
    # mark_support_subturn → loop_controller.mark_support_subturn()
    # force_terminal_decision_active → loop_controller.force_terminal_decision_active()
    # final_quality_guided_route_available → loop_controller.final_quality_guided_route_available()
    # runtime_debug_packet → loop_controller.build_runtime_debug_packet()
    # persist_loop_turn_memory → loop_controller.persist_turn_memory()
    # _coverage_satisfied → loop_controller.coverage_satisfied()
    # _missing_owner_paths → loop_controller.missing_owner_paths()
    # _dict_field → loop_controller.dict_field()
    # _list_field → loop_controller.list_field()

    state.update({
        "status": "running_agentic",
        "planner_url": PLANNER_URL,
        "planner_model": PLANNER_MODEL,
        "selector_url": OLLAMA_TASK_URL,
        "selector_model": OLLAMA_TASK_MODEL,
    })
    write_agent_job_state(state)
    append_agent_event(
        job_id, "agentic_loop_started",
        "Controlled 30B planner loop started.",
        {"max_steps": max_steps, "planner_url": PLANNER_URL}, step=0,
    )

    initial_orientation_skipped: list[dict[str, Any]] = []

    def update_initial_orientation_state() -> None:
        state["initial_orientation_skipped"] = initial_orientation_skipped[-120:]
        state["initial_orientation_surface"] = _initial_orientation_surface_from_history(
            history,
            initial_orientation_skipped,
        )
        loop_state.refresh_history()
        state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
            str(state.get("goal") or ""),
            history,
            state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else None,
        )
        write_agent_job_state(state)

    def add_initial_orientation_skipped(skipped: list[dict[str, Any]]) -> None:
        for item in skipped:
            if isinstance(item, dict) and item not in initial_orientation_skipped:
                initial_orientation_skipped.append(item)
        update_initial_orientation_state()

    def execute_controller_preseed(preseed_plan: dict[str, Any], preseed_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
        preseed_tool = str(preseed_plan["tool"])
        preseed_args = dict(preseed_plan["arguments"])
        preseed_event = str(preseed_plan["event"])
        preseed_result_event = str(preseed_plan["result_event"])
        preseed_reason = str(preseed_plan["reason"])
        internal_preseed_args = sanitize_tool_args(
            preseed_tool, dict(preseed_args), original_args, public_tool_name
        )
        preseed_cache_key = _tool_cache_key(preseed_tool, internal_preseed_args)
        state["status_message"] = preseed_event.replace("_", " ")
        write_agent_job_state(state)
        append_agent_event(
            job_id,
            preseed_event,
            f"Executing deterministic {preseed_tool} preseed.",
            {
                "tool": preseed_tool,
                "arguments": preseed_args,
                "cache_key": preseed_cache_key,
                "preseed_reason": preseed_reason,
                "preseed_index": preseed_index,
                "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
            },
            step=0,
        )
        try:
            preseed_result = dispatch_tool(
                preseed_tool,
                internal_preseed_args,
                root,
                allow_command=True,
                user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
            )
        except Exception as exc:  # pragma: no cover - defensive artifact preservation
            preseed_result = {
                "ok": False,
                "tool": preseed_tool,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": traceback.format_exc()[-4000:],
            }
        tool_results_dir = root / "tool-results"
        tool_results_dir.mkdir(parents=True, exist_ok=True)
        suffix = str(preseed_plan["artifact_suffix"]).replace("\\", "__").replace("/", "__")
        preseed_path = tool_results_dir / f"step-000-{preseed_index:02d}-controller_preseed_{suffix}.json"
        write_json(preseed_path, preseed_result)
        compact_preseed = compact_tool_result_for_planner(
            preseed_tool, preseed_result if isinstance(preseed_result, dict) else {}
        )
        compact_preseed.update({
            "artifact": str(preseed_path),
            "controller_preseed": True,
            "preseed_reason": preseed_reason,
            "preseed_index": preseed_index,
            "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
        })
        for metadata_key in ("preplanner_rag", "ranked_preplanner_paths"):
            if preseed_plan.get(metadata_key) not in (None, "", [], {}):
                compact_preseed[metadata_key] = preseed_plan[metadata_key]
        if preseed_cache_key:
            compact_preseed["cache_key"] = preseed_cache_key
        append_agent_event(
            job_id,
            preseed_result_event,
            f"{preseed_tool} preseed ok={bool(compact_preseed.get('ok'))}.",
            compact_preseed,
            step=0,
        )
        row = {
            "step": 0,
            "preseed_index": preseed_index,
            "decision": {
                "action": "controller_preseed",
                "tool": preseed_tool,
                "arguments": preseed_args,
                "reason": preseed_reason,
            },
            "tool_result": compact_preseed,
        }
        loop_state.append_history_row(row)
        loop_controller.persist_turn_memory(row)
        update_initial_orientation_state()
        return preseed_result if isinstance(preseed_result, dict) else {}, compact_preseed

    def execute_dynamic_initial_orientation(root_result: dict[str, Any], preseed_index: int) -> int:
        if not root_result.get("ok"):
            return preseed_index
        doc_plan, skipped = _controller_initial_doc_preseed_plan(root_result)
        add_initial_orientation_skipped(skipped)
        if doc_plan:
            execute_controller_preseed(doc_plan, preseed_index)
            preseed_index += 1

        area_plans, skipped = _controller_initial_area_list_plans(root_result)
        add_initial_orientation_skipped(skipped)
        for area_plan in area_plans:
            area_list_result, _area_compact = execute_controller_preseed(area_plan, preseed_index)
            preseed_index += 1
            area_read_plan, skipped = _controller_initial_area_read_plan(area_list_result)
            add_initial_orientation_skipped(skipped)
            if area_read_plan:
                execute_controller_preseed(area_read_plan, preseed_index)
                preseed_index += 1
# Shadow evaluator invocation after legacy flow completes
        if AICARMINE_ORIENTATION_LANE_MODE == "shadow":
            semantic_intent = (
                preplanner_query_plan.get("semantic_intent")
                if (
                    isinstance(preplanner_query_plan, dict)
                    and isinstance(
                        preplanner_query_plan.get("semantic_intent"),
                        dict,
                    )
                )
                else {}
            )
            try:
                shadow_evaluation = evaluate_initial_orientation_shadow(
                    requested_mode=AICARMINE_ORIENTATION_LANE_MODE,
                    root_result=root_result,
                    goal=state.get("goal"),
                    semantic_intent=semantic_intent,
                    doc_plan=doc_plan,
                    area_plans=area_plans,
                    candidate_pool_fn=(
                        _controller_initial_orientation_candidate_pool
                    ),
                    selector_fn=_controller_orientation_model_select,
                    effective_mode_fn=_orientation_shadow_effective_mode,
                    legacy_selected_ids_fn=(
                        _orientation_legacy_selected_candidate_ids
                    ),
                    selection_metrics_fn=(
                        _orientation_shadow_selection_metrics
                    ),
                )
            except Exception:
                shadow_evaluation = None
            if isinstance(shadow_evaluation, dict):
                shadow_event_payload = deepcopy(shadow_evaluation)
                shadow_event_payload["preseed_index_after_legacy"] = int(
                    preseed_index
                )
                try:
                    append_agent_event(
                        job_id,
                        "orientation_shadow_evaluated",
                        (
                            "Initial orientation shadow evaluation completed "
                            f"with status={shadow_evaluation.get('status')}."
                        ),
                        shadow_event_payload,
                        step=0,
                    )
                except Exception:
                    pass

        return preseed_index

    preseed_index = 1
    preplanner_args = dict(original_args)
    preplanner_query_plan: dict[str, Any] = {}
    try:
        preplanner_query_plan = _controller_preplanner_rag_query_plan(str(state.get("goal") or ""))
    except Exception as exc:  # pragma: no cover - query planning must not block deterministic RAG
        preplanner_query_plan = {
            "schema": "agentic_loop_preplanner_rag_query_plan.v1",
            "ok": False,
            "status": "unavailable",
            "source": "planner",
            "reason": "query_plan_unhandled_exception",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "semantic_intent_required": False,
            "semantic_intent_available": False,
            "preplanner_rag_can_continue": True,
            "fallback_scope": "deterministic_rag_preseed_only",
        }
    if preplanner_query_plan:
        state["controller_preplanner_rag_query_plan"] = preplanner_query_plan
        preplanner_args["controller_rag_query_plan"] = preplanner_query_plan
        write_agent_job_state(state)
        append_agent_event(
            job_id,
            "controller_preplanner_rag_query_plan_result",
            f"Controller pre-planner RAG query plan status={preplanner_query_plan.get('status')}.",
            preplanner_query_plan,
            step=0,
        )
        if (
            preplanner_query_plan.get("semantic_intent_required") is True
            and preplanner_query_plan.get("ok") is not True
        ):
# Issue 1: Use fallback deterministico instead of blocking
# Use query_plan_continue_without_model() for semantic intent failures
            preplanner_query_plan = query_plan_continue_without_model(
                preplanner_query_plan,
                reason=preplanner_query_plan.get("reason") or "planner_query_plan_semantic_intent_unusable_after_retry",
                attempt=1,
                planner_model=PLANNER_MODEL,
                timeout_seconds=AGENTIC_PLANNER_STEP_TIMEOUT,
            )
 # Issue 1.1: Propagate fallback to state and args before calling _controller_preplanner_rag_preseed_plan
            state["controller_preplanner_rag_query_plan"] = preplanner_query_plan
            preplanner_args["controller_rag_query_plan"] = preplanner_query_plan
            write_agent_job_state(state)
            row = {
                "step": 0,
                "decision": {
                    "action": "controller_fallback",
                    "reason": "preplanner_semantic_intent_unusable_continue_deterministically",
                },
                "tool_result": {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "preplanner_semantic_intent_fallback",
                    "summary": "semantic preplanner unavailable; deterministic RAG preseed remains enabled",
                    "preplanner_query_plan": preplanner_query_plan,
                },
            }
            loop_state.append_history_row(row)
            loop_controller.persist_turn_memory(row)
            write_agent_job_state(state)
# Continue with deterministic RAG preseed instead of blocking
            preplanner_plan = None
    preplanner_plan: dict[str, Any] | None = None
    preplanner_report: dict[str, Any] = {}
    preplanner_skipped: list[dict[str, Any]] = []
    try:
        preplanner_plan, preplanner_report, preplanner_skipped = _controller_preplanner_rag_preseed_plan(
            str(state.get("goal") or ""),
            preplanner_args,
        )
    except Exception as exc:  # pragma: no cover - loop must fall back to legacy preseed
        preplanner_report = {
            "schema": "agentic_loop_preplanner_rag.v1",
            "ok": False,
            "status": "failed",
            "reason": "preplanner_rag_unhandled_exception",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
        preplanner_skipped = [{
            "stage": "preplanner_rag_reindex",
            "reason": "preplanner_rag_unhandled_exception",
            "error": str(exc),
        }]
    state["controller_preplanner_rag"] = preplanner_report
    write_agent_job_state(state)
    append_agent_event(
        job_id,
        "controller_preplanner_rag_reindex_result",
        f"Controller pre-planner RAG reindex status={preplanner_report.get('status')}.",
        preplanner_report,
        step=0,
    )
    add_initial_orientation_skipped(preplanner_skipped)
# Issue 7: Fix RAG preseed success measurement - use success_count > 0 instead of just ranked_paths count
    ranked_preseed_success = False
    ranked_paths: list[str] = []
    if preplanner_plan:
        _preplanner_result, preplanner_compact = execute_controller_preseed(preplanner_plan, preseed_index)
        preseed_index += 1
        raw_ranked_paths = preplanner_compact.get("ranked_preplanner_paths")
        ranked_path_items = raw_ranked_paths if isinstance(raw_ranked_paths, list) else []
        ranked_paths = [
            str(path) for path in ranked_path_items
            if str(path).strip()
        ]
# Use success_count from preplanner_compact instead of just counting ranked_paths
        ranked_preseed_success = bool(
            preplanner_compact.get("ok")
            and int(preplanner_compact.get("success_count") or 0) > 0
        )
    preseed_plan = _controller_preseed_plan(str(state.get("goal") or ""), original_args)
    if preseed_plan:
        skip_generic_root_surface = (
            ranked_preseed_success
            and str(preseed_plan.get("tool") or "") == "repo_tree"
            and str(preseed_plan.get("reason") or "") == "generic_repo_request_needs_root_surface"
        )
        if skip_generic_root_surface:
            add_initial_orientation_skipped([{
                "candidate": "repo_tree:.",
                "reason": "preplanner_rag_ranked_read_replaced_generic_root_surface",
                "stage": "initial_root_surface",
            }])
            append_agent_event(
                job_id,
                "controller_preseed_root_surface_skipped",
                "Generic root repo_tree preseed skipped after ranked RAG read preseed.",
                {
                    "replacement": "controller_preseed_preplanner_rag_ranked_read",
                    "preseed_reason": preseed_plan.get("reason"),
                    "ranked_path_count": len(ranked_paths),
                },
                step=0,
            )
        else:
            root_preseed_result, _root_compact = execute_controller_preseed(preseed_plan, preseed_index)
            preseed_index += 1
            if preseed_plan.get("dynamic_initial_orientation") and root_preseed_result.get("ok"):
                preseed_index = execute_dynamic_initial_orientation(root_preseed_result, preseed_index)
            orientation_plan = _controller_file_code_product_orientation_preseed_plan(str(state.get("goal") or ""))
            if orientation_plan and not preseed_plan.get("dynamic_initial_orientation"):
                orientation_result, _orientation_compact = execute_controller_preseed(
                    orientation_plan,
                    preseed_index,
                )
                preseed_index += 1
                preseed_index = execute_dynamic_initial_orientation(orientation_result, preseed_index)
    for step in itertools.count(1):
        semantic_step = loop_controller.get_semantic_step(step)
        if semantic_step > max_steps:
            break
        state = load_agent_job_state(job_id) or state
        if str(state.get("status") or "") == "cancel_requested":
            return finalize_agentic_job(job_id, state, "cancelled", "Job cancelled.", {"history": history})
        goal_text = str(state.get("goal") or "")
        step_budget_guidance = loop_controller.build_step_budget_guidance(semantic_step)
        if step_budget_guidance:
            state["planner_step_budget_guidance"] = step_budget_guidance
        else:
            state.pop("planner_step_budget_guidance", None)
        contract_snapshot = planner_evidence_contract(goal_text, history)
        memory_snapshot = planner_memory_surface({
            "goal": goal_text,
            "limit": 12,
            "target_key": _controller_memory_target_key(goal_text, contract_snapshot),
        }, root)
        successful_paths = (
            contract_snapshot.get("successful_repo_read_paths")
            if isinstance(contract_snapshot.get("successful_repo_read_paths"), list)
            else []
        )
        candidate_actions = (
            contract_snapshot.get("candidate_next_actions")
            if isinstance(contract_snapshot.get("candidate_next_actions"), list)
            else []
        )
        file_memory = (
            contract_snapshot.get("file_memory")
            if isinstance(contract_snapshot.get("file_memory"), list)
            else []
        )
        rejections_tail = (
            contract_snapshot.get("validation_rejections_tail")
            if isinstance(contract_snapshot.get("validation_rejections_tail"), list)
            else []
        )
        candidate_action_preview = []
        for action in candidate_actions[:6]:
            if not isinstance(action, dict):
                continue
            candidate_action_preview.append({
                key: action.get(key)
                for key in ("action_id", "tool", "arguments", "reason")
                if action.get(key) not in (None, "", [], {})
            })
        planner_memory_records = memory_snapshot.get("records") if isinstance(memory_snapshot.get("records"), list) else []
        operational_notes = (
            contract_snapshot.get("operational_notes")
            if isinstance(contract_snapshot.get("operational_notes"), dict)
            else {}
        )
        operational_notes_compact = {
            key: (
                str(operational_notes.get(key))[:900]
                if isinstance(operational_notes.get(key), str)
                else operational_notes.get(key)
            )
            for key in (
                "final_allowed",
                "next_instruction",
                "required_next_progress",
                "step_budget_hint",
            )
            if operational_notes.get(key) not in (None, "", [], {})
        }
        contract_snapshot_summary, contract_snapshot_chars, contract_snapshot_sha256 = (
            evidence_contract_summary_triplet(
                contract_snapshot,
                schema="planner_evidence_contract_history_summary.v1",
            )
        )
        state.update({
            "current_step": step,
            "semantic_step": semantic_step,
            "support_subturns_used": support_subturns_used,
            "support_semantic_turns_used": support_semantic_turns_used,
            "status_message": "planning next action",
            "evidence_contract": contract_snapshot_summary,
            "evidence_contract_chars": contract_snapshot_chars,
            "evidence_contract_sha256": contract_snapshot_sha256,
            "planner_memory_surface": memory_snapshot,
            "working_memory_for_30b": {
                "schema": "agentic_loop_operational_memory.v1",
                "goal": state.get("goal"),
                "physical_step": step,
                "semantic_step": semantic_step,
                "history_count": len(history),
                "successful_repo_read_paths": successful_paths[-24:],
                "successful_repo_read_path_count": len(successful_paths),
                "latest_repo_list_path": (contract_snapshot.get("repo_list_files_evidence") or [{}])[-1].get("path") if contract_snapshot.get("repo_list_files_evidence") else None,
                "candidate_next_actions": candidate_action_preview,
                "candidate_next_action_count": len(candidate_actions),
                "file_memory_count": len(file_memory),
                "file_memory_paths": [
                    row.get("path")
                    for row in file_memory[:20]
                    if isinstance(row, dict) and row.get("path") not in (None, "")
                ],
                "operational_notes": operational_notes_compact,
                "planner_memory": {
                    "schema": memory_snapshot.get("schema"),
                    "available": bool(memory_snapshot),
                    "record_count": len(planner_memory_records),
                    "target_key": memory_snapshot.get("target_key"),
                    "records_omitted_from_working_memory": True,
                },
                "finalization_contract": contract_snapshot.get("finalization_contract", {}),
                "codex_quality": contract_snapshot.get("agentic_codex_quality", {}),
                "rejection_count": len(rejections_tail),
                "rejections_tail": rejections_tail[-6:],
                "planner_step_budget_guidance": step_budget_guidance,
            },
        })
        write_agent_job_state(state)
# The planner must remain the decision-maker. 3572 may validate or reject
# the proposal, but must not synthesize hidden tool calls such as an
# automatic repo_read after repo_list_files.
        planner_role_override = (
            dict(state.get("planner_role_override"))
            if isinstance(state.get("planner_role_override"), dict)
            else {}
        )
        if planner_role_override:
            append_agent_event(
                job_id,
                "planner_role_call_started",
                f"Planner role {planner_role_override.get('role')} started on GPU1.",
                {
                    "role": planner_role_override.get("role"),
                    "provider": "gpu1_planner",
                    "planner_model": PLANNER_MODEL,
                    "planner_url": PLANNER_URL,
                    "rewrite_target": planner_role_override.get("rewrite_target"),
                    "source_step": planner_role_override.get("source_step"),
                },
                step=step,
            )
        try:
            decision = planner_decision(job_id, state, step, history)
        except Exception as exc:
            if planner_role_override:
                append_agent_event(
                    job_id,
                    "planner_role_call_failed",
                    f"Planner role {planner_role_override.get('role')} failed.",
                    {
                        "role": planner_role_override.get("role"),
                        "provider": "gpu1_planner",
                        "planner_model": PLANNER_MODEL,
                        "planner_url": PLANNER_URL,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1000],
                    },
                    step=step,
                )
                state.pop("planner_role_override", None)
                write_agent_job_state(state)
            raise
        if planner_role_override:
            decision["planner_role"] = planner_role_override.get("role")
            decision["planner_role_override"] = planner_role_override
            append_agent_event(
                job_id,
                "planner_role_call_completed",
                f"Planner role {planner_role_override.get('role')} returned a candidate decision.",
                {
                    "role": planner_role_override.get("role"),
                    "provider": "gpu1_planner",
                    "planner_model": PLANNER_MODEL,
                    "planner_url": PLANNER_URL,
                    "rewrite_target": planner_role_override.get("rewrite_target"),
                    "candidate_action": decision.get("action"),
                    "candidate_tool": decision.get("tool"),
                },
                step=step,
            )
            state.pop("planner_role_override", None)
            write_agent_job_state(state)
        append_agent_event(
            job_id, "planner_decision",
            f"Decision: {decision.get('action')} {decision.get('tool', '')}",
            decision, step=step,
        )
        planner_memory_snapshot = (
            state.get("planner_memory_surface")
            if isinstance(state.get("planner_memory_surface"), dict)
            else {}
        )
        memory_claim_text = _decision_memory_claim_text(decision)
# Phase 2: Replace inline memory claim guard with GuardEvaluator
        memory_claim_guard = guard_evaluator.evaluate_memory_claim_guard(
            memory_claim_text=memory_claim_text,
            decision=decision,
            validation={},
            history=history,
            step=step,
            job_id=job_id,
            goal=str(state.get("goal") or ""),
            planner_memory_snapshot=planner_memory_snapshot,
        )
        if memory_claim_guard and not memory_claim_guard.get("should_finalize"):
            guard_result = memory_claim_guard["guard_result"]
            append_agent_event(
                job_id,
                "planner_decision_rejected",
                guard_result["summary"],
                guard_result,
                step=step,
            )
            row = {
                "step": step,
                "decision": {
                    "action": "continue_required",
                    "reason": "planner falsely claimed long-term memory unavailable",
                    "rejected_decision": guard_result["rejected_decision"],
                },
                "tool_result": guard_result,
            }
            loop_state.append_history_row(row)
            state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
                str(state.get("goal") or ""),
                history,
                planner_memory_snapshot,
            )
            loop_controller.persist_turn_memory(row)
            write_agent_job_state(state)
            continue
        elif memory_claim_guard and memory_claim_guard.get("should_finalize"):
            return finalize_agentic_job(
                job_id,
                state,
                memory_claim_guard["final_status"],
                memory_claim_guard["final_reason"],
                memory_claim_guard.get("final_extra", {
                    "history": history,
                    "blocked_by": "planner_memory_false_unavailable_claim",
                    "planner_decision": decision,
                }),
            )

        if (
            str(decision.get("action") or "").strip().lower() == "tool_batch"
            and not loop_controller.force_terminal_decision_active(semantic_step, max_steps)
        ):
            calls = loop_controller.list_field(decision, "tool_calls")
            batch_decisions: list[dict[str, Any]] = []
            batch_guard: dict[str, Any] = {}
            batch_evidence_contract = planner_evidence_contract(str(state.get("goal") or ""), history)
            micro_batch_contract = (
                batch_evidence_contract.get("micro_batch_contract")
                if isinstance(batch_evidence_contract.get("micro_batch_contract"), dict)
                else {}
            )
            used_micro_batch_action_ids: set[str] = set()
            used_micro_batch_call_signatures: set[str] = set()
            if not calls:
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_invalid",
                    "summary": "native_tool_batch_empty",
                    "violations": ["native_tool_batch_empty"],
                    "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        validation={
                            "ok": False,
                            "violations": ["native_tool_batch_empty"],
                            "evidence_contract": batch_evidence_contract,
                        },
                    ),
                }
            elif len(calls) > int(AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY or 1):
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_too_large",
                    "summary": "native_tool_batch_exceeds_readonly_limit",
                    "violations": ["native_tool_batch_too_large"],
                    "native_tool_call_count": len(calls),
                    "native_tool_call_limit": int(AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY or 1),
                    "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        validation={
                            "ok": False,
                            "violations": ["native_tool_batch_too_large"],
                            "evidence_contract": batch_evidence_contract,
                        },
                    ),
                }
            elif micro_batch_contract.get("allowed") is not True:
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_contract",
                    "summary": "native_tool_batch_not_allowed_by_evidence_contract",
                    "violations": ["native_tool_batch_not_allowed_by_evidence_contract"],
                    "micro_batch_contract": micro_batch_contract,
                    "native_tool_call_count": len(calls),
                    "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        validation={
                            "ok": False,
                            "violations": ["native_tool_batch_not_allowed_by_evidence_contract"],
                            "evidence_contract": batch_evidence_contract,
                        },
                    ),
                }
            else:
                for call in calls:
                    if not isinstance(call, dict):
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_invalid",
                            "summary": "native_tool_batch_call_invalid",
                            "violations": ["native_tool_batch_call_invalid"],
                            "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                step_number=step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=decision,
                                validation={
                                    "ok": False,
                                    "violations": ["native_tool_batch_call_invalid"],
                                    "evidence_contract": batch_evidence_contract,
                                },
                            ),
                        }
                        break
                    call_decision = {
                        "action": "tool",
                        "tool": normalize_tool_name(str(call.get("tool") or "")),
                        "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                        "reason": "native_tool_call_batch",
                        "native_tool_call": True,
                        "raw_native_tool_call": call.get("raw_tool_call") if isinstance(call.get("raw_tool_call"), dict) else call,
                    }
                    if isinstance(decision.get("allowed_tool_names"), list):
                        call_decision["allowed_tool_names"] = list(decision["allowed_tool_names"])
                    if isinstance(decision.get("allowed_native_tool_names"), list):
                        call_decision["allowed_native_tool_names"] = list(decision["allowed_native_tool_names"])
                    internal_args = sanitize_tool_args(
                        call_decision["tool"],
                        dict(call_decision["arguments"]),
                        original_args,
                        public_tool_name,
                    )
                    call_signature = canonical_batch_call_key(
                        normalize_tool_name(str(call_decision["tool"] or "")),
                        internal_args,
                    )
                    if call_signature in used_micro_batch_call_signatures:
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_duplicate_call",
                            "summary": "native_tool_batch_duplicate_call",
                            "violations": ["native_tool_batch_duplicate_call"],
                            "rejected_decision": call_decision,
                            "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                step_number=step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=call_decision,
                                validation={
                                    "ok": False,
                                    "violations": ["native_tool_batch_duplicate_call"],
                                    "evidence_contract": batch_evidence_contract,
                                },
                            ),
                        }
                        break
                    used_micro_batch_call_signatures.add(call_signature)
                    matched_action = loop_controller.match_micro_batch_action(
                        micro_batch_contract,
                        tool=call_decision["tool"],
                        internal_args=internal_args,
                    )
                    if not matched_action:
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_contract",
                            "summary": "native_tool_batch_call_not_in_micro_batch_contract",
                            "violations": ["native_tool_batch_call_not_in_micro_batch_contract"],
                            "rejected_decision": call_decision,
                            "micro_batch_contract": micro_batch_contract,
                            "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                step_number=step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=call_decision,
                                validation={
                                    "ok": False,
                                    "violations": ["native_tool_batch_call_not_in_micro_batch_contract"],
                                    "evidence_contract": batch_evidence_contract,
                                },
                            ),
                        }
                        break
                    if call_decision["tool"] == "planner_scratchpad_read":
                        matched_args = (
                            matched_action.get("arguments")
                            if isinstance(matched_action.get("arguments"), dict)
                            else {}
                        )
                        call_decision["prompt_context_continuation_required"] = {
                            "tool": "planner_scratchpad_read",
                            "arguments": matched_args,
                            "reason": matched_action.get("reason"),
                        }
                    action_id = str(matched_action.get("action_id") or "").strip()
                    if not action_id or action_id in used_micro_batch_action_ids:
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_contract",
                            "summary": "native_tool_batch_duplicate_or_missing_action_id",
                            "violations": ["native_tool_batch_duplicate_or_missing_action_id"],
                            "rejected_decision": call_decision,
                            "micro_batch_action_id": action_id,
                            "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                step_number=step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=call_decision,
                                validation={
                                    "ok": False,
                                    "violations": ["native_tool_batch_duplicate_or_missing_action_id"],
                                    "evidence_contract": batch_evidence_contract,
                                },
                            ),
                        }
                        break
                    used_micro_batch_action_ids.add(action_id)
                    call_decision["micro_batch_action_id"] = action_id
                    call_decision["micro_batch_contract_schema"] = micro_batch_contract.get("schema")
                    if not _tool_cache_key(call_decision["tool"], internal_args):
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_non_readonly",
                            "summary": "native_tool_batch_requires_readonly_tools_only",
                            "violations": ["native_tool_batch_non_readonly"],
                            "rejected_decision": call_decision,
                            "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                step_number=step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=call_decision,
                                validation={
                                    "ok": False,
                                    "violations": ["native_tool_batch_non_readonly"],
                                    "evidence_contract": batch_evidence_contract,
                                },
                            ),
                        }
                        break
                    validation_i = validate_planner_decision_against_evidence(
                        str(state.get("goal") or ""), call_decision, history
                    )
                    if not validation_i.get("ok"):
                        should_repair_call = _should_attempt_vulkan_repair(call_decision, validation_i, history)
                        repair_result = {
                            "ok": False,
                            "error": "vulkan_repair_not_applicable_for_this_invalid_decision",
                        }
                        if should_repair_call:
                            repair_result = vulkan_repair_invalid_planner_decision(
                                goal=str(state.get("goal") or ""),
                                step=step,
                                decision=call_decision,
                                validation=validation_i,
                                history=history,
                                state=state,
                            )
                        if repair_result.get("ok") and isinstance(repair_result.get("repaired_decision"), dict):
                            repaired_decision = _normalize_terminal_planner_decision(
                                repair_result["repaired_decision"]
                            )
                            if _native_required_repaired_tool_decision_disallowed(repaired_decision):
                                validation_for_debug = validation_without_full_evidence_contract({
                                    "ok": False,
                                    "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                                    "evidence_contract": validation_i.get("evidence_contract"),
                                })
                                batch_guard = {
                                    "tool": "controller_guard",
                                    "ok": True,
                                    "guard_type": "native_tool_batch_validation",
                                    "summary": "vulkan_repair_tool_decision_disallowed_in_native_mode",
                                    "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                                    "rejected_decision": call_decision,
                                    "evidence_contract_summary": validation_for_debug.get("evidence_contract_summary"),
                                    "evidence_contract_chars": validation_for_debug.get("evidence_contract_chars"),
                                    "evidence_contract_sha256": validation_for_debug.get("evidence_contract_sha256"),
                                    "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                                        step_number=step,
                                        phase="CONTROLLER_GUARD",
                                        planner_decision=call_decision,
                                        validation=validation_for_debug,
                                        extra={"repaired_decision_disallowed": True},
                                    ),
                                    "vulkan_repair": repair_result,
                                }
                                break
                            append_agent_event(
                                job_id,
                                "vulkan_gpu0_decision_repair",
                                "Vulkan/GPU0 repaired invalid native batch tool call.",
                                {"repair_ok": True, "repaired_decision": repaired_decision},
                                step=step,
                            )
                            decision = repaired_decision
                            break
                        batch_guard = controller_guard_result_for_validation(
                            validation_i,
                            call_decision,
                            job_id=job_id,
                            step=step,
                            goal=str(state.get("goal") or ""),
                        )
                        batch_guard["guard_type"] = "native_tool_batch_validation"
                        batch_guard["summary"] = "native_tool_batch_validation_failed"
                        if should_repair_call:
                            batch_guard["vulkan_repair"] = repair_result
                        break
                    batch_decisions.append(call_decision)

            if str(decision.get("action") or "").strip().lower() != "tool_batch":
                pass
            elif batch_guard:
                append_agent_event(job_id, "planner_decision_rejected", batch_guard["summary"], batch_guard, step=step)
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": batch_guard["summary"],
                        "rejected_decision": decision,
                    },
                    "tool_result": batch_guard,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
            elif batch_decisions:
                append_agent_event(
                    job_id,
                    "native_tool_batch_executed",
                    f"Executing native read-only tool batch. count={len(batch_decisions)}",
                    {
                        "schema": "native_tool_batch_execution.v1",
                        "count": len(batch_decisions),
                        "micro_batch_action_ids": [
                            decision.get("micro_batch_action_id")
                            for decision in batch_decisions
                            if decision.get("micro_batch_action_id")
                        ],
                    },
                    step=step,
                )
                for idx, batch_decision in enumerate(batch_decisions, start=1):
                    terminal = loop_controller.execute_step(step, batch_decision, substep=idx)
                    if terminal is not None:
                        return terminal
                continue

        validation = validate_planner_decision_against_evidence(
            str(state.get("goal") or ""), decision, history
        )
        if not validation.get("ok"):

            if loop_controller.force_terminal_decision_active(semantic_step, max_steps):


                planner_memory_snapshot = (
                    state.get("planner_memory_surface")
                    if isinstance(state.get("planner_memory_surface"), dict)
                    else {}
                )
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                prior_final_quality_routes = controller_guard_count(
                    history,
                    "guided_terminal_final_quality_route",
                )
                if (
                    loop_controller.final_quality_guided_route_available(validation)
                    and prior_final_quality_routes < 1
                ):
                    guard_result["guard_type"] = "guided_terminal_final_quality_route"
                    guard_result["summary"] = "guided_terminal_final_quality_route"
                    guard_result["planner_step_budget_guidance"] = state.get("planner_step_budget_guidance")
                    guard_result["guided_terminal_feedback_turn"] = True
                    guard_result["final_quality_judge_intervened"] = True
                    guard_result["final_quality_feedback_retry_count"] = prior_final_quality_routes
                    guard_result["final_quality_feedback_retry_limit"] = 1
                    append_agent_event(
                        job_id,
                        "planner_decision_rejected",
                        guard_result["summary"],
                        guard_result,
                        step=step,
                    )
                    row = {
                        "step": step,
                        "decision": {
                            "action": "continue_required",
                            "reason": (
                                "guided terminal final was rejected by final-quality judge; "
                                "planner must follow the judge route without consuming a semantic step"
                            ),
                            "rejected_decision": guard_result.get("rejected_decision"),
                        },
                        "tool_result": guard_result,
                    }
                    loop_controller.mark_support_subturn(row, semantic_step=semantic_step)
                    loop_state.append_history_row(row)
                    loop_controller.persist_turn_memory(row)
                    write_agent_job_state(state)
                    continue
                guard_result["guard_type"] = "guided_terminal_decision_validation_failed"
                guard_result["summary"] = "guided_terminal_decision_validation_failed"
                guard_result["planner_step_budget_guidance"] = state.get("planner_step_budget_guidance")
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": (
                            "guided terminal turn rejected invalid planner decision; "
                            "no further tool step was consumed"
                        ),
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    (
                        "guided_terminal_decision_validation_failed: "
                        "AICARMINE_AGENT_MAX_STEPS reached the guided terminal turn before "
                        "max_steps_reached, but the planner did not produce a validator-accepted "
                        "final/block decision. The controller preserved the available evidence "
                        "and validation details instead of consuming another tool step."
                    ),
                    {
                        "history": history,
                        "blocked_by": "guided_terminal_decision_validation_failed",
                        "planner_decision": decision,
                        "validation": validation,
                        "planner_step_budget_guidance": state.get("planner_step_budget_guidance"),
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )
            validation = loop_controller.enrich_validation_with_replan_specialist(step, decision, validation)
            raw_planner_text = _decision_raw_planner_text(decision)
            retry_limit = (
                AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES
                if semantic_step < max_steps else 0
            )
            planner_memory_snapshot = (
                state.get("planner_memory_surface")
                if isinstance(state.get("planner_memory_surface"), dict)
                else {}
            )
            validation_violations = {
                str(v)
                for v in (
                    validation.get("violations")
                    if isinstance(validation.get("violations"), list)
                    else []
                )
            }

            # Phase 2: Replace inline support_subturn guard with GuardEvaluator
            if loop_controller.support_subturn_decision(decision):
                support_guard = guard_evaluator.evaluate_support_subturn_guard(
                    decision=decision,
                    validation=validation,
                    history=history,
                    step=step,
                    semantic_step=semantic_step,
                    support_subturns_used=loop_controller.support_subturns_used,
                    job_id=job_id,
                    goal=str(state.get("goal") or ""),
                )
                guard_result = support_guard["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "support subturn rejected by evidence validator",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                loop_controller.mark_support_subturn(row, semantic_step=semantic_step)
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                if not support_guard.get("should_continue", True):
                    return finalize_agentic_job(
                        job_id,
                        state,
                        support_guard["final_status"],
                        support_guard["final_reason"],
                        support_guard.get("final_extra", {
                            "history": history,
                            "blocked_by": "support_subturn_validation_failed_repeated",
                            "planner_decision": decision,
                            "validation": validation,
                        }),
                    )
                continue
            # Phase 2: Replace inline native_tool_call guard with GuardEvaluator
            native_tool_guard = guard_evaluator.evaluate_native_tool_call_guard(
                validation=validation,
                decision=decision,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
            )
            if native_tool_guard:
                if native_tool_guard["should_finalize"]:
                    return finalize_agentic_job(
                        job_id,
                        state,
                        native_tool_guard["final_status"],
                        native_tool_guard["final_reason"],
                        native_tool_guard.get("final_extra", {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": "planner_native_tool_call_required_repeated",
                            "validation": validation,
                        }),
                    )
                guard_result = native_tool_guard["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "native planner emitted no message.tool_calls",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
            # Phase 2: Replace inline memory_claim (raw_planner_text) guard with GuardEvaluator
            memory_claim_guard2 = guard_evaluator.evaluate_memory_claim_guard(
                memory_claim_text=raw_planner_text,
                decision=decision,
                validation=validation,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
            )
            if memory_claim_guard2 and not memory_claim_guard2.get("should_finalize"):
                guard_result = memory_claim_guard2["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner falsely claimed long-term memory unavailable",
                        "rejected_decision": guard_result["rejected_decision"],
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                state["agent_flow_diagnostics"] = _agent_flow_diagnostics(
                    str(state.get("goal") or ""),
                    history,
                    planner_memory_snapshot,
                )
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
            elif memory_claim_guard2 and memory_claim_guard2.get("should_finalize"):
                return finalize_agentic_job(
                    job_id,
                    state,
                    memory_claim_guard2["final_status"],
                    memory_claim_guard2["final_reason"],
                    memory_claim_guard2.get("final_extra", {
                        "history": history,
                        "blocked_by": "planner_memory_false_unavailable_claim",
                        "planner_decision": decision,
                    }),
                )

            # Phase 2: Replace inline incomprehensible_output guard with GuardEvaluator
            incomprehensible_guard = guard_evaluator.evaluate_incomprehensible_output_guard(
                decision=decision,
                validation=validation,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
            )
            if incomprehensible_guard:
                guard_result = incomprehensible_guard["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": (
                            "planner output incomprehensible; planner must repeat "
                            "with one pure JSON decision"
                        ),
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue

            # Phase 2: Replace inline repeated_code_product guard with GuardEvaluator
            repeated_code_guard = guard_evaluator.evaluate_repeated_code_product_guard(
                validation=validation,
                decision=decision,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
            )
            if repeated_code_guard:
                guard_result = repeated_code_guard["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner repeated identical invalid code-product decision",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    repeated_code_guard["final_status"],
                    repeated_code_guard["final_reason"],
                    repeated_code_guard.get("final_extra", {
                        "history": history,
                        "blocked_by": "planner_repeated_invalid_code_product_decision",
                        "planner_decision": decision,
                        "validation": validation,
                    }),
                )

            # Phase 2: Replace inline repeated_rejection guard with GuardEvaluator
            repeated_rejection_guard = guard_evaluator.evaluate_repeated_rejection_guard(
                validation=validation,
                decision=decision,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
            )
            if repeated_rejection_guard:
                guard_result = repeated_rejection_guard["guard_result"]
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner repeated identical rejected decision",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    repeated_rejection_guard["final_status"],
                    repeated_rejection_guard["final_reason"],
                    repeated_rejection_guard.get("final_extra", {
                        "history": history,
                        "blocked_by": "repeated_identical_planner_rejection",
                        "planner_decision": decision,
                        "validation": validation,
                    }),
                )

# Judge lane evaluation: replace cuda_rewrite guard with judge authority pattern
# Import judge_lane at the point of use to avoid circular imports
            from .judge_lane import execute_judge_lane, prepare_judge_context
# Evaluate judge decision based on evidence_contract
            judge_result = execute_judge_lane(
                str(state.get("goal") or ""),
                history,
                validation.get("evidence_contract", {}) if isinstance(validation.get("evidence_contract"), dict) else {},
                deps=deps,
                config=config,
            )
# Handle judge decision
            judge_decision = judge_result.get("decision", "continue_discovery")
            
            if judge_decision == "terminal_block":
# Judge determined terminal block - job cannot proceed
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "judge_terminal_block"
                guard_result["summary"] = "judge_terminal_block"
                guard_result["judge_rationale"] = judge_result.get("rationale", "")
                append_agent_event(
                    job_id,
                    "judge_decision",
                    f"Judge: TERMINAL_BLOCK - {judge_result.get('rationale', '')}",
                    judge_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "block",
                        "reason": "Judge terminal block - insufficient evidence after maximum retries",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    f"Judge terminal block: {judge_result.get('rationale', '')}",
                    {
                        "history": history,
                        "blocked_by": "judge_terminal_block",
                        "planner_decision": decision,
                        "validation": validation,
                        "judge_result": judge_result,
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )
            if judge_decision == "final_allowed":
# Judge approved final - allow planner to choose final
                validation["evidence_contract"]["planner_may_choose_final"] = True
                validation["evidence_contract"]["finalization_contract"]["final_allowed"] = True
                validation["evidence_contract"]["finalization_contract"]["planner_may_choose_final"] = True
                append_agent_event(
                    job_id,
                    "judge_decision",
                    "Judge: FINAL_ALLOWED - evidence sufficient for finalization",
                    judge_result,
                    step=step,
                )
# Continue to normal decision handling below (planner can now choose final)
                pass
            elif judge_decision == "rewrite_required":
# Judge determined rewrite required - send to cuda_rewrite lane
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "judge_rewrite_required"
                guard_result["summary"] = "judge_rewrite_required"
                guard_result["judge_rationale"] = judge_result.get("rationale", "")
                guard_result["suggestions"] = judge_result.get("suggestions", [])
                append_agent_event(
                    job_id,
                    "judge_decision",
                    f"Judge: REWRITE_REQUIRED - {judge_result.get('rationale', '')}",
                    judge_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "Judge determined rewrite required",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
            else:
# Default: CONTINUE_DISCOVERY with suggestions
                suggestions = judge_result.get("suggestions", [])
                required_next_progress = judge_result.get("required_next_progress", "")
                append_agent_event(
                    job_id,
                    "judge_decision",
                    f"Judge: CONTINUE_DISCOVERY - {judge_result.get('rationale', '')}",
                    judge_result,
                    step=step,
                )
# Inject suggestions into evidence_contract
                if required_next_progress:
                    validation["evidence_contract"]["required_next_progress"] = required_next_progress
                if suggestions:
                    validation["evidence_contract"]["judge_suggestions"] = suggestions[:5]
# Continue to normal decision handling (planner will get suggestions in prompt)
                pass
# Detect if rewrite_target is stuck on same value (model inability)
            previous_targets = [
                str(row.get("tool_result", {}).get("rewrite_target") or "")
                for row in history[-10:]
                if isinstance(row.get("tool_result"), dict)
            ]
            if len(set(previous_targets)) == 1 and previous_targets[0] == loop_controller.rewrite_target:
                state["planner_stuck_on_rewrite_target"] = loop_controller.rewrite_target
                state["planner_rewrite_stuck_count"] = loop_controller.cuda_rewrite_history_count + 1
            guard_result["planner_role_scheduled"] = state["planner_role_override"]
            append_agent_event(
                job_id,
                "planner_decision_rejected",
                guard_result["summary"],
                guard_result,
                step=step,
            )
            row = {
                "step": step,
                "decision": {
                    "action": "continue_required",
                    "reason": f"planner CUDA rewrite required for rejected {loop_controller.rewrite_target} proposal",
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                        if decision.get(k) not in (None, "", [], {})
                    },
                },
                "tool_result": guard_result,
            }
            loop_state.append_history_row(row)
            loop_controller.persist_turn_memory(row)
            write_agent_job_state(state)
            if "planner_native_mode_non_json_output" in validation_violations:
                prior_native_text_guards = controller_guard_count(
                    history,
                    "planner_native_mode_non_json_output",
                )
                if prior_native_text_guards >= int(retry_limit or 0):
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        (
                            "planner_native_mode_non_json_output_repeated: planner native tool mode "
                            "was active and tools were provided to Ollama, but the planner repeatedly "
                            "returned malformed protocol-shaped text instead of message.tool_calls or "
                            "a valid terminal decision."
                        ),
                        {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": "planner_native_mode_non_json_output_repeated",
                            "validation": validation,
                            "agent_flow_diagnostics": _agent_flow_diagnostics(
                                str(state.get("goal") or ""),
                                history,
                                planner_memory_snapshot,
                            ),
                        },
                    )
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "planner_native_mode_non_json_output"
                guard_result["summary"] = "planner_native_mode_non_json_output"
                guard_result["retry_count"] = prior_native_text_guards
                guard_result["retry_limit"] = int(retry_limit or 0)
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    guard_result["summary"],
                    guard_result,
                    step=step,
                )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner native mode requires native tool_calls or a valid terminal answer",
                        "raw_planner_text": raw_planner_text[:4000],
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
# Phase 2: Replace inline unrecoverable_output guard with GuardEvaluator
            unrecoverable_guard = guard_evaluator.evaluate_unrecoverable_output_guard(
                decision=decision,
                history=history,
                retry_limit=retry_limit,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
            )
            if unrecoverable_guard:
                return finalize_agentic_job(
                    job_id,
                    state,
                    unrecoverable_guard["final_status"],
                    unrecoverable_guard["final_reason"],
                    unrecoverable_guard.get("final_extra", {
                        "history": history,
                        "planner_decision": decision,
                        "blocked_by": decision.get("reason"),
                    }),
                )
            repair_result: dict[str, Any] = {
                "ok": False,
                "error": "vulkan_repair_not_applicable_for_this_invalid_decision",
            }
            cached_repair_result = _cached_vulkan_repair_result(decision, history)
            should_attempt_vulkan = bool(cached_repair_result)
            if cached_repair_result:
                repair_result = cached_repair_result
                append_agent_event(
                    job_id,
                    "vulkan_gpu0_repair_cache_hit",
                    "Reused cached Vulkan/GPU0 repair for identical raw planner output.",
                    {
                        "repair_cache_key": repair_result.get("repair_cache_key"),
                        "cached_from_step": repair_result.get("cached_from_step"),
                        "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                    },
                    step=step,
                )
            else:
                should_attempt_vulkan = _should_attempt_vulkan_repair(decision, validation, history)
            if should_attempt_vulkan and not cached_repair_result:
                repair_result = vulkan_repair_invalid_planner_decision(
                    goal=str(state.get("goal") or ""),
                    step=step,
                    decision=decision,
                    validation=validation,
                    history=history,
                    state=state,
                )

            if (
                should_attempt_vulkan
                and repair_result.get("ok")
                and isinstance(repair_result.get("repaired_decision"), dict)
            ):
                repaired_decision = _normalize_terminal_planner_decision(
                    repair_result["repaired_decision"]
                )
                if _native_required_repaired_tool_decision_disallowed(repaired_decision):
                    repaired_validation = {
                        "ok": False,
                        "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                        "evidence_contract": planner_evidence_contract(str(state.get("goal") or ""), history),
                    }
                else:
                    repaired_validation = validate_planner_decision_against_evidence(
                        str(state.get("goal") or ""), repaired_decision, history
                    )
                append_agent_event(
                    job_id,
                    "vulkan_gpu0_decision_repair",
                    "Vulkan/GPU0/11435 proposed repaired planner decision.",
                    {
                        "repair_ok": bool(repaired_validation.get("ok")),
                        "original_violations": validation.get("violations"),
                        "repaired_validation": repaired_validation,
                        "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                        "repair_cache_key": repair_result.get("repair_cache_key"),
                        "repair_cache_hit": repair_result.get("repair_cache_hit"),
                        "cached_from_step": repair_result.get("cached_from_step"),
                        "repaired_decision": {
                            k: repaired_decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer")
                            if repaired_decision.get(k) not in (None, "", [], {})
                        },
                    },
                    step=step,
                )
                validation_for_debug = validation_without_full_evidence_contract(validation)
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner proposal rejected; explicit Vulkan/GPU0 repair attempted and surfaced",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": {
                        "tool": "controller_guard",
                        "ok": True,
                        "guard_type": "vulkan_decision_repair",
                        "summary": "vulkan_gpu0_11435_repaired_invalid_planner_emission",
                        "violations": validation.get("violations"),
                        "evidence_contract_summary": validation_for_debug.get("evidence_contract_summary"),
                        "evidence_contract_chars": validation_for_debug.get("evidence_contract_chars"),
                        "evidence_contract_sha256": validation_for_debug.get("evidence_contract_sha256"),
                        "runtime_debug_packet": loop_controller.build_runtime_debug_packet(
                            step_number=step,
                            phase="CONTROLLER_GUARD",
                            planner_decision=decision,
                            validation=validation_for_debug,
                            extra={"guard_type": "vulkan_decision_repair"},
                        ),
                        "vulkan_repair": {
                            "ok": True,
                            "raw_text_preview": repair_result.get("raw_text_preview"),
                            "raw_planner_text_preview": repair_result.get("raw_planner_text_preview"),
                            "repair_cache_key": repair_result.get("repair_cache_key"),
                            "repair_cache_hit": repair_result.get("repair_cache_hit"),
                            "cached_from_step": repair_result.get("cached_from_step"),
                            "repaired_decision": {
                                k: repaired_decision.get(k)
                                for k in ("action", "tool", "arguments", "reason", "final_answer")
                                if repaired_decision.get(k) not in (None, "", [], {})
                            },
                            "repaired_validation": repaired_validation,
                        },
                    },
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                if repaired_validation.get("ok"):
                    decision = repaired_decision
                    validation = repaired_validation
                else:
                    continue
# Phase 2: Replace inline final guard (default case) with GuardEvaluator
            final_guard = guard_evaluator.evaluate_final_guard(
                decision=decision,
                validation=validation,
                history=history,
                step=step,
                job_id=job_id,
                goal=str(state.get("goal") or ""),
                planner_memory_snapshot=planner_memory_snapshot,
                should_attempt_vulkan=should_attempt_vulkan,
                repair_result=repair_result,
            )
            if final_guard:
                guard_result = final_guard["guard_result"]
                append_agent_event(
                    job_id, "planner_decision_rejected",
                    guard_result.get("summary") or "Planner decision rejected by evidence validator.",
                    guard_result, step=step,
                )

                if (
                    str(decision.get("action") or "").strip().lower() == "block"
                    and str(decision.get("reason") or "") == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE"
                ):
                    final_answer = str(decision.get("final_answer") or decision.get("reason") or "")
                    if should_attempt_vulkan:
                        final_answer += (
                            "\n\nVulkan/GPU0 11435 repair was attempted and failed: "
                            + str(repair_result.get("error") or "unknown")
                        )
                    raw_text = str(decision.get("raw_planner_text") or "")
                    if raw_text:
                        final_answer += (
                            "\n\nRaw planner output surfaced, first 4000 chars:\n"
                            + raw_text[:4000]
                        )
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        final_answer,
                        {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": decision.get("reason"),
                            "classification": "planner_output_unrecoverable",
                            "raw_planner_text": decision.get("raw_planner_text"),
                            "vulkan_repair": repair_result if should_attempt_vulkan else {"attempted": False},
                        },
                    )
                row = {
                    "step": step,
                    "decision": {
                        "action": "continue_required",
                        "reason": "planner proposal rejected by evidence validator; explicit repair not available or failed",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                loop_state.append_history_row(row)
                loop_controller.persist_turn_memory(row)
                write_agent_job_state(state)
                continue
        decision = _normalize_terminal_planner_decision(decision if isinstance(decision, dict) else {})
        action = str(decision.get("action") or "tool").strip().lower()
# --- final ---
        if action in {"final", "done", "complete", "completed"}:
            final_answer = str(
                decision.get("final_answer") or decision.get("answer")
                or decision.get("summary") or "Job completed."
            )
            terminal_decision = dict(decision)
            terminal_decision["step"] = step
            return finalize_agentic_job(
                job_id, state, "completed", final_answer,
                {"history": history, "planner_decision": terminal_decision},
            )
# --- block ---
        if action in {"block", "blocked", "need_user", "needs_user"}:
# No fallback: do not convert planner block/no-json/timeout into a
# controller_guard loop. Surface the real loop result and artifacts.
            final_answer = str(decision.get("final_answer") or decision.get("reason") or "Job blocked.")
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                final_answer,
                {"history": history, "planner_decision": decision, "blocked_by": decision.get("reason")},
            )
# --- tool ---
        tool = normalize_tool_name(str(decision.get("tool") or ""))
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        if not tool or tool not in VALID_INTERNAL_TOOLS:
# Should be unreachable because validate_planner_decision_against_evidence()
# rejects invalid tools. Do not substitute repo_capabilities here: that
 # would let 3572 replace planner reasoning with a hidden controller step.
            return finalize_agentic_job(
                job_id, state, "blocked_needs_attention",
                f"Planner selected invalid tool: {tool or '<empty>'}.",
                {"history": history, "blocked_by": "invalid_planner_tool", "planner_decision": decision},
            )
        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
        is_support_subturn = loop_controller.support_subturn_decision(decision)
        if repeated_tool_call_count(history, tool, internal_args) >= 2:
            # Phase 3: Replace append_repeat_guard_result with loop_controller method
            repeat_guard_row = {
                "step": step,
                "decision": {
                    "action": "repeat_guard",
                    "tool": tool,
                    "arguments": internal_args,
                },
                "tool_result": {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "repeated_tool_call_guard",
                    "summary": "repeated_tool_call_guard",
                    "_tool": tool,
                    "_arguments": internal_args,
                },
            }
            loop_state.append_history_row(repeat_guard_row)
            loop_controller.persist_turn_memory(repeat_guard_row)
            write_agent_job_state(state)
            continue
        cache_key = _tool_cache_key(tool, internal_args)
        hit = _tool_cache_hit(history, tool, internal_args)
        if hit:
            effective_cache_key = cache_key or str(hit.get("cache_key") or "")
            loop_controller.append_cached_tool_result(
                step,
                decision,
                {
                    "tool": tool,
                    "arguments": internal_args,
                    "cache_key": effective_cache_key,
                    "result": _cached_tool_result(hit, effective_cache_key),
                },
            )
            continue
# approval gate
        allowed, block_reason = _agentic_tool_allowed(tool, internal_args, approval_mode)
        if not allowed:
            append_agent_event(job_id, "tool_blocked", block_reason, {"tool": tool}, step=step)
            return finalize_agentic_job(
                job_id, state, "blocked_needs_consent", block_reason,
                {"history": history, "blocked_tool": tool},
            )
        state["status_message"] = f"executing {tool}"
        write_agent_job_state(state)
        tool_start_payload = {"tool": tool, "arguments": internal_args}
        if is_support_subturn:
            tool_start_payload["support_subturn"] = True
            tool_start_payload["semantic_step"] = semantic_step
        append_agent_event(job_id, "tool_start", f"Executing {tool}",
                            tool_start_payload, step=step)
        result = dispatch_tool(
            tool, internal_args, root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        tool_result_path = root / "tool-results" / f"step-{step:03d}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {})
        compact_result["artifact"] = str(tool_result_path)
        if is_support_subturn:
            compact_result["support_subturn"] = True
            compact_result["semantic_step"] = semantic_step
        if cache_key and bool(compact_result.get("ok")):
            compact_result["cache_key"] = cache_key
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}",
                            compact_result, step=step)
        row = {
            "step": step,
            "decision": {k: v for k, v in decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        }
        if is_support_subturn:
            loop_controller.mark_support_subturn(row, semantic_step=semantic_step)
        loop_state.append_history_row(row, update_evidence=False)
        loop_controller.persist_turn_memory(row)
        write_agent_job_state(state)
 # No controller_auto_final here: the next planner step must inspect the
 # structured evidence and decide whether to continue, read more, or final.
    terminal_contract = planner_evidence_contract(str(state.get("goal") or ""), history)
    if not loop_controller.coverage_satisfied(terminal_contract):
        missing_paths = loop_controller.missing_owner_paths(terminal_contract)
        return finalize_agentic_job(
            job_id,
            state,
            "blocked_needs_attention",
            (
                f"coverage_required: max_steps reached ({max_steps}) before minimum "
                "owner/core read coverage was satisfied."
            ),
            {
                "history": history,
                "blocked_by": "coverage_required",
                "coverage_satisfied": False,
                "missing_owner_paths": missing_paths,
                "evidence_contract": terminal_contract,
            },
        )
    return finalize_agentic_job(
        job_id,
        state,
        "blocked_needs_attention",
        (
            f"planner_failed_to_finalize_with_coverage: max_steps reached ({max_steps}) "
            "after minimum owner/core coverage was satisfied, but planner did not produce "
            "a validator-accepted final/block decision."
        ),
        {
            "history": history,
            "blocked_by": "planner_failed_to_finalize_with_coverage",
            "coverage_satisfied": True,
            "missing_owner_paths": [],
            "evidence_contract": terminal_contract,
        },
    )