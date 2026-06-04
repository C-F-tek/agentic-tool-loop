"""Multi-step planner loop owner."""

from __future__ import annotations

import traceback
from typing import Any, Mapping


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
    _controller_preseed_plan = deps["controller_preseed_plan"]
    _decision_memory_claim_text = deps["decision_memory_claim_text"]
    _decision_raw_planner_text = deps["decision_raw_planner_text"]
    _initial_orientation_surface_from_history = deps["initial_orientation_surface_from_history"]
    _is_unrecoverable_plain_text_planner_output = deps["is_unrecoverable_plain_text_planner_output"]
    _native_required_repaired_tool_decision_disallowed = deps["native_required_repaired_tool_decision_disallowed"]
    _normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
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
    compact_tool_result_for_planner = deps["compact_tool_result_for_planner"]
    controller_guard_count = deps["controller_guard_count"]
    controller_guard_result_for_validation = deps["controller_guard_result_for_validation"]
    finalize_agentic_job = deps["finalize_agentic_job"]
    goal_has_write_intent = deps["goal_has_write_intent"]
    history_has_tool = deps["history_has_tool"]
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
    approval_mode = str(state.get("approval_mode") or "safe_write_lab")
    original_args = dict(state.get("original_args") or {})
    public_tool_name = str(state.get("public_tool_name") or "vulkan_helper")
    history: list[dict[str, Any]] = []

    def persist_loop_turn_memory(row: dict[str, Any]) -> None:
        state["controller_loop_turn_memory_last_write"] = _write_loop_turn_memory(
            job_id,
            state,
            row,
            root,
            history,
        )

    def append_cached_tool_result(step_number: int, planner_decision: dict[str, Any], cached: dict[str, Any]) -> None:
        cached_result = cached.get("result") if isinstance(cached.get("result"), dict) else {}
        append_agent_event(
            job_id,
            "tool_cache_hit",
            f"{cached.get('tool')} reused cached intra-job result.",
            {
                "tool": cached.get("tool"),
                "cache_key": cached.get("cache_key"),
                "cached_from_step": cached_result.get("cached_from_step"),
                "cached_from_artifact": cached_result.get("cached_from_artifact"),
            },
            step=step_number,
        )
        row = {
            "step": step_number,
            "decision": {k: v for k, v in planner_decision.items() if k != "raw_planner_text_preview"},
            "tool_result": cached_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def append_repeat_guard_result(
        step_number: int,
        planner_decision: dict[str, Any],
        tool: str,
        internal_args: dict[str, Any],
    ) -> None:
        validation_repeat = {
            "ok": False,
            "violations": ["repeated_same_tool_arguments_without_progress"],
            "evidence_contract": planner_evidence_contract(str(state.get("goal") or ""), history),
        }
        guard_result = controller_guard_result_for_validation(validation_repeat, planner_decision)
        guard_result["guard_type"] = "repeat_guard"
        guard_result["summary"] = "repeated_same_tool_arguments_without_progress"
        guard_result["rejected_decision"] = {
            "action": planner_decision.get("action"),
            "tool": tool,
            "arguments": internal_args,
            "reason": planner_decision.get("reason"),
        }
        append_agent_event(job_id, "planner_decision_rejected", guard_result["summary"], guard_result, step=step_number)
        row = {
            "step": step_number,
            "decision": {"action": "continue_required", "reason": "repeat guard rejected planner proposal"},
            "tool_result": guard_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

    def execute_validated_tool_decision(step_number: int, planner_decision: dict[str, Any], substep: int | None = None) -> dict[str, Any] | None:
        tool = normalize_tool_name(str(planner_decision.get("tool") or ""))
        args = planner_decision.get("arguments") if isinstance(planner_decision.get("arguments"), dict) else {}
        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)
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
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)
        return None

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
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
        history.append(row)
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

    preseed_plan = _controller_preseed_plan(str(state.get("goal") or ""), original_args)
    if preseed_plan:
        preseed_index = 1
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

    for step in range(1, max_steps + 1):
        state = load_agent_job_state(job_id) or state
        if str(state.get("status") or "") == "cancel_requested":
            return finalize_agentic_job(job_id, state, "cancelled", "Job cancelled.", {"history": history})

        goal_text = str(state.get("goal") or "")
        contract_snapshot = planner_evidence_contract(goal_text, history)
        memory_snapshot = planner_memory_surface({
            "goal": goal_text,
            "limit": 12,
            "target_key": _controller_memory_target_key(goal_text, contract_snapshot),
        }, root)
        state.update({
            "current_step": step,
            "status_message": "planning next action",
            "evidence_contract": contract_snapshot,
            "planner_memory_surface": memory_snapshot,
            "working_memory_for_30b": {
                "schema": "agentic_loop_operational_memory.v1",
                "goal": state.get("goal"),
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
                if step < max_steps else 0
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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

        if str(decision.get("action") or "").strip().lower() == "tool_batch":
            calls = decision.get("tool_calls") if isinstance(decision.get("tool_calls"), list) else []
            batch_decisions: list[dict[str, Any]] = []
            batch_guard: dict[str, Any] | None = None
            if not calls:
                batch_guard = {
                    "tool": "controller_guard",
                    "ok": True,
                    "guard_type": "native_tool_batch_invalid",
                    "summary": "native_tool_batch_empty",
                    "violations": ["native_tool_batch_empty"],
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
                }
            else:
                for call in calls:
                    if not isinstance(call, dict):
                        continue
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
                    if isinstance(decision.get("prompt_context_continuation_required"), dict):
                        call_decision["prompt_context_continuation_required"] = decision["prompt_context_continuation_required"]
                    internal_args = sanitize_tool_args(
                        call_decision["tool"],
                        dict(call_decision["arguments"]),
                        original_args,
                        public_tool_name,
                    )
                    if not _tool_cache_key(call_decision["tool"], internal_args):
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_non_readonly",
                            "summary": "native_tool_batch_requires_readonly_tools_only",
                            "violations": ["native_tool_batch_non_readonly"],
                            "rejected_decision": call_decision,
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
                        batch_guard = controller_guard_result_for_validation(validation_i, call_decision)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
            elif batch_decisions:
                append_agent_event(
                    job_id,
                    "native_tool_batch_executed",
                    f"Executing native read-only tool batch. count={len(batch_decisions)}",
                    {"count": len(batch_decisions)},
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
            raw_planner_text = _decision_raw_planner_text(decision)
            retry_limit = (
                AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES
                if step < max_steps else 0
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
                guard_result = controller_guard_result_for_validation(validation, decision)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue

            if "planner_repeated_invalid_code_product_decision" in {
                str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])
            }:
                guard_result = controller_guard_result_for_validation(validation, decision)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
                guard_result = controller_guard_result_for_validation(validation, decision)
                guard_result["guard_type"] = "repeated_identical_planner_rejection"
                guard_result["summary"] = "repeated_identical_planner_rejection"
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
                        "reason": "planner repeated identical rejected decision",
                        "rejected_decision": guard_result.get("rejected_decision"),
                    },
                    "tool_result": guard_result,
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                if repaired_validation.get("ok"):
                    decision = repaired_decision
                    validation = repaired_validation
                else:
                    continue
            else:
                guard_result = controller_guard_result_for_validation(validation, decision)
                if should_attempt_vulkan:
                    guard_result["vulkan_repair"] = {
                        k: repair_result.get(k)
                        for k in (
                            "ok", "error", "raw_text_preview", "raw_planner_text_preview",
                            "repair_cache_key", "repair_cache_hit", "cached_from_step",
                        )
                        if repair_result.get(k) not in (None, "", [], {})
                    }
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
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                state["evidence_contract"] = planner_evidence_contract(str(state.get("goal") or ""), history)
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
            if goal_has_write_intent(state.get("goal") or "") and not history_has_tool(history, "repo_apply_patch"):
                row = {
                    "step": step,
                    "decision": {"action": "continue_required",
                                  "reason": "final rejected: patch requested but not applied"},
                    "tool_result": {
                        "tool": "controller_guard", "ok": True,
                        "summary": (
                            "The user requested a patch. You may not final yet. "
                            "Use repo_apply_patch if old_text/new_text are ready, "
                            "or repo_read to get old_text first."
                        ),
                    },
                }
                history.append(row)
                state["history"] = planner_history_ledger(history)
                state["history_count"] = len(history)
                persist_loop_turn_memory(row)
                write_agent_job_state(state)
                continue
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
        append_agent_event(job_id, "tool_start", f"Executing {tool}",
                            {"tool": tool, "arguments": internal_args}, step=step)

        result = dispatch_tool(
            tool, internal_args, root,
            allow_command=True,
            user_consent=str(original_args.get("user_consent") or state.get("user_consent") or ""),
        )
        tool_result_path = root / "tool-results" / f"step-{step:03d}-{tool}.json"
        write_json(tool_result_path, result)
        compact_result = compact_tool_result_for_planner(tool, result if isinstance(result, dict) else {})
        compact_result["artifact"] = str(tool_result_path)
        if cache_key and bool(compact_result.get("ok")):
            compact_result["cache_key"] = cache_key
        append_agent_event(job_id, "tool_result", f"{tool} ok={bool(result.get('ok'))}",
                            compact_result, step=step)

        row = {
            "step": step,
            "decision": {k: v for k, v in decision.items() if k != "raw_planner_text_preview"},
            "tool_result": compact_result,
        }
        history.append(row)
        state["history"] = planner_history_ledger(history)
        state["history_count"] = len(history)
        persist_loop_turn_memory(row)
        write_agent_job_state(state)

        # No controller_auto_final here: the next planner step must inspect the
        # structured evidence and decide whether to continue, read more, or final.

    return finalize_agentic_job(
        job_id, state, "max_steps_reached",
        f"Max steps reached ({max_steps}) before planner produced a final answer.",
        {"history": history},
    )
