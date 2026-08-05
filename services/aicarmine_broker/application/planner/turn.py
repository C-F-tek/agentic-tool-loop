"""Single planner-turn owner for 114from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

34 decision calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ...tool_contract import TOOLS_SCHEMA
from ..planner.lane_catalog import control_lane_event_metadata
from ..prompt.pack_builder import explicit_request_context_from_state
from ..shared.payload_metadata import sha256_text, stable_json_text
from ..tool_surface.candidate_actions import enforce_required_scratchpad_read_continuation_contract


def _dict_from_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _contract_coverage_satisfied(contract: dict[str, Any]) -> bool:
    coverage = _dict_from_mapping(contract.get("minimum_read_coverage"))
    if coverage:
        return coverage.get("coverage_satisfied") is True
    return contract.get("coverage_satisfied") is True


def _planner_step_budget_guidance_from_state(state: dict[str, Any]) -> dict[str, Any]:
    guidance = state.get("planner_step_budget_guidance")
    if not isinstance(guidance, dict):
        return {}
    mode = str(guidance.get("mode") or "").strip()
    if mode not in {"prepare_terminal_decision", "force_terminal_decision"}:
        return {}
    return _dict_from_mapping(guidance)


def _planner_role_override_from_state(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("planner_role_override")
    if not isinstance(value, dict):
        return {}
    role = str(value.get("role") or "").strip().lower()
    if role != "planner_cuda_rewrite":
        return {}
    out = {
        key: value.get(key)
        for key in (
            "schema",
            "role",
            "rewrite_target",
            "source_step",
            "instruction",
            "rejected_decision",
            "validator_violations",
            "evidence_contract_sha256",
        )
        if value.get(key) not in (None, "", [], {})
    }
    out["role"] = role
    out["one_shot"] = True
    out["provider"] = "gpu1_planner"
    return out


def _planner_role_system_suffix(role_override: dict[str, Any]) -> str:
    if str(role_override.get("role") or "") != "planner_cuda_rewrite":
        return ""
    rewrite_target = str(role_override.get("rewrite_target") or "decision")
    instruction = str(role_override.get("instruction") or "").strip()
    return (
        "ACTIVE SPECIALIST ROLE: planner_cuda_rewrite on the same GPU1 planner model. "
        f"Rewrite target={rewrite_target}. This is a one-shot continuation of a "
        "validator-rejected planner decision, not a fresh planning episode. Use the "
        "verified evidence and validator feedback already supplied. Do not restart broad "
        "discovery, do not call Vulkan/GPU0, and do not claim success unless the candidate "
        "satisfies the current evidence contract. Return exactly one normal planner decision; "
        "the validator remains authoritative."
        + (f" Specialist instruction: {instruction}" if instruction else "")
    )


def _apply_step_budget_guidance_to_contract(
    contract: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    guidance = _planner_step_budget_guidance_from_state(state)
    if not guidance:
        return contract
    out = _dict_from_mapping(contract)
    final_contract = _dict_from_mapping(out.get("finalization_contract"))
    coverage_satisfied = _contract_coverage_satisfied(out)
    final_allowed = final_contract.get("final_allowed") is True and coverage_satisfied
    mode = str(guidance.get("mode") or "")
    guidance_payload = {
        "schema": "planner_step_budget_guidance.v1",
        "mode": mode,
        "current_step": guidance.get("current_step"),
        "max_steps": guidance.get("max_steps"),
        "remaining_steps": guidance.get("remaining_steps"),
        "final_allowed_by_evidence_contract": final_allowed,
        "coverage_satisfied": coverage_satisfied,
        "missing_owner_paths": out.get("missing_owner_paths"),
        "controller_does_not_auto_final": True,
    }
    out["planner_step_budget_guidance"] = guidance_payload
    if mode == "prepare_terminal_decision":
        operational = _dict_from_mapping(out.get("operational_notes"))
        operational["step_budget_hint"] = {
            "mode": mode,
            "remaining_steps": guidance_payload["remaining_steps"],
            "instruction": (
                "The configured step budget is almost exhausted. Prefer a validator-accepted "
                "final when the evidence contract allows it; otherwise use at most one targeted "
                "tool call needed to make the final robust."
            ),
        }
        out["operational_notes"] = operational
        return out
    required = _dict_from_mapping(out.get("required_next_tool_call"))
    required_tool = str(required.get("tool") or "").strip()
    if required_tool == "planner_scratchpad_read":
        guidance_payload["terminal_decision_deferred_by_required_continuation"] = True
        out["planner_step_budget_guidance"] = guidance_payload
        out = enforce_required_scratchpad_read_continuation_contract(
            out,
            {
                "tool": "planner_scratchpad_read",
                "arguments": _dict_from_mapping(required.get("arguments")),
                "reason": required.get("reason") or out.get("required_next_progress"),
            },
        )
        operational = _dict_from_mapping(out.get("operational_notes"))
        operational["step_budget_hint"] = {
            "mode": mode,
            "remaining_steps": guidance_payload["remaining_steps"],
            "instruction": (
                "Step budget is exhausted, but an exact planner_scratchpad_read "
                "continuation is still required. Consume that continuation before "
                "any terminal final/block decision."
            ),
        }
        out["operational_notes"] = operational
        return out
    if required_tool in {
        "repo_read",
        "repo_semantic_search",
        "repo_rg_search",
        "repo_search",
        "repo_list_files",
    }:
        guidance_payload["terminal_decision_deferred_by_required_tool_call"] = True
        out["planner_step_budget_guidance"] = guidance_payload
        out["planner_may_choose_final"] = False
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = "step_budget_deferred_by_required_tool_call"
        out["finalization_contract"] = final_contract
        operational = _dict_from_mapping(out.get("operational_notes"))
        operational["step_budget_hint"] = {
            "mode": mode,
            "remaining_steps": guidance_payload["remaining_steps"],
            "instruction": (
                "Step budget is tight, but a model-selected required_next_tool_call is pending. "
                "Execute that exact read-only tool before any terminal final/block decision."
            ),
        }
        out["operational_notes"] = operational
        return out
    final_contract["terminal_decision_required_by_step_budget"] = True
    final_contract["tool_calls_disallowed_by_step_budget"] = True
    final_contract["planner_may_choose_final"] = final_allowed
    final_contract["planner_may_choose_block"] = True
    final_contract["coverage_satisfied"] = coverage_satisfied
    if not coverage_satisfied:
        final_contract["final_allowed"] = False
        final_contract["missing_owner_paths"] = out.get("missing_owner_paths")
    out["finalization_contract"] = final_contract
    out["planner_may_choose_block"] = True
    out["planner_may_choose_final"] = final_allowed
    out["candidate_next_actions"] = []
    out.pop("required_next_tool_call", None)
    out.pop("forbidden_repeated_tool_calls", None)
    if final_allowed:
        required_next_progress = (
            "Step budget is exhausted before max_steps_reached. Produce action=final now "
            "using only verified evidence already present in history, with explicit limits. "
            "If a robust conclusion is impossible from the available evidence, produce "
            "action=block with final_answer explaining the evidence gaps and the exact next "
            "proof needed. Do not call another tool."
        )
    elif not coverage_satisfied:
        required_next_progress = (
            "coverage_required: step budget is exhausted before max_steps_reached, "
            "but minimum_read_coverage.coverage_satisfied=false. Produce action=block "
            "with missing_owner_paths and the exact selective read/search needed; do not final."
        )
    else:
        required_next_progress = (
            "Step budget is exhausted before max_steps_reached and final_allowed=false. "
            "Produce action=block with final_answer explaining why a robust conclusion "
            "cannot be reached from current evidence, cite the blocking evidence gaps, and "
            "name the exact next proof/tool that would be required. Do not call another tool."
        )
    out["required_next_progress"] = required_next_progress
    out["terminal_decision_guidance"] = {
        "schema": "planner_terminal_decision_guidance.v1",
        "terminal_decision_required": True,
        "allowed_actions": ["final", "block"] if final_allowed else ["block"],
        "tool_calls_allowed": False,
        "reason": "configured_step_budget_exhausted_before_max_steps_reached",
    }
    out["allowed_actions"] = ["final", "block"] if final_allowed else ["block"]
    surface_policy = _dict_from_mapping(out.get("turn_tool_surface_policy"))
    surface_policy.update(
        {
            "schema": "planner_turn_tool_surface_policy.v1",
            "reason": "step_budget_force_terminal_decision",
            "locked": True,
            "available_tools": [],
            "allowed_tool_names": [],
            "candidate_actions_filtered": True,
            "locked_empty_tool_surface": True,
            "step_budget_terminal_turn": True,
        }
    )
    out["turn_tool_surface_policy"] = surface_policy
    operational = _dict_from_mapping(out.get("operational_notes"))
    operational["final_allowed"] = final_allowed
    operational["next_instruction"] = required_next_progress
    out["operational_notes"] = operational
    return out


def _looks_like_malformed_native_protocol(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return (
        stripped[0] in "{["
        or lowered.startswith("<tool_call")
        or lowered.startswith("tool_call")
        or lowered.startswith("message.tool_calls")
        or "</tool_call>" in lowered
    )


def _planner_payload_capture_view(
    planner_payload: dict[str, Any],
    user_payload: dict[str, Any],
) -> dict[str, Any]:
    capture = dict(planner_payload)
    messages = planner_payload.get("messages") if isinstance(planner_payload.get("messages"), list) else []
    capture_messages: list[dict[str, Any]] = []
    last_user_index = len(messages) - 1
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        row = dict(message)
        if index == last_user_index and row.get("role") == "user":
            content = str(row.get("content") or "")
            row["content"] = {
                "schema": "planner_payload_user_message_ref.v1",
                "ref": "user_payload",
                "chars": len(content),
                "sha256": sha256_text(content),
                "content_omitted_from_capture": True,
            }
            row["user_payload_sha256"] = sha256_text(stable_json_text(user_payload))
        capture_messages.append(row)
    capture["messages"] = capture_messages
    capture["capture_compacted"] = True
    capture["runtime_request_unchanged"] = True
    return capture


def _native_plain_text_final_decision(
    raw_text: str,
    *,
    native_tool_names: list[str],
    prompt_context_continuation_required: dict[str, Any],
    stream_meta: dict[str, Any],
) -> dict[str, Any]:
    stripped = raw_text.strip()
    decision: dict[str, Any] = {
        "action": "final",
        "final_answer": stripped,
        "raw_planner_text": raw_text[:12000],
        "raw_planner_text_preview": raw_text[:2000],
        "planner_native_tools_enabled": True,
        "native_tool_calls_seen": 0,
        "native_tool_text_decision_allowed": "plain_text_final",
        "controller_wrapped_plain_text_final": True,
        "controller_wrap_reason": (
            "native_tool_mode_plain_text_terminal_candidate"
        ),
        "allowed_tool_names": list(native_tool_names),
    }
    if prompt_context_continuation_required:
        decision["prompt_context_continuation_required"] = prompt_context_continuation_required
    if stream_meta:
        decision["planner_stream_meta"] = stream_meta
    return decision


def _degenerate_output_block_decision(
    response: Mapping[str, Any],
    stream_path: Path,
    *,
    stream_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    partial = str(response.get("partial_content") or response.get("response") or "")
    decision: dict[str, Any] = {
        "action": "block",
        "reason": f"PLANNER_DEGENERATE_OUTPUT_NON_JSON:{response.get('error')}",
        "final_answer": (
            "Planner 30B produced degenerate output. No partial JSON extraction, "
            "plaintext recovery, or controller fallback normalization was executed. "
            "Plain text output must be retried by the planner; malformed JSON or "
            "recognizable invalid tool calls remain eligible for Vulkan/GPU0 11435 repair. "
            f"Partial stream chars={len(partial)}. Stream artifact={stream_path}."
        ),
        "raw_planner_text": partial[:12000],
    }
    if stream_meta:
        decision["planner_stream_meta"] = dict(stream_meta)
    return decision


def _post_final_reject_turn_tool_names(
    evidence_contract: dict[str, Any],
    tool_names: list[str],
    *,
    known_tool_names: set[str] | None = None,
) -> list[str]:
    known_by_lower = {}
    for name in known_tool_names or tool_names:
        canonical_name = str(name or "").strip()
        if canonical_name:
            known_by_lower[canonical_name.lower()] = canonical_name
    if not isinstance(evidence_contract, dict):
        return tool_names
    final_rewrite_latch = str(evidence_contract.get("final_rewrite_latch") or "inactive").strip().lower()
    supported_latches = {
        "rewrite_required",
        "required_gap_only",
        "terminal_block_required",
    }
    if final_rewrite_latch not in supported_latches:
        if not bool(evidence_contract.get("planner_cuda_rewrite_required")):
            return tool_names
        rewrite_count = int(evidence_contract.get("planner_final_quality_reject_count") or 0)
        if rewrite_count < 1:
            return tool_names
    if final_rewrite_latch == "terminal_block_required":
        return []
    required = evidence_contract.get("required_next_tool_call")
    required_tool_raw = str(required.get("tool") or "").strip() if isinstance(required, dict) else ""
    required_tool_key = required_tool_raw.lower()
    if required_tool_key:
        canonical_required_tool = known_by_lower.get(required_tool_key)
        if canonical_required_tool:
            return [canonical_required_tool]
        evidence_contract["required_next_tool_call_invalid_tool"] = required_tool_raw
        evidence_contract["required_next_tool_call_invalid_reason"] = (
            "required_next_tool_call.tool is not present in the planner tool registry"
        )
        evidence_contract.pop("required_next_tool_call", None)
        evidence_contract["planner_may_choose_final"] = False
        evidence_contract["planner_may_choose_block"] = True
        evidence_contract["required_next_progress"] = (
            f"required_next_tool_call references unknown tool {required_tool_raw!r}. "
            "Return action=block with invalid contract diagnostic instead of calling "
            "an unknown tool."
        )
        final_contract = (
            evidence_contract.get("finalization_contract")
            if isinstance(evidence_contract.get("finalization_contract"), dict)
            else {}
        )
        final_contract["planner_may_choose_final"] = False
        final_contract["planner_may_choose_block"] = True
        final_contract["final_allowed"] = False
        final_contract["reason"] = "required_next_tool_call_unknown_tool"
        evidence_contract["finalization_contract"] = final_contract
        return []
    if final_rewrite_latch in {"rewrite_required", "required_gap_only"}:
        return []
    return []


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    AGENTIC_PLANNER_NATIVE_TOOLS = config["AGENTIC_PLANNER_NATIVE_TOOLS"]
    AGENTIC_PLANNER_NUM_CTX = config["AGENTIC_PLANNER_NUM_CTX"]
    AGENTIC_PLANNER_NUM_CTX_CAP = config["AGENTIC_PLANNER_NUM_CTX_CAP"]
    AGENTIC_PLANNER_NUM_CTX_REQUESTED = config["AGENTIC_PLANNER_NUM_CTX_REQUESTED"]
    AGENTIC_PLANNER_NUM_PREDICT = config["AGENTIC_PLANNER_NUM_PREDICT"]
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = config["AGENTIC_PLANNER_PROMPT_CHAR_BUDGET"]
    AGENTIC_PLANNER_STEP_TIMEOUT = config["AGENTIC_PLANNER_STEP_TIMEOUT"]
    AGENTIC_PLANNER_TEMPERATURE = config["AGENTIC_PLANNER_TEMPERATURE"]
    AGENTIC_PLANNER_TOP_K = config["AGENTIC_PLANNER_TOP_K"]
    AGENTIC_PLANNER_TOP_P = config["AGENTIC_PLANNER_TOP_P"]
    AGENTIC_PLANNER_PRESENCE_PENALTY = config["AGENTIC_PLANNER_PRESENCE_PENALTY"]
    OLLAMA_KEEP_ALIVE = config["OLLAMA_KEEP_ALIVE"]
    PLANNER_INTRINSIC_CONTEXT_MAX_CHARS = config["PLANNER_INTRINSIC_CONTEXT_MAX_CHARS"]
    PLANNER_INTRINSIC_RAG_CHAR_BUDGET = config["PLANNER_INTRINSIC_RAG_CHAR_BUDGET"]
    PLANNER_INTRINSIC_RAG_TOP_K = config["PLANNER_INTRINSIC_RAG_TOP_K"]
    PLANNER_MODEL = config["PLANNER_MODEL"]
    PLANNER_RAG_DB = config["PLANNER_RAG_DB"]
    PLANNER_RAG_EMBEDDING_BATCH_SIZE = config["PLANNER_RAG_EMBEDDING_BATCH_SIZE"]
    PLANNER_RAG_EXTERNAL_RERANKER_URL = config["PLANNER_RAG_EXTERNAL_RERANKER_URL"]
    PLANNER_RAG_RERANKING_ENGINE = config["PLANNER_RAG_RERANKING_ENGINE"]
    PLANNER_RAG_RERANKING_MODEL = config["PLANNER_RAG_RERANKING_MODEL"]
    PLANNER_RAG_RERANK_TIMEOUT_SECONDS = config["PLANNER_RAG_RERANK_TIMEOUT_SECONDS"]
    PLANNER_URL = config["PLANNER_URL"]
    _build_planner_user_payload = deps["build_planner_user_payload"]
    _controller_memory_target_key = deps["controller_memory_target_key"]
    _filter_tool_manifest_for_names = deps["filter_tool_manifest_for_names"]
    _history_tool_result = deps["history_tool_result"]
    _input_error_goal = deps["input_error_goal"]
    _native_tool_calls_decision = deps["native_tool_calls_decision"]
    _native_tools_schema_for_planner = deps["native_tools_schema_for_planner"]
    _normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
    _parse_strict_json_object = deps["parse_strict_json_object"]
    _planner_history_messages_for_ollama = deps["planner_history_messages_for_ollama"]
    _planner_system_for_current_mode = deps["planner_system_for_current_mode"]
    _planner_token_generation_reserve = deps["planner_token_generation_reserve"]
    _prompt_context_continuation_from_payload = deps["prompt_context_continuation_from_payload"]
    _prompt_generation_headroom_char_budget = deps["prompt_generation_headroom_char_budget"]
    _prompt_window_chars = deps["prompt_window_chars"]
    _tool_surface_names_for_turn = deps["tool_surface_names_for_turn"]
    agent_job_planner_stream_path = deps["agent_job_planner_stream_path"]
    agent_job_root = deps["agent_job_root"]
    append_agent_event = deps["append_agent_event"]
    build_planner_intrinsic_context = deps["build_planner_intrinsic_context"]
    goal_requires_code_product_report = deps["goal_requires_code_product_report"]
    history_has_tool = deps["history_has_tool"]
    internal_tools_list = deps["internal_tools_list"]
    normalize_planner_decision = deps["normalize_planner_decision"]
    planner_done_token = deps["planner_done_token"]
    planner_evidence_contract = deps["planner_evidence_contract"]
    planner_memory_surface = deps["planner_memory_surface"]
    post_json_stream_to_file = deps["post_json_stream_to_file"]
    summarize_history_artifacts = deps["summarize_history_artifacts"]
    write_json = deps["write_json"]
    goal = str(state.get("goal") or "")
    planner_role_override = _planner_role_override_from_state(state)
    # Compute planner_lane_id based on planner_role_override
    if planner_role_override and planner_role_override.get("role") == "planner_cuda_rewrite":
        planner_lane_id = "planner.cuda_rewrite"
        trigger = "planner_role_override"
    else:
        planner_lane_id = "planner.primary"
        trigger = "planner_turn"
    planner_lane_metadata = control_lane_event_metadata(
        planner_lane_id,
        step=step,
        attempt=1,
        trigger=trigger,
    )
    if _input_error_goal(goal):
        return {
            "action": "block",
            "reason": "missing_user_request_no_fallback",
            "final_answer": (
                "Public tool call is missing the natural-language user request. "
                "No semantic fallback was generated; the raw input error is surfaced."
            ),
        }
    all_tool_manifest = [
        {
            "name": item["function"]["name"],
            "description": item["function"]["description"],
            "parameters": item["function"]["parameters"],
            "argument_contract": item["function"].get("argument_contract") or {},
        }
        for item in TOOLS_SCHEMA
        if isinstance(item.get("function"), dict)
        and item["function"].get("name") in internal_tools_list(exclude_vulkan=False)
    ]
    known_tool_names = {
        str(item.get("name") or "").strip()
        for item in all_tool_manifest
        if str(item.get("name") or "").strip()
    }
    last_step = history[-1] if history else {}
    last_tool_result = last_step.get("tool_result") if isinstance(last_step, dict) else {}
    evidence_contract = planner_evidence_contract(goal, history)
    planner_memory = state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else {}
    if not planner_memory:
        planner_memory = planner_memory_surface({
            "goal": goal,
            "limit": 12,
            "target_key": _controller_memory_target_key(goal, evidence_contract),
        }, agent_job_root(job_id))
    intrinsic_context = build_planner_intrinsic_context(
        goal=goal,
        history=history,
        evidence_contract=evidence_contract,
        planner_memory=planner_memory,
        rag_db=PLANNER_RAG_DB,
        num_ctx=AGENTIC_PLANNER_NUM_CTX,
        max_chars=PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
        rag_top_k=PLANNER_INTRINSIC_RAG_TOP_K,
        rag_char_budget=PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
        rerank_engine=PLANNER_RAG_RERANKING_ENGINE,
        rerank_url=PLANNER_RAG_EXTERNAL_RERANKER_URL,
        rerank_model=PLANNER_RAG_RERANKING_MODEL,
        rerank_timeout_seconds=PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
        rag_embedding_batch_size=PLANNER_RAG_EMBEDDING_BATCH_SIZE,
    )
    if isinstance(intrinsic_context.get("budget_report"), dict):
        intrinsic_context["budget_report"]["num_ctx_requested"] = AGENTIC_PLANNER_NUM_CTX_REQUESTED
        intrinsic_context["budget_report"]["num_ctx_cap"] = AGENTIC_PLANNER_NUM_CTX_CAP
    explicit_request_context = explicit_request_context_from_state(state)
    if explicit_request_context:
        intrinsic_context["explicit_request_context"] = explicit_request_context
    evidence_contract = planner_evidence_contract(goal, history, intrinsic_context=intrinsic_context)
    evidence_contract = _apply_step_budget_guidance_to_contract(evidence_contract, state)
    if planner_role_override:
        evidence_contract["planner_role_override"] = planner_role_override
    base_tool_names = _tool_surface_names_for_turn(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
    )
    native_tool_names = _post_final_reject_turn_tool_names(
        evidence_contract,
        base_tool_names,
        known_tool_names=known_tool_names,
    )
    final_rewrite_latch = str(evidence_contract.get("final_rewrite_latch") or "inactive").strip().lower()
    if "base_tool_surface_reason" not in evidence_contract:
        turn_tool_surface_policy = (
            evidence_contract.get("turn_tool_surface_policy")
            if isinstance(evidence_contract.get("turn_tool_surface_policy"), dict)
            else {}
        )
        evidence_contract["base_tool_surface_reason"] = (
            str(
                turn_tool_surface_policy.get("reason") or "tool_surface_policy"
            ).strip()
            if final_rewrite_latch == "inactive"
            else "final_rewrite_latch"
        )
    evidence_contract["surface_filter_source"] = (
        "final_rewrite_latch"
        if final_rewrite_latch != "inactive"
        else "tool_surface_policy"
    )
    planner_may_choose_final = bool(evidence_contract.get("planner_may_choose_final"))
    planner_may_choose_block = bool(evidence_contract.get("planner_may_choose_block"))
    surface_filter_source = (
        "final_rewrite_latch"
        if final_rewrite_latch != "inactive"
        else "tool_surface_policy"
    )
    def build_payload_for_native_tool_names(tool_names: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        schema = (
            _native_tools_schema_for_planner(TOOLS_SCHEMA, tool_names)
            if AGENTIC_PLANNER_NATIVE_TOOLS
            else []
        )
        manifest = _filter_tool_manifest_for_names(all_tool_manifest, tool_names)
        payload, budget = _build_planner_user_payload(
            job_id=job_id,
            state=state,
            step=step,
            history=history,
            tool_manifest=manifest,
            evidence_contract=evidence_contract,
            planner_memory=planner_memory,
            intrinsic_context=intrinsic_context,
            last_tool_result=last_tool_result if isinstance(last_tool_result, dict) else {},
            native_tools_schema=schema,
        )
        return payload, budget, schema
    user_payload, prompt_budget, native_tools_schema = build_payload_for_native_tool_names(
        native_tool_names
    )
    prompt_context_continuation_required = _prompt_context_continuation_from_payload(user_payload)
    refined_native_tool_names = _tool_surface_names_for_turn(
        goal=goal,
        evidence_contract=evidence_contract,
        intrinsic_context=intrinsic_context,
        prompt_context_continuation_required=prompt_context_continuation_required,
    )
    refined_native_tool_names = _post_final_reject_turn_tool_names(
        evidence_contract,
        refined_native_tool_names,
        known_tool_names=known_tool_names,
    )
    if AGENTIC_PLANNER_NATIVE_TOOLS and refined_native_tool_names != native_tool_names:
        native_tool_names = refined_native_tool_names
        user_payload, prompt_budget, native_tools_schema = build_payload_for_native_tool_names(
            native_tool_names
        )
        prompt_context_continuation_required = _prompt_context_continuation_from_payload(user_payload)
    runtime_roots = user_payload.get("runtime_roots") if isinstance(user_payload, dict) else {}
    def _normalized_root_root(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        normalized = str(Path(normalized).resolve()).lower().replace("\\", "/").rstrip("/")
        return normalized
    def _is_terminal_runtime_tool(name: str) -> bool:
        lowered = str(name or "").strip().lower()
        return (
            lowered.startswith("terminal_")
            or lowered.startswith("open_terminal_")
            or lowered in {"run_command", "terminal_run_command", "terminal_run_command_wait"}
        )
    runtime_roots_mismatch = False
    if isinstance(runtime_roots, dict):
        lab_root = str(runtime_roots.get("AICARMINE_LAB_REPO") or "").strip()
        open_terminal_cwd = str(runtime_roots.get("OPEN_TERMINAL_CWD") or "").strip()
        open_terminal_workdir = str(runtime_roots.get("AICARMINE_OPEN_TERMINAL_WORKDIR") or "").strip()
        if open_terminal_cwd and lab_root:
            normalized_cwd = _normalized_root_root(open_terminal_cwd)
            normalized_lab = _normalized_root_root(lab_root)
            runtime_roots_mismatch = not (
                normalized_cwd == normalized_lab or normalized_cwd.startswith(f"{normalized_lab}/")
            )
        if not runtime_roots_mismatch and open_terminal_workdir and lab_root:
            normalized_workdir = _normalized_root_root(open_terminal_workdir)
            normalized_lab = _normalized_root_root(lab_root)
            runtime_roots_mismatch = not (
                normalized_workdir == normalized_lab or normalized_workdir.startswith(f"{normalized_lab}/")
            )
    evidence_contract["runtime_roots_mismatch"] = runtime_roots_mismatch
    terminal_runtime_surface = any(
        _is_terminal_runtime_tool(name)
        for name in base_tool_names + native_tool_names
    )
    runtime_roots_mismatch_blocks_final = bool(runtime_roots_mismatch and terminal_runtime_surface)
    evidence_contract["runtime_roots_mismatch_blocks_final"] = runtime_roots_mismatch_blocks_final
    evidence_contract["runtime_roots_mismatch_diagnostic_only"] = bool(
        runtime_roots_mismatch and not runtime_roots_mismatch_blocks_final
    )
    if runtime_roots_mismatch_blocks_final:
        final_contract = (
            evidence_contract.get("finalization_contract")
            if isinstance(evidence_contract.get("finalization_contract"), dict)
            else {}
        )
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["planner_may_choose_block"] = True
        final_contract["reason"] = "runtime_roots_mismatch"
        evidence_contract["finalization_contract"] = final_contract
        evidence_contract["planner_may_choose_final"] = False
        evidence_contract["planner_may_choose_block"] = True
        planner_may_choose_final = False
        planner_may_choose_block = True
        evidence_contract["required_next_progress"] = (
            "Runtime root mismatch detected between lab/workdir and terminal runtime. "
            "Return action=block with explicit root-drift diagnosis and requested alignment, "
            "then continue after root metadata is coherent."
        )
    required_errors = prompt_budget.get("required_working_set_errors") if isinstance(prompt_budget, dict) else []
    if isinstance(prompt_budget, dict):
        native_history_reserve_chars_for_budget = (
            int(prompt_budget.get("native_history_reserve_chars") or 0)
            if AGENTIC_PLANNER_NATIVE_TOOLS
            else 0
        )
        total_prompt_chars_for_budget = int(prompt_budget.get("total_prompt_chars") or 0)
        total_without_native_history_reserve = max(
            0,
            total_prompt_chars_for_budget - native_history_reserve_chars_for_budget,
        )
        generation_headroom_char_budget = int(
            prompt_budget.get("generation_headroom_char_budget")
            or _prompt_generation_headroom_char_budget()
            or 0
        )
        prompt_budget["native_history_reserve_is_synthetic"] = bool(native_history_reserve_chars_for_budget)
        prompt_budget["total_prompt_chars_without_native_history_reserve"] = total_without_native_history_reserve
        prompt_budget["over_budget_without_native_history_reserve"] = bool(
            AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
            and total_without_native_history_reserve > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        )
        prompt_budget["over_generation_headroom_without_native_history_reserve"] = bool(
            generation_headroom_char_budget > 0
            and total_without_native_history_reserve > generation_headroom_char_budget
        )
    hard_required_errors = [
        err for err in (required_errors or [])
        if isinstance(err, dict) and err.get("error") in {
            "repo_read_full_content_window_unavailable",
            "repo_read_full_content_missing_in_required_working_set",
        }
    ]
    effective_prompt_over_budget = (
        bool(prompt_budget.get("over_generation_headroom_budget")) if isinstance(prompt_budget, dict) else False
    )
    if (
        isinstance(prompt_budget, dict)
        and AGENTIC_PLANNER_NATIVE_TOOLS
        and int(prompt_budget.get("native_history_reserve_chars") or 0) > 0
    ):
        effective_prompt_over_budget = bool(
            prompt_budget.get("over_generation_headroom_without_native_history_reserve")
        )
    if (
        isinstance(prompt_budget, dict)
        and effective_prompt_over_budget
        and int(prompt_budget.get("generation_headroom_char_budget") or 0) > 0
    ):
        hard_required_errors.append(
            {
                "error": "planner_prompt_no_generation_headroom",
                "total_prompt_chars": prompt_budget.get("total_prompt_chars"),
                "total_prompt_chars_without_native_history_reserve": prompt_budget.get("total_prompt_chars_without_native_history_reserve"),
                "prompt_char_budget": prompt_budget.get("char_budget"),
                "generation_headroom_char_budget": prompt_budget.get("generation_headroom_char_budget"),
                "generation_headroom_reserve_chars": prompt_budget.get("generation_headroom_reserve_chars"),
                "native_history_reserve_chars": prompt_budget.get("native_history_reserve_chars"),
                "required_working_set_chars": prompt_budget.get("required_working_set_chars"),
            }
        )
    if hard_required_errors:
        headroom_block = any(
            isinstance(err, dict) and err.get("error") == "planner_prompt_no_generation_headroom"
            for err in hard_required_errors
        )
        return {
            "action": "block",
            "reason": (
                "planner_prompt_no_generation_headroom"
                if headroom_block
                else "planner_prompt_required_working_set_invalid"
            ),
            "blocked_by": (
                "planner_prompt_no_generation_headroom"
                if headroom_block
                else "planner_prompt_required_payload_not_complete"
            ),
            "final_answer": (
                (
                    "Planner prompt construction refused to call 11434 without generation headroom. "
                    if headroom_block
                    else "Planner prompt construction refused to send truncated required payload. "
                )
                + f"Errors: {json.dumps(hard_required_errors, ensure_ascii=False, default=str)}"
            ),
            "prompt_budget_report": prompt_budget,
        }
    planner_system_prompt = _planner_system_for_current_mode()
    planner_role_suffix = _planner_role_system_suffix(planner_role_override)
    if planner_role_suffix:
        planner_system_prompt = f"{planner_system_prompt}\n\n{planner_role_suffix}"
        user_payload["planner_role_override"] = planner_role_override
        if isinstance(prompt_budget, dict):
            prompt_budget["planner_role_override"] = {
                "role": planner_role_override.get("role"),
                "rewrite_target": planner_role_override.get("rewrite_target"),
                "chars": len(json.dumps(planner_role_override, ensure_ascii=False, default=str)),
            }
    history_messages: list[dict[str, Any]] = []
    history_messages_report: dict[str, Any] = {
        "schema": "planner_history_messages.v1",
        "enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
        "message_count": 0,
        "message_chars": 0,
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        native_history_reserve_chars = int(prompt_budget.get("native_history_reserve_chars") or 0)
        prompt_chars_without_history_messages = max(
            0,
            int(prompt_budget.get("total_prompt_chars") or 0) - native_history_reserve_chars,
        )
        generation_headroom_char_budget = int(prompt_budget.get("generation_headroom_char_budget") or 0)
        if generation_headroom_char_budget > 0:
            history_message_budget = max(
                0,
                generation_headroom_char_budget - prompt_chars_without_history_messages,
            )
        else:
            history_message_budget = max(0, AGENTIC_PLANNER_NUM_CTX * 2)
        history_messages, history_messages_report = _planner_history_messages_for_ollama(
            history,
            root=agent_job_root(job_id),
            goal=goal,
            window_chars=_prompt_window_chars(True, 0),
            max_chars=history_message_budget,
        )
        prompt_budget["history_messages"] = history_messages_report
        prompt_budget["history_messages_chars"] = history_messages_report.get("message_chars", 0)
        prompt_budget["native_history_reserve_chars"] = native_history_reserve_chars
        prompt_budget["history_message_budget"] = history_message_budget
        prompt_budget["total_prompt_chars_with_history_messages"] = (
            prompt_chars_without_history_messages + int(history_messages_report.get("message_chars") or 0)
        )
        if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0:
            prompt_budget["over_budget_with_history_messages"] = (
                int(prompt_budget["total_prompt_chars_with_history_messages"])
                > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
            )
        if generation_headroom_char_budget > 0:
            prompt_budget["over_generation_headroom_with_history_messages"] = (
                int(prompt_budget["total_prompt_chars_with_history_messages"])
                > generation_headroom_char_budget
            )
            if prompt_budget["over_generation_headroom_with_history_messages"]:
                return {
                    "action": "block",
                    "reason": "planner_prompt_no_generation_headroom",
                    "blocked_by": "planner_prompt_no_generation_headroom",
                    "final_answer": (
                        "Planner prompt construction refused to call 11434 without generation headroom "
                        "after native history transport. "
                        f"total_prompt_chars_with_history_messages={prompt_budget['total_prompt_chars_with_history_messages']} "
                        f"generation_headroom_char_budget={generation_headroom_char_budget}."
                    ),
                    "prompt_budget_report": prompt_budget,
                }
        transportable_history_items = sum(
            1
            for item in (history if isinstance(history, list) else [])
            if _history_tool_result(item)
        )
        if (
            transportable_history_items > 0
            and int(history_messages_report.get("included_history_items") or 0) == 0
            and not prompt_context_continuation_required
        ):
            return {
                "action": "block",
                "reason": "planner_history_messages_budget_unavailable",
                "blocked_by": "planner_history_messages_not_transported",
                "final_answer": (
                    "Native tool mode requires prior tool history/results to be transported "
                    "through Ollama messages. The prompt budget left no room for any full "
                    "SQLite-windowed history message, so the planner was not called with "
                    "lost operational state."
                ),
                "prompt_budget_report": prompt_budget,
            }
    planner_payload = {
        "model": PLANNER_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "messages": [
            {"role": "system", "content": planner_system_prompt},
            *history_messages,
            {"role": "user",
             "content": json.dumps(user_payload, ensure_ascii=False, indent=2, default=str)},
        ],
        "options": {
            "temperature": AGENTIC_PLANNER_TEMPERATURE,
            "top_k": AGENTIC_PLANNER_TOP_K,
            "top_p": AGENTIC_PLANNER_TOP_P,
            "presence_penalty": AGENTIC_PLANNER_PRESENCE_PENALTY,
            "num_ctx": AGENTIC_PLANNER_NUM_CTX,
            "num_predict": AGENTIC_PLANNER_NUM_PREDICT,
        },
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        planner_payload["tools"] = native_tools_schema
    # Always include format=json as fallback so Ollama can return JSON text
    # when it cannot produce message.tool_calls (native tool mode fallback).
    planner_payload["format"] = "json"
    prompt_capture: dict[str, Any] = {
        "ok": False,
        "schema": "planner_payload_capture.v1",
    }
    try:
        prompt_payload_path = agent_job_root(job_id) / "planner-prompts" / f"step-{int(step):03d}-planner-payload.json"
        write_json(
            prompt_payload_path,
            {
                "schema": "planner_payload_capture.v1",
                "job_id": job_id,
                "step": step,
                "planner_url": PLANNER_URL,
                "planner_model": PLANNER_MODEL,
                "planner_role": planner_role_override.get("role") or "main_planner",
                "planner_role_override": planner_role_override,
                "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                "prompt_budget_report": prompt_budget,
                "user_payload": user_payload,
                "planner_payload": _planner_payload_capture_view(planner_payload, user_payload),
            },
        )
        prompt_capture.update({
            "ok": True,
            "path": str(prompt_payload_path),
        })
    except Exception as _e:
        prompt_capture.update({
            "ok": False,
            "error": "planner_payload_capture_failed",
            "error_type": type(_e).__name__,
            "details": str(_e)[:1000],
        })
    planner_stream_timeout_seconds = max(3600, int(AGENTIC_PLANNER_STEP_TIMEOUT or 3600))
    append_agent_event(
        job_id, "planner_request_started",
        f"Planner request step={step} timeout={planner_stream_timeout_seconds}s.",
        {
            "planner_url": PLANNER_URL,
            "planner_model": PLANNER_MODEL,
            "planner_role": planner_role_override.get("role") or "main_planner",
            "planner_role_source_step": planner_role_override.get("source_step"),
            "planner_role_rewrite_target": planner_role_override.get("rewrite_target"),
            "num_ctx_requested": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "num_ctx_cap": AGENTIC_PLANNER_NUM_CTX_CAP,
            "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
            "intrinsic_context_schema": intrinsic_context.get("schema"),
            "intrinsic_context_chars": (intrinsic_context.get("budget_report") or {}).get("intrinsic_context_chars"),
            "intrinsic_rag_status": (intrinsic_context.get("retrieved_rag_chunks") or {}).get("status"),
            "intrinsic_rag_rerank_status": ((intrinsic_context.get("retrieved_rag_chunks") or {}).get("rerank") or {}).get("status"),
            "prompt_char_budget": prompt_budget.get("char_budget") if isinstance(prompt_budget, dict) else None,
            "generation_headroom_char_budget": prompt_budget.get("generation_headroom_char_budget") if isinstance(prompt_budget, dict) else None,
            "generation_headroom_reserve_chars": prompt_budget.get("generation_headroom_reserve_chars") if isinstance(prompt_budget, dict) else None,
            "prompt_payload_chars": prompt_budget.get("total_user_payload_chars") if isinstance(prompt_budget, dict) else None,
            "prompt_over_budget": prompt_budget.get("over_budget") if isinstance(prompt_budget, dict) else None,
            "prompt_over_generation_headroom_budget": prompt_budget.get("over_generation_headroom_budget") if isinstance(prompt_budget, dict) else None,
            "planner_step_timeout_requested_seconds": int(AGENTIC_PLANNER_STEP_TIMEOUT or 0),
            "required_working_set_chars": prompt_budget.get("required_working_set_chars") if isinstance(prompt_budget, dict) else None,
            "tool_surface_names": base_tool_names,
            "native_tool_surface_names": native_tool_names if AGENTIC_PLANNER_NATIVE_TOOLS else [],
            "planner_may_choose_final": planner_may_choose_final,
            "planner_may_choose_block": planner_may_choose_block,
            "surface_filter_source": surface_filter_source,
            "base_tool_surface_reason": str(evidence_contract.get("base_tool_surface_reason") or ""),
            "surface_lock_reason": (
                f"final_rewrite_latch:{final_rewrite_latch}"
                if final_rewrite_latch != "inactive"
                else ""
            ),
            "required_next_tool_call": (
                evidence_contract["required_next_tool_call"]
                if isinstance(evidence_contract.get("required_next_tool_call"), dict)
                else {}
            ),
            "post_filter_applied": base_tool_names != native_tool_names,
            "runtime_roots": runtime_roots,
            "runtime_roots_mismatch": runtime_roots_mismatch,
            "planner_payload_capture": prompt_capture,
            "lane": planner_lane_metadata,
        },
        step=step,
    )
    stream_path = agent_job_planner_stream_path(job_id, step)
    response = post_json_stream_to_file(
        PLANNER_URL, planner_payload,
        timeout=planner_stream_timeout_seconds,
        job_id=job_id, step=step, stream_path=stream_path,
        allow_plain_text_without_json=bool(AGENTIC_PLANNER_NATIVE_TOOLS),
    )
    native_calls = response.get("native_tool_calls") if isinstance(response.get("native_tool_calls"), list) else []
    stream_meta = {
        key: response.get(key)
        for key in (
            "ollama_done_seen",
            "ollama_done_reason",
            "ollama_load_duration",
            "ollama_total_duration",
            "ollama_eval_count",
            "ollama_prompt_eval_count",
        )
        if response.get(key) not in (None, "", [], {})
    }
    if response.get("planner_degenerate_output"):
        return _degenerate_output_block_decision(
            response,
            stream_path,
            stream_meta=stream_meta,
        )
    if native_calls:
        decision = _native_tool_calls_decision(native_calls, str(response.get("response") or ""))
        if decision:
            if planner_role_override:
                decision["planner_role"] = planner_role_override.get("role")
                decision["planner_role_override"] = planner_role_override
            decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
            decision["native_tool_calls_seen"] = len(native_calls)
            decision["allowed_tool_names"] = list(native_tool_names)
            decision["allowed_native_tool_names"] = list(native_tool_names)
            if prompt_context_continuation_required:
                decision["prompt_context_continuation_required"] = prompt_context_continuation_required
            if stream_meta:
                decision["planner_stream_meta"] = stream_meta
            return decision
    if AGENTIC_PLANNER_NATIVE_TOOLS and not native_calls:
        raw_text_for_native_mode = str(response.get("response") or response.get("partial_content") or "")
        decoded_text_decision = _parse_strict_json_object(raw_text_for_native_mode)
        if isinstance(decoded_text_decision, dict):
            action = str(decoded_text_decision.get("action") or "").strip().lower()
            if action in {"final", "done", "complete", "completed", "block", "blocked", "need_user", "needs_user"}:
                decision = _normalize_terminal_planner_decision(decoded_text_decision)
                if planner_role_override:
                    decision["planner_role"] = planner_role_override.get("role")
                    decision["planner_role_override"] = planner_role_override
                decision.setdefault("raw_planner_text_preview", raw_text_for_native_mode[:2000])
                decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
                decision["native_tool_calls_seen"] = 0
                decision["native_tool_text_decision_allowed"] = action
                decision["allowed_tool_names"] = list(native_tool_names)
                if prompt_context_continuation_required:
                    decision["prompt_context_continuation_required"] = prompt_context_continuation_required
                if stream_meta:
                    decision["planner_stream_meta"] = stream_meta
                return decision
            if action == "tool":
                decision = normalize_planner_decision(raw_text_for_native_mode, goal, step, state)
                if planner_role_override:
                    decision["planner_role"] = planner_role_override.get("role")
                    decision["planner_role_override"] = planner_role_override
                decision.setdefault("raw_planner_text_preview", raw_text_for_native_mode[:2000])
                decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
                decision["native_tool_calls_seen"] = 0
                decision["allowed_tool_names"] = list(native_tool_names)
                decision["allowed_native_tool_names"] = list(native_tool_names)
                if prompt_context_continuation_required:
                    decision["prompt_context_continuation_required"] = prompt_context_continuation_required
                if stream_meta:
                    decision["planner_stream_meta"] = stream_meta
                return decision
        if raw_text_for_native_mode.strip() and not _looks_like_malformed_native_protocol(
            raw_text_for_native_mode
        ):
            decision = _native_plain_text_final_decision(
                raw_text_for_native_mode,
                native_tool_names=list(native_tool_names),
                prompt_context_continuation_required=prompt_context_continuation_required,
                stream_meta=stream_meta,
            )
            if planner_role_override:
                decision["planner_role"] = planner_role_override.get("role")
                decision["planner_role_override"] = planner_role_override
            return decision
        prompt_eval_count = 0
        try:
            prompt_eval_count = int(response.get("ollama_prompt_eval_count") or 0)
        except Exception:
            prompt_eval_count = 0
        token_reserve = _planner_token_generation_reserve(AGENTIC_PLANNER_NUM_CTX)
        token_headroom_low = bool(
            AGENTIC_PLANNER_NUM_CTX > 0
            and prompt_eval_count > 0
            and token_reserve > 0
            and prompt_eval_count >= max(0, AGENTIC_PLANNER_NUM_CTX - token_reserve)
        )
        prompt_over_headroom_for_native = (
            bool(prompt_budget.get("over_generation_headroom_budget"))
            if isinstance(prompt_budget, dict)
            else False
        )
        if (
            isinstance(prompt_budget, dict)
            and AGENTIC_PLANNER_NATIVE_TOOLS
            and int(prompt_budget.get("native_history_reserve_chars") or 0) > 0
        ):
            prompt_over_headroom_for_native = bool(
                prompt_budget.get("over_generation_headroom_without_native_history_reserve")
            )
        if (
            (AGENTIC_PLANNER_NUM_CTX > 0 and prompt_eval_count >= AGENTIC_PLANNER_NUM_CTX)
            or token_headroom_low
            or prompt_over_headroom_for_native
            or (
                isinstance(prompt_budget, dict)
                and bool(prompt_budget.get("over_generation_headroom_with_history_messages"))
            )
        ):
            return {
                "action": "block",
                "reason": "planner_prompt_no_generation_headroom",
                "blocked_by": "planner_prompt_no_generation_headroom",
                "final_answer": (
                    "Planner native tool mode returned no tool call, but the prompt had no "
                    "safe generation headroom. This is a controller prompt-pack issue, not "
                    "a native tool-call violation."
                ),
                "raw_planner_text": raw_text_for_native_mode[:12000],
                "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
                "native_tool_calls_seen": 0,
                "controller_synthesized_protocol_block": True,
                "prompt_budget_report": prompt_budget,
                "prompt_token_headroom": {
                    "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
                    "ollama_prompt_eval_count": prompt_eval_count,
                    "generation_token_reserve": token_reserve,
                    "headroom_tokens": (
                        AGENTIC_PLANNER_NUM_CTX - prompt_eval_count
                        if AGENTIC_PLANNER_NUM_CTX > 0 and prompt_eval_count > 0
                        else None
                    ),
                    "classification": (
                        "planner_prompt_token_headroom_low"
                        if token_headroom_low
                        else "planner_prompt_no_generation_headroom"
                    ),
                },
                **({"planner_stream_meta": stream_meta} if stream_meta else {}),
            }
        if not native_tools_schema:
            return {
                "action": "block",
                "reason": "planner_final_required_empty_output",
                "final_answer": (
                    "Planner had no native tools in this turn because the evidence contract "
                    "required a final answer, but Ollama returned no usable terminal text."
                ),
                "raw_planner_text": raw_text_for_native_mode[:12000],
                "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
                "native_tool_calls_seen": 0,
                "controller_synthesized_protocol_block": True,
                "prompt_budget_report": prompt_budget,
                **({"planner_stream_meta": stream_meta} if stream_meta else {}),
            }
        if raw_text_for_native_mode.strip():
            # Try to parse raw text as a normal planner decision before blocking
            plain_text_decision = normalize_planner_decision(
                raw_text_for_native_mode,
                goal,
                step,
                state,
            )
            if plain_text_decision and isinstance(plain_text_decision, dict):
                action = str(plain_text_decision.get("action") or "").strip().lower()
                if action in {"final", "done", "complete", "completed", "block", "blocked", "need_user", "needs_user", "tool"}:
                    plain_text_decision.setdefault("raw_planner_text_preview", raw_text_for_native_mode[:2000])
                    plain_text_decision["planner_native_tools_enabled"] = bool(AGENTIC_PLANNER_NATIVE_TOOLS)
                    plain_text_decision["native_tool_calls_seen"] = 0
                    plain_text_decision["allowed_tool_names"] = list(native_tool_names)
                    if prompt_context_continuation_required:
                        plain_text_decision["prompt_context_continuation_required"] = prompt_context_continuation_required
                    if stream_meta:
                        plain_text_decision["planner_stream_meta"] = stream_meta
                    return plain_text_decision
            return {
                "action": "block",
                "reason": "planner_native_mode_non_json_output",
                "final_answer": (
                    "Planner native tool mode received protocol-shaped text, but it was neither "
                    "message.tool_calls nor a valid terminal JSON object. Plain terminal prose "
                    "was attempted as fallback decision; failed to extract valid action."
                ),
                "raw_planner_text": raw_text_for_native_mode[:12000],
                "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
                "native_tool_calls_seen": 0,
                "controller_synthesized_protocol_block": True,
                **({"planner_stream_meta": stream_meta} if stream_meta else {}),
            }
        return {
            "action": "block",
            "reason": "planner_native_tool_call_required",
            "final_answer": (
                "Planner native tool mode is required for tool execution, but Ollama "
                "did not return message.tool_calls. JSON-text tool fallback was not used."
            ),
            "raw_planner_text": raw_text_for_native_mode[:12000],
            "planner_native_tools_enabled": bool(AGENTIC_PLANNER_NATIVE_TOOLS),
            "native_tool_calls_seen": 0,
            "controller_synthesized_protocol_block": True,
            **({"planner_stream_meta": stream_meta} if stream_meta else {}),
        }
    # --- degenerate output ---
    if response.get("planner_degenerate_output"):
        return _degenerate_output_block_decision(response, stream_path, stream_meta=stream_meta)
    # --- timeout: surface, do not force a fallback decision ---
    if response.get("backend_timeout"):
        stream_timeout_seconds = int(response.get("timeout_seconds") or planner_stream_timeout_seconds)
        append_agent_event(
            job_id,
            "planner_timeout",
            f"Timeout after {stream_timeout_seconds}s; no forced retry/fallback.",
            {
                "error": response.get("error"),
                "partial_content_chars": len(str(response.get("partial_content") or "")),
                "stream_path": str(stream_path),
            },
            step=step,
        )
        partial = str(response.get("partial_content") or "")
        return {
            "action": "block",
            "reason": "planner_timeout_non_json_output",
            "final_answer": (
                "Planner 30B timed out. No forced retry or controller fallback was executed. "
                "Plain text partial output must be retried by the planner, not repaired by GPU0. "
                f"Partial stream chars={len(partial)}. Stream artifact={stream_path}."
            ),
            "raw_planner_text": partial[:12000],
        }
    if response.get("backend_unreachable") or response.get("backend_timeout"):
        return {
            "action": "block",
            "reason": "planner backend error",
            "final_answer": f"Planner 30B non raggiungibile: {response.get('error')}.",
        }
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    raw_text = str(message.get("content") or response.get("response") or "")
    if planner_done_token(raw_text):
        if goal_requires_code_product_report(goal):
            successful_code_edit_proposals = deps["successful_code_edit_proposals"]
            has_code_product_candidate = bool(successful_code_edit_proposals(history))
        else:
            has_code_product_candidate = True
        if not has_code_product_candidate:
            return {
                "action": "block",
                "reason": "planner done token without required code product candidate",
                "final_answer": (
                    "Il planner ha emesso un token di completamento senza JSON, "
                    "ma il goal richiedeva un code product/diff e manca repo_propose_code_edit."
                ),
            }
        apply_contract = (
            evidence_contract.get("apply_write_contract")
            if isinstance(evidence_contract.get("apply_write_contract"), dict)
            else {}
        )
        apply_required = bool(evidence_contract.get("goal_requests_apply")) or bool(apply_contract.get("required"))
        apply_patch_applied = bool(apply_contract.get("patch_applied")) or history_has_tool(history, "repo_apply_patch")
        if apply_required and not apply_patch_applied:
            return {
                "action": "block",
                "reason": "planner done token without applying requested patch",
                "final_answer": (
                    "Il planner ha emesso un token di completamento senza JSON, "
                    "ma il goal richiedeva una patch non eseguita."
                ),
            }
        return {
            "action": "final",
            "final_answer": (
                f"Il planner ha emesso un token di completamento ({raw_text.strip()!r}). "
                "3572 ha chiuso il job usando la history degli artifact."
            ),
            "history_artifacts": summarize_history_artifacts(history),
        }
    decision = normalize_planner_decision(raw_text, goal, step, state)
    decision.setdefault("raw_planner_text_preview", raw_text[:2000])
    decision["allowed_tool_names"] = list(native_tool_names)
    if prompt_context_continuation_required:
        decision["prompt_context_continuation_required"] = prompt_context_continuation_required
    if stream_meta:
        decision["planner_stream_meta"] = stream_meta
    return decision