"""Multi-step planner loop owner."""

from __future__ import annotations

import itertools
import traceback
from typing import Any, Mapping

from .state import PlannerLoopState
from ..tool_surface.batch_contract import canonical_batch_args as _canonical_batch_args
from ..tool_surface.batch_contract import canonical_batch_call_key


def _dict_field(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _list_field(mapping: Mapping[str, Any], key: str) -> list[Any]:
    value = mapping.get(key)
    return list(value) if isinstance(value, list) else []


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
    planner_cuda_rewrite_guard_for_validation = deps["planner_cuda_rewrite_guard_for_validation"]
    planner_cuda_rewrite_target = deps["planner_cuda_rewrite_target"]
    _planner_incomprehensible_retry_count = deps["planner_incomprehensible_retry_count"]
    _planner_memory_false_unavailable_claim = deps["planner_memory_false_unavailable_claim"]
    _raw_planner_text_classification = deps["raw_planner_text_classification"]
    _should_attempt_vulkan_repair = deps["should_attempt_vulkan_repair"]
    _should_retry_incomprehensible_planner_output = deps["should_retry_incomprehensible_planner_output"]
    _tool_cache_hit = deps["tool_cache_hit"]
    _tool_cache_key = deps["tool_cache_key"]
    _write_loop_turn_memory = deps["write_loop_turn_memory"]
    agent_job_root = deps["agent_job_root"]
    append_agent_event = deps["append_agent_event"]
    build_runtime_debug_packet = deps["build_runtime_debug_packet"]
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

    from ...tool_dispatch import dispatch_tool  # noqa
    from ...tool_contract import normalize_tool_name, sanitize_tool_args  # noqa

    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    root = agent_job_root(job_id)
    max_steps = max(1, min(int(state.get("max_steps") or AGENT_DEFAULT_MAX_STEPS), AGENT_MAX_STEPS))
    support_subturns_used = 0
    support_semantic_turns_used = 0
    support_semantic_steps_marked: set[int] = set()
    support_subturn_tools = frozenset({
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
    })
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

    def support_subturn_tool(tool: str) -> bool:
        return normalize_tool_name(tool) in support_subturn_tools

    def support_subturn_decision(planner_decision: dict[str, Any]) -> bool:
        if str(planner_decision.get("action") or "").strip().lower() != "tool":
            return False
        return support_subturn_tool(str(planner_decision.get("tool") or ""))

    def semantic_step_for_physical_step(step_number: int) -> int:
        physical_step = max(1, int(step_number))
        counted_support_turns = support_semantic_turns_used
        if physical_step in support_semantic_steps_marked:
            counted_support_turns = max(0, counted_support_turns - 1)
        return max(1, physical_step - counted_support_turns)

    def mark_support_subturn(row: dict[str, Any], *, semantic_step: int) -> None:
        nonlocal support_semantic_turns_used, support_subturns_used
        support_subturns_used += 1
        try:
            physical_step = int(row.get("step") or 0)
        except (TypeError, ValueError):
            physical_step = 0
        if physical_step > 0 and physical_step not in support_semantic_steps_marked:
            support_semantic_steps_marked.add(physical_step)
            support_semantic_turns_used += 1
        row["support_subturn"] = True
        row["semantic_step"] = semantic_step
        result = row.get("tool_result")
        if isinstance(result, dict):
            result["support_subturn"] = True
            result["semantic_step"] = semantic_step
            result["support_subturn_index"] = support_subturns_used
            result["support_semantic_turns_used"] = support_semantic_turns_used
        state["support_subturns_used"] = support_subturns_used
        state["support_semantic_turns_used"] = support_semantic_turns_used

    def planner_step_budget_guidance(step_number: int) -> dict[str, Any]:
        remaining_steps = max(0, max_steps - int(step_number) + 1)
        if remaining_steps <= 0:
            return {}
        if remaining_steps == 1:
            mode = "force_terminal_decision"
        elif remaining_steps == 2:
            mode = "prepare_terminal_decision"
        else:
            return {}
        return {
            "schema": "planner_step_budget_guidance.v1",
            "mode": mode,
            "current_step": int(step_number),
            "max_steps": int(max_steps),
            "remaining_steps": int(remaining_steps),
            "source": "AICARMINE_AGENT_MAX_STEPS",
            "controller_does_not_auto_final": True,
        }

    def force_terminal_decision_active() -> bool:
        guidance = state.get("planner_step_budget_guidance")
        return (
            isinstance(guidance, dict)
            and str(guidance.get("mode") or "") == "force_terminal_decision"
        )

    def runtime_debug_packet(
        *,
        step_number: int,
        phase: str,
        planner_decision: dict[str, Any],
        validation: dict[str, Any] | None = None,
        evidence_contract: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        contract = evidence_contract
        if contract is None and isinstance(validation, dict):
            maybe_contract = validation.get("evidence_contract")
            contract = maybe_contract if isinstance(maybe_contract, dict) else {}
        return build_runtime_debug_packet(
            job_id=job_id,
            step=step_number,
            phase=phase,
            goal=str(state.get("goal") or ""),
            decision=planner_decision,
            validator_result=validation,
            evidence_contract=contract or {},
            extra=extra,
        )

    def persist_loop_turn_memory(row: dict[str, Any]) -> None:
        state["controller_loop_turn_memory_last_write"] = _write_loop_turn_memory(
            job_id,
            state,
            row,
            root,
            history,
        )

    def append_cached_tool_result(step_number: int, planner_decision: dict[str, Any], cached: dict[str, Any]) -> None:
        cached_result = _dict_field(cached, "result")
        support_subturn = support_subturn_decision(planner_decision)
        semantic_step = semantic_step_for_physical_step(step_number)
        if support_subturn:
            cached_result["support_subturn"] = True
            cached_result["semantic_step"] = semantic_step
        append_agent_event(
            job_id,
            "tool_cache_hit",
            f"{cached.get('tool')} reused cached intra-job result.",
            {
                "tool": cached.get("tool"),
                "cache_key": cached.get("cache_key"),
                "cached_from_step": cached_result.get("cached_from_step"),
                "cached_from_artifact": cached_result.get("cached_from_artifact"),
                **({"support_subturn": True, "semantic_step": semantic_step} if support_subturn else {}),
            },
            step=step_number,
        )
        row = {
            "step": step_number,
            "decision": {k: v for k, v in planner_decision.items() if k != "raw_planner_text_preview"},
            "tool_result": cached_result,
        }
        if support_subturn:
            mark_support_subturn(row, semantic_step=semantic_step)
        loop_state.append_history_row(row)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def successful_prior_tool_results_for_feedback(
        tool: str,
        internal_args: dict[str, Any],
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        wanted_tool = normalize_tool_name(tool)
        wanted_cache_key = _tool_cache_key(wanted_tool, internal_args)
        rows: list[dict[str, Any]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            result = _dict_field(item, "tool_result")
            decision = _dict_field(item, "decision")
            result_tool = normalize_tool_name(str(result.get("tool") or decision.get("tool") or ""))
            if result_tool != wanted_tool or result.get("ok") is False:
                continue
            decision_args = _dict_field(decision, "arguments")
            try:
                comparable_args = sanitize_tool_args(
                    wanted_tool,
                    dict(decision_args),
                    original_args,
                    public_tool_name,
                )
            except Exception:
                comparable_args = dict(decision_args)
            if wanted_cache_key and _tool_cache_key(wanted_tool, comparable_args) != wanted_cache_key:
                continue
            digest: dict[str, Any] = {
                "step": item.get("step"),
                "tool": wanted_tool,
                "ok": result.get("ok", True),
            }
            for key in (
                "summary", "count", "items_total", "dry_run", "changed",
                "deleted_count", "success_count", "failed_count", "all_ok",
                "status", "mode",
            ):
                value = result.get(key)
                if value not in (None, "", [], {}):
                    digest[key] = value
            if result.get("artifact"):
                digest["artifact_available"] = True
            rows.append(digest)
        return rows[-max(1, int(limit or 1)):]

    def _coverage_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
        contract = contract if isinstance(contract, dict) else {}
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            return coverage
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        coverage = final_contract.get("minimum_read_coverage")
        return coverage if isinstance(coverage, dict) else {}

    def _coverage_satisfied(contract: dict[str, Any] | None) -> bool:
        contract = contract if isinstance(contract, dict) else {}
        coverage = _coverage_contract(contract)
        if coverage:
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True

    def _missing_owner_paths(contract: dict[str, Any] | None) -> list[str]:
        contract = contract if isinstance(contract, dict) else {}
        coverage = _coverage_contract(contract)
        raw = coverage.get("missing_owner_paths") if coverage else contract.get("missing_owner_paths")
        return [str(path) for path in raw] if isinstance(raw, list) else []

    def enrich_repeated_tool_guard_feedback(
        guard_result: dict[str, Any],
        planner_decision: dict[str, Any],
        validation: dict[str, Any],
    ) -> None:
        violations = _list_field(validation, "violations")
        if "repeated_same_tool_arguments_without_progress" not in {str(item) for item in violations}:
            return
        tool = normalize_tool_name(str(planner_decision.get("tool") or ""))
        if not tool:
            return
        raw_args = _dict_field(planner_decision, "arguments")
        internal_args = sanitize_tool_args(tool, dict(raw_args), original_args, public_tool_name)
        prior_results = successful_prior_tool_results_for_feedback(tool, internal_args)
        evidence_contract = guard_result.get("evidence_contract")
        if isinstance(evidence_contract, dict):
            required = _dict_field(evidence_contract, "required_next_tool_call")
            if required.get("tool") == "planner_scratchpad_read":
                next_instruction = str(
                    evidence_contract.get("required_next_progress")
                    or required.get("reason")
                    or "Consume the required planner_scratchpad_read continuation before final/block."
                )
                guard_result["next_instruction"] = next_instruction
                guard_result["required_next_progress"] = next_instruction
                guard_result["planner_may_choose_final"] = False
                evidence_contract["required_next_progress"] = next_instruction
                evidence_contract["planner_may_choose_final"] = False
                operational = evidence_contract.get("operational_notes")
                operational = operational if isinstance(operational, dict) else {}
                operational["next_instruction"] = next_instruction
                evidence_contract["operational_notes"] = operational
                return
            if not _coverage_satisfied(evidence_contract):
                missing_paths = _missing_owner_paths(evidence_contract)
                next_instruction = (
                    "coverage_required_after_repeated_tool_result: minimum_read_coverage.coverage_satisfied=false. "
                    "Do not final from the repeated tool result. Choose a different selective evidence-bound "
                    f"read/search for missing_owner_paths {missing_paths[:12]}, or return a typed block."
                )
                guard_result["next_instruction"] = next_instruction
                guard_result["required_next_progress"] = "coverage_required_after_repeated_tool_result"
                guard_result["planner_may_choose_final"] = False
                guard_result["coverage_satisfied"] = False
                guard_result["missing_owner_paths"] = missing_paths
                evidence_contract["required_next_progress"] = next_instruction
                evidence_contract["planner_may_choose_final"] = False
                final_contract = (
                    evidence_contract.get("finalization_contract")
                    if isinstance(evidence_contract.get("finalization_contract"), dict)
                    else {}
                )
                final_contract["final_allowed"] = False
                final_contract["planner_may_choose_final"] = False
                final_contract["coverage_satisfied"] = False
                final_contract["missing_owner_paths"] = missing_paths
                evidence_contract["finalization_contract"] = final_contract
                operational = evidence_contract.get("operational_notes")
                operational = operational if isinstance(operational, dict) else {}
                operational["next_instruction"] = next_instruction
                evidence_contract["operational_notes"] = operational
                return
        next_instruction = (
            f"Do not call {tool} again with the same arguments. Use the successful "
            "prior tool result evidence already present in history to return action=final, "
            "or choose a different tool only if it adds new evidence required by the user."
        )
        guard_result["next_instruction"] = next_instruction
        guard_result["required_next_progress"] = "final_from_existing_tool_result_or_different_new_evidence"
        guard_result["planner_may_choose_final"] = True
        if prior_results:
            guard_result["successful_prior_tool_results"] = prior_results
        if isinstance(evidence_contract, dict):
            evidence_contract["required_next_progress"] = guard_result["required_next_progress"]
            evidence_contract["planner_may_choose_final"] = True
            operational = evidence_contract.get("operational_notes")
            operational = operational if isinstance(operational, dict) else {}
            operational["next_instruction"] = next_instruction
            evidence_contract["operational_notes"] = operational

    def append_repeat_guard_result(
        step_number: int,
        planner_decision: dict[str, Any],
        tool: str,
        internal_args: dict[str, Any],
    ) -> None:
        support_subturn = support_subturn_decision(planner_decision)
        semantic_step = semantic_step_for_physical_step(step_number)
        validation_repeat = {
            "ok": False,
            "violations": ["repeated_same_tool_arguments_without_progress"],
            "evidence_contract": planner_evidence_contract(str(state.get("goal") or ""), history),
        }
        guard_result = controller_guard_result_for_validation(
            validation_repeat,
            planner_decision,
            job_id=job_id,
            step=step_number,
            goal=str(state.get("goal") or ""),
        )
        guard_result["guard_type"] = "repeat_guard"
        guard_result["summary"] = "repeated_same_tool_arguments_without_progress"
        guard_result["rejected_decision"] = {
            "action": planner_decision.get("action"),
            "tool": tool,
            "arguments": internal_args,
            "reason": planner_decision.get("reason"),
        }
        if support_subturn:
            guard_result["support_subturn"] = True
            guard_result["semantic_step"] = semantic_step
            guard_result["support_subturn_index"] = support_subturns_used + 1
        enrich_repeated_tool_guard_feedback(guard_result, planner_decision, validation_repeat)
        append_agent_event(job_id, "planner_decision_rejected", guard_result["summary"], guard_result, step=step_number)
        row = {
            "step": step_number,
            "decision": {"action": "continue_required", "reason": "repeat guard rejected planner proposal"},
            "tool_result": guard_result,
        }
        if support_subturn:
            mark_support_subturn(row, semantic_step=semantic_step)
        loop_state.append_history_row(row)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def execute_validated_tool_decision(step_number: int, planner_decision: dict[str, Any], substep: int | None = None) -> dict[str, Any] | None:
        tool = normalize_tool_name(str(planner_decision.get("tool") or ""))
        args = _dict_field(planner_decision, "arguments")
        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
        is_support_subturn = support_subturn_decision(planner_decision)
        semantic_step = semantic_step_for_physical_step(step_number)
        if repeated_tool_call_count(history, tool, internal_args) >= 2:
            append_repeat_guard_result(step_number, planner_decision, tool, internal_args)
            return None
        cache_key = _tool_cache_key(tool, internal_args)
        if cache_key:
            hit = _tool_cache_hit(history, tool, internal_args)
            if hit:
                cached_result = _cached_tool_result(hit, cache_key)
                append_cached_tool_result(step_number, planner_decision, {
                    "tool": tool,
                    "arguments": internal_args,
                    "cache_key": cache_key,
                    "result": cached_result,
                })
                return None

        allowed, block_reason = _agentic_tool_allowed(tool, internal_args, approval_mode)
        if not allowed:
            append_agent_event(job_id, "tool_blocked", block_reason, {"tool": tool}, step=step_number)
            return finalize_agentic_job(
                job_id, state, "blocked_needs_consent", block_reason,
                {"history": history, "blocked_tool": tool},
            )

        event_payload = {"tool": tool, "arguments": internal_args}
        if is_support_subturn:
            event_payload["support_subturn"] = True
            event_payload["semantic_step"] = semantic_step
        if substep is not None:
            event_payload["substep"] = substep
        state["status_message"] = f"executing {tool}"
        write_agent_job_state(state)
        append_agent_event(job_id, "tool_start", f"Executing {tool}", event_payload, step=step_number)

        result = dispatch_tool(
            tool, internal_args, root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        suffix = f"-{substep:02d}" if substep is not None else ""
        tool_result_path = root / "tool-results" / f"step-{step_number:03d}{suffix}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {})
        compact_result["artifact"] = str(tool_result_path)
        if is_support_subturn:
            compact_result["support_subturn"] = True
            compact_result["semantic_step"] = semantic_step
        if substep is not None:
            compact_result["substep"] = substep
        if cache_key and bool(compact_result.get("ok")):
            compact_result["cache_key"] = cache_key
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}", compact_result, step=step_number)
        row = {
            "step": step_number,
            "decision": {k: v for k, v in planner_decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        }
        if substep is not None:
            row["substep"] = substep
        if is_support_subturn:
            mark_support_subturn(row, semantic_step=semantic_step)
        loop_state.append_history_row(row, update_evidence=False)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)
        return None

    def match_micro_batch_action(
        micro_batch_contract: dict[str, Any],
        *,
        tool: str,
        internal_args: dict[str, Any],
    ) -> dict[str, Any]:
        actions = micro_batch_contract.get("allowed_batch_actions")
        if not isinstance(actions, list):
            return {}
        wanted_tool = normalize_tool_name(str(tool or ""))
        wanted_args_key = _canonical_batch_args(internal_args)
        for action in actions:
            if not isinstance(action, dict):
                continue
            candidate_tool = normalize_tool_name(str(action.get("tool") or ""))
            if candidate_tool != wanted_tool:
                continue
            candidate_raw_args = (
                action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            )
            candidate_args = sanitize_tool_args(
                candidate_tool,
                dict(candidate_raw_args),
                original_args,
                public_tool_name,
            )
            if _canonical_batch_args(candidate_args) == wanted_args_key:
                return action
        return {}

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
        persist_loop_turn_memory(row)
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
            "status": "failed",
            "source": "planner",
            "reason": "query_plan_unhandled_exception",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "semantic_intent_required": True,
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
            row = {
                "step": 0,
                "decision": {
                    "action": "block",
                    "reason": "preplanner_semantic_intent_unusable",
                },
                "tool_result": {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "preplanner_semantic_intent_unusable",
                    "summary": "preplanner_semantic_intent_unusable",
                    "preplanner_query_plan": preplanner_query_plan,
                },
            }
            loop_state.append_history_row(row)
            persist_loop_turn_memory(row)
            write_agent_job_state(state)
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                (
                    "preplanner_semantic_intent_unusable: the controlled preplanner did not "
                    "return a usable semantic_intent after retry. The controller did not fall "
                    "back to regex/static goal routing."
                ),
                {
                    "history": history,
                    "blocked_by": "preplanner_semantic_intent_unusable",
                    "preplanner_query_plan": preplanner_query_plan,
                },
            )

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
        ranked_preseed_success = bool(
            preplanner_compact.get("ok")
            and len(ranked_paths) >= 2
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
        semantic_step = semantic_step_for_physical_step(step)
        if semantic_step > max_steps:
            break
        state = load_agent_job_state(job_id) or state
        if str(state.get("status") or "") == "cancel_requested":
            return finalize_agentic_job(job_id, state, "cancelled", "Job cancelled.", {"history": history})

        goal_text = str(state.get("goal") or "")
        step_budget_guidance = planner_step_budget_guidance(semantic_step)
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
        state.update({
            "current_step": step,
            "semantic_step": semantic_step,
            "support_subturns_used": support_subturns_used,
            "support_semantic_turns_used": support_semantic_turns_used,
            "status_message": "planning next action",
            "evidence_contract": contract_snapshot,
            "planner_memory_surface": memory_snapshot,
            "working_memory_for_30b": {
                "schema": "agentic_loop_operational_memory.v1",
                "goal": state.get("goal"),
                "physical_step": step,
                "semantic_step": semantic_step,
                "history_count": len(history),
                "successful_repo_read_paths": contract_snapshot.get("successful_repo_read_paths", []),
                "latest_repo_list_path": (contract_snapshot.get("repo_list_files_evidence") or [{}])[-1].get("path") if contract_snapshot.get("repo_list_files_evidence") else None,
                "candidate_next_actions": contract_snapshot.get("candidate_next_actions", []),
                "file_memory": contract_snapshot.get("file_memory", []),
                "operational_notes": contract_snapshot.get("operational_notes", {}),
                "planner_memory": memory_snapshot,
                "finalization_contract": contract_snapshot.get("finalization_contract", {}),
                "codex_quality": contract_snapshot.get("agentic_codex_quality", {}),
                "rejections_tail": contract_snapshot.get("validation_rejections_tail", []),
                "planner_step_budget_guidance": step_budget_guidance,
            },
        })
        write_agent_job_state(state)

        # The planner must remain the decision-maker. 3572 may validate or reject
        # the proposal, but must not synthesize hidden tool calls such as an
        # automatic repo_read after repo_list_files.
        decision = planner_decision(job_id, state, step, history)

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
        if _planner_memory_false_unavailable_claim(memory_claim_text, planner_memory_snapshot):
            retry_limit = (
                AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES
                if semantic_step < max_steps else 0
            )
            retry_count = _planner_incomprehensible_retry_count(history)
            if int(retry_limit or 0) > 0 and retry_count < int(retry_limit):
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_memory_false_unavailable_claim",
                    "summary": "planner_memory_available_but_planner_claimed_unavailable",
                    "classification": "planner_memory_false_unavailable_claim_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "raw_planner_text_preview": memory_claim_text[:4000],
                    "planner_memory": {
                        "available": True,
                        "record_count": planner_memory_snapshot.get("record_count", 0),
                        "source": planner_memory_snapshot.get("source"),
                    },
                    "next_instruction": (
                        "planner_memory is available; do not claim long-term memory is unavailable; "
                        "repeat as one pure JSON object; use/cite intrinsic_context and planner_memory first; "
                        "call runtime_sqlite_memory_search only for a named selective gap"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                    "runtime_debug_packet": runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        evidence_contract=contract_snapshot,
                        extra={"guard_type": "planner_memory_false_unavailable_claim"},
                    ),
                }
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            return finalize_agentic_job(
                job_id,
                state,
                "blocked_needs_attention",
                (
                    "Planner claimed long-term memory is unavailable even though "
                    "the controller injected planner_memory.available=true."
                ),
                {
                    "history": history,
                    "blocked_by": "planner_memory_false_unavailable_claim",
                    "planner_decision": decision,
                    "agent_flow_diagnostics": _agent_flow_diagnostics(
                        str(state.get("goal") or ""),
                        history,
                        planner_memory_snapshot,
                    ),
                },
            )

        if (
            str(decision.get("action") or "").strip().lower() == "tool_batch"
            and not force_terminal_decision_active()
        ):
            calls = _list_field(decision, "tool_calls")
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
                    "runtime_debug_packet": runtime_debug_packet(
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
                    "runtime_debug_packet": runtime_debug_packet(
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
                    "runtime_debug_packet": runtime_debug_packet(
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
                            "runtime_debug_packet": runtime_debug_packet(
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
                            "runtime_debug_packet": runtime_debug_packet(
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
                    matched_action = match_micro_batch_action(
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
                            "runtime_debug_packet": runtime_debug_packet(
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
                            "runtime_debug_packet": runtime_debug_packet(
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
                            "runtime_debug_packet": runtime_debug_packet(
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
                                batch_guard = {
                                    "tool": "controller_guard",
                                    "ok": True,
                                    "guard_type": "native_tool_batch_validation",
                                    "summary": "vulkan_repair_tool_decision_disallowed_in_native_mode",
                                    "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                                    "rejected_decision": call_decision,
                                    "runtime_debug_packet": runtime_debug_packet(
                                        step_number=step,
                                        phase="CONTROLLER_GUARD",
                                        planner_decision=call_decision,
                                        validation={
                                            "ok": False,
                                            "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                                            "evidence_contract": validation_i.get("evidence_contract"),
                                        },
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
                persist_loop_turn_memory(row)
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
                    terminal = execute_validated_tool_decision(step, batch_decision, substep=idx)
                    if terminal is not None:
                        return terminal
                continue

        validation = validate_planner_decision_against_evidence(
            str(state.get("goal") or ""), decision, history
        )
        if not validation.get("ok"):
            if force_terminal_decision_active():
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
                persist_loop_turn_memory(row)
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
            if support_subturn_decision(decision):
                rejection_signature = _controller_guard_rejection_signature(validation, decision)
                repeated_rejection_count = _controller_guard_rejection_signature_count(
                    history,
                    rejection_signature,
                )
                repeated_rejection_limit = max(1, int(retry_limit or 0))
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "support_subturn_validation_failed"
                guard_result["summary"] = "support_subturn_validation_failed"
                guard_result["support_subturn"] = True
                guard_result["semantic_step"] = semantic_step
                guard_result["support_subturn_index"] = support_subturns_used + 1
                guard_result["invalid_decision_signature"] = rejection_signature
                guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
                guard_result["retry_limit"] = repeated_rejection_limit
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
                mark_support_subturn(row, semantic_step=semantic_step)
                loop_state.append_history_row(row)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                if repeated_rejection_count >= repeated_rejection_limit:
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        (
                            "support_subturn_validation_failed_repeated: planner repeated the same "
                            "invalid support primitive after validator feedback."
                        ),
                        {
                            "history": history,
                            "blocked_by": "support_subturn_validation_failed_repeated",
                            "planner_decision": decision,
                            "validation": validation,
                            "semantic_step": semantic_step,
                            "support_subturns_used": support_subturns_used,
                            "support_semantic_turns_used": support_semantic_turns_used,
                            "invalid_decision_signature": rejection_signature,
                            "invalid_decision_repeat_count": repeated_rejection_count + 1,
                        },
                    )
                continue
            if "planner_native_tool_call_required" in validation_violations:
                prior_native_empty_guards = controller_guard_count(
                    history,
                    "planner_native_tool_call_required",
                )
                if prior_native_empty_guards >= int(retry_limit or 0):
                    return finalize_agentic_job(
                        job_id,
                        state,
                        "blocked_needs_attention",
                        (
                            "planner_native_tool_call_required_repeated: planner native tool mode "
                            "was active, tools were provided to Ollama, but the planner repeatedly "
                            "returned no message.tool_calls. Controller did not fall back to JSON-text "
                            "tool execution."
                        ),
                        {
                            "history": history,
                            "planner_decision": decision,
                            "blocked_by": "planner_native_tool_call_required_repeated",
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
                guard_result["guard_type"] = "planner_native_tool_call_required"
                guard_result["summary"] = "planner_native_tool_call_required"
                guard_result["retry_count"] = prior_native_empty_guards
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
                        "reason": "native planner emitted no message.tool_calls",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            if (
                _planner_memory_false_unavailable_claim(raw_planner_text, planner_memory_snapshot)
                and int(retry_limit or 0) > 0
                and _planner_incomprehensible_retry_count(history) < int(retry_limit)
            ):
                retry_count = _planner_incomprehensible_retry_count(history)
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_memory_false_unavailable_claim",
                    "summary": "planner_memory_available_but_planner_claimed_unavailable",
                    "classification": "plain_text_non_json_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "violations": validation.get("violations"),
                    "raw_planner_text_preview": raw_planner_text[:4000],
                    "planner_memory": {
                        "available": True,
                        "record_count": planner_memory_snapshot.get("record_count", 0),
                        "source": planner_memory_snapshot.get("source"),
                    },
                    "next_instruction": (
                        "planner_memory is available; do not claim long-term memory is unavailable; "
                        "repeat as one pure JSON object and either use planner_memory, call a memory tool, "
                        "or choose another evidence-bound action"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                    "evidence_contract": validation.get("evidence_contract"),
                    "runtime_debug_packet": runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        validation=validation,
                        extra={"guard_type": "planner_memory_false_unavailable_claim"},
                    ),
                }
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if _should_retry_incomprehensible_planner_output(
                decision, history, retry_limit
            ):
                output_classification = _raw_planner_text_classification(raw_planner_text)
                retry_count = _planner_incomprehensible_retry_count(history)
                guard_result = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "planner_retry_required",
                    "summary": "planner_output_incomprehensible_repeat_required",
                    "classification": f"{output_classification}_retryable",
                    "retry_count": retry_count,
                    "retry_limit": int(retry_limit or 0),
                    "violations": validation.get("violations"),
                    "raw_planner_text_preview": raw_planner_text[:4000],
                    "next_instruction": (
                        "repeat as one pure JSON object; no prose before or after; "
                        "choose from candidate_next_actions; do not answer unrelated "
                        "questions"
                    ),
                    "rejected_decision": {
                        k: decision.get(k)
                        for k in ("action", "tool", "arguments", "reason", "final_answer")
                        if decision.get(k) not in (None, "", [], {})
                    },
                    "evidence_contract": validation.get("evidence_contract"),
                    "runtime_debug_packet": runtime_debug_packet(
                        step_number=step,
                        phase="CONTROLLER_GUARD",
                        planner_decision=decision,
                        validation=validation,
                        extra={"guard_type": "planner_retry_required"},
                    ),
                }
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if "planner_repeated_invalid_code_product_decision" in {
                str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])
            }:
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "planner_repeated_invalid_code_product_decision"
                guard_result["summary"] = "planner_repeated_invalid_code_product_decision"
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                blocker_answer = (
                    "planner_repeated_invalid_code_product_decision: planner repeated the same invalid "
                    "repo_propose_code_edit placeholder/missing-payload decision after the validator "
                    "already required a route shift. Controller did not synthesize a patch or hidden tool call."
                )
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    blocker_answer,
                    {
                        "history": history,
                        "blocked_by": "planner_repeated_invalid_code_product_decision",
                        "planner_decision": decision,
                        "invalid_decision_signature": validation.get("invalid_decision_signature"),
                        "invalid_decision_repeat_count": validation.get("invalid_decision_repeat_count"),
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )

            rejection_signature = _controller_guard_rejection_signature(validation, decision)
            repeated_rejection_count = _controller_guard_rejection_signature_count(
                history,
                rejection_signature,
            )
            repeated_rejection_limit = max(1, int(retry_limit or 0))
            if repeated_rejection_count >= repeated_rejection_limit:
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["guard_type"] = "repeated_identical_planner_rejection"
                guard_result["summary"] = "repeated_identical_planner_rejection"
                guard_result["invalid_decision_signature"] = rejection_signature
                guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
                guard_result["retry_limit"] = repeated_rejection_limit
                enrich_repeated_tool_guard_feedback(guard_result, decision, validation)
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                return finalize_agentic_job(
                    job_id,
                    state,
                    "blocked_needs_attention",
                    (
                        "repeated_identical_planner_rejection: planner repeated the same "
                        "validator-rejected decision after controller feedback. Controller "
                        "stopped the loop and preserved available payloads instead of "
                        "consuming max_steps."
                    ),
                    {
                        "history": history,
                        "blocked_by": "repeated_identical_planner_rejection",
                        "planner_decision": decision,
                        "validation": validation,
                        "invalid_decision_signature": rejection_signature,
                        "invalid_decision_repeat_count": repeated_rejection_count + 1,
                        "agent_flow_diagnostics": _agent_flow_diagnostics(
                            str(state.get("goal") or ""),
                            history,
                            planner_memory_snapshot,
                        ),
                    },
                )

            rewrite_target = str(planner_cuda_rewrite_target(validation, decision) or "")
            if (
                rewrite_target
                and int(retry_limit or 0) > 0
                and repeated_rejection_count == 0
            ):
                guard_result = planner_cuda_rewrite_guard_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                guard_result["invalid_decision_signature"] = rejection_signature
                guard_result["invalid_decision_repeat_count"] = repeated_rejection_count + 1
                guard_result["retry_count"] = repeated_rejection_count
                guard_result["retry_limit"] = 1
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
                        "reason": f"planner CUDA rewrite required for rejected {rewrite_target} proposal",
                        "rejected_decision": {
                            k: decision.get(k)
                            for k in ("action", "tool", "arguments", "reason", "final_answer", "raw_planner_text")
                            if decision.get(k) not in (None, "", [], {})
                        },
                    },
                    "tool_result": guard_result,
                }
                loop_state.append_history_row(row)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if _is_unrecoverable_plain_text_planner_output(decision, history, retry_limit):
                final_answer = str(decision.get("final_answer") or decision.get("reason") or "")
                raw_text = str(decision.get("raw_planner_text") or "")
                output_classification = _raw_planner_text_classification(raw_text)
                repair_reason = f"{output_classification}_not_gpu0_repairable"
                if raw_text:
                    final_answer += (
                        "\n\nRaw planner output surfaced, first 4000 chars:\n"
                        + raw_text[:4000]
                    )
                append_agent_event(
                    job_id,
                    "planner_decision_rejected",
                    "planner_output_gpu1_retry_unrecoverable_no_gpu0_repair",
                    {
                        "classification": output_classification,
                        "retry_count": _planner_incomprehensible_retry_count(history),
                        "retry_limit": int(AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES or 0),
                        "raw_planner_text_preview": raw_text[:4000],
                        "vulkan_repair": {
                            "attempted": False,
                            "reason": repair_reason,
                        },
                    },
                    step=step,
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
                        "classification": f"planner_output_{output_classification}_unrecoverable",
                        "raw_planner_text": decision.get("raw_planner_text"),
                        "vulkan_repair": {
                            "attempted": False,
                            "reason": repair_reason,
                        },
                    },
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
                        "evidence_contract": validation.get("evidence_contract"),
                        "runtime_debug_packet": runtime_debug_packet(
                            step_number=step,
                            phase="CONTROLLER_GUARD",
                            planner_decision=decision,
                            validation=validation,
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
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                if repaired_validation.get("ok"):
                    decision = repaired_decision
                    validation = repaired_validation
                else:
                    continue
            else:
                guard_result = controller_guard_result_for_validation(
                    validation,
                    decision,
                    job_id=job_id,
                    step=step,
                    goal=str(state.get("goal") or ""),
                )
                if should_attempt_vulkan:
                    guard_result["vulkan_repair"] = {
                        k: repair_result.get(k)
                        for k in (
                            "ok", "error", "raw_text_preview", "raw_planner_text_preview",
                            "repair_cache_key", "repair_cache_hit", "cached_from_step",
                        )
                        if repair_result.get(k) not in (None, "", [], {})
                    }
                enrich_repeated_tool_guard_feedback(guard_result, decision, validation)
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
                persist_loop_turn_memory(row)
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
        is_support_subturn = support_subturn_decision(decision)
        if repeated_tool_call_count(history, tool, internal_args) >= 2:
            append_repeat_guard_result(step, decision, tool, internal_args)
            continue

        cache_key = _tool_cache_key(tool, internal_args)
        hit = _tool_cache_hit(history, tool, internal_args)
        if hit:
            effective_cache_key = cache_key or str(hit.get("cache_key") or "")
            append_cached_tool_result(
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
            mark_support_subturn(row, semantic_step=semantic_step)
        loop_state.append_history_row(row, update_evidence=False)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

        # No controller_auto_final here: the next planner step must inspect the
        # structured evidence and decide whether to continue, read more, or final.

    terminal_contract = planner_evidence_contract(str(state.get("goal") or ""), history)
    if not _coverage_satisfied(terminal_contract):
        missing_paths = _missing_owner_paths(terminal_contract)
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
