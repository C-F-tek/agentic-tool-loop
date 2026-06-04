"""Structured terminal context builder returned to OpenWebUI."""

from __future__ import annotations

from typing import Any, Callable


JobRootForId = Callable[[str], Any]
ComposedAnswerLoader = Callable[[Any], dict[str, Any]]
HistoryToRows = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
HistoryToDict = Callable[[list[dict[str, Any]]], dict[str, Any]]
EvidenceContractBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
ResultToText = Callable[[dict[str, Any]], str]
ResultToDict = Callable[[dict[str, Any]], dict[str, Any]]
ValueCleaner = Callable[[Any], Any]


def build_tool_context_for_30b(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
    *,
    planner_model: str,
    planner_url: str,
    job_root_for_id: JobRootForId,
    planner_composed_answer: ComposedAnswerLoader,
    agent_flow_diagnostics: Callable[[str, list[dict[str, Any]], dict[str, Any] | None], dict[str, Any]],
    partial_products_for_30b: HistoryToRows,
    best_partial_product_for_30b: Callable[[list[dict[str, Any]]], dict[str, Any]],
    answer_for_openwebui: Callable[[str, str, dict[str, Any]], str],
    execution_evidence_digest_text: ResultToText,
    repo_read_content_views: HistoryToRows,
    next_action_for_openwebui: Callable[[str, dict[str, Any]], dict[str, Any]],
    initial_orientation_surface_from_history: Callable[[list[dict[str, Any]], list[Any]], dict[str, Any]],
    planner_decision_rows: HistoryToRows,
    validation_rejection_rows: HistoryToRows,
    executed_tool_rows: HistoryToRows,
    planner_turn_memory: Callable[[list[dict[str, Any]], dict[str, Any]], dict[str, Any]],
    compact_final_state_result: ResultToDict,
    public_tool_artifact_rows: HistoryToRows,
    public_tool_context_limits: HistoryToRows,
    planner_evidence_contract: EvidenceContractBuilder,
    planner_history_ledger: HistoryToRows,
    strip_public_local_references: ValueCleaner,
) -> dict[str, Any]:
    """Structured terminal context returned to OpenWebUI."""
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
    goal = str(state.get("goal") or "")
    planner_memory = state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else None
    diagnostics = agent_flow_diagnostics(goal, history, planner_memory)
    result = dict(result)
    partial_products = partial_products_for_30b(history)
    best_partial_product = best_partial_product_for_30b(history)
    if partial_products:
        result["partial_products_for_30b"] = partial_products
    if best_partial_product:
        result["best_partial_product_for_30b"] = best_partial_product
    controller_memory = state.get("controller_memory_last_write") if isinstance(state.get("controller_memory_last_write"), dict) else {}
    if controller_memory:
        diagnostics["controller_memory_records_written"] = 1 if controller_memory.get("ok") else 0
        diagnostics["controller_memory_target_key"] = controller_memory.get("target_key")
    result["agent_flow_diagnostics"] = diagnostics
    answer = answer_for_openwebui(status, final_summary, result)
    job_root = job_root_for_id(job_id)
    composed_answer = planner_composed_answer(job_root)
    if status == "completed" and composed_answer.get("ok") and str(composed_answer.get("text") or "").strip():
        answer = str(composed_answer.get("text") or "").strip()
    evidence_digest = execution_evidence_digest_text(result)
    evidence_view = repo_read_content_views(history)
    next_action = next_action_for_openwebui(status, result)
    initial_orientation = (
        state.get("initial_orientation_surface")
        if isinstance(state.get("initial_orientation_surface"), dict)
        else initial_orientation_surface_from_history(
            history,
            state.get("initial_orientation_skipped")
            if isinstance(state.get("initial_orientation_skipped"), list)
            else [],
        )
    )
    decisions = planner_decision_rows(history)
    if terminal_decision:
        decisions.append({
            "step": terminal_decision.get("step"),
            "action": terminal_decision.get("action"),
            "tool": terminal_decision.get("tool"),
            "reason": terminal_decision.get("reason"),
            "final_answer_preview": str(terminal_decision.get("final_answer") or "")[:700],
            "terminal": True,
        })
    validation_rejections = validation_rejection_rows(history)
    executed_tools = executed_tool_rows(history)
    turn_memory = planner_turn_memory(history, terminal_decision)
    result_digest = compact_final_state_result(result)
    artifacts = public_tool_artifact_rows(history)
    evidence_contract = planner_evidence_contract(goal, history)
    context = {
        "type": "agentic_loop_complete_structured_context",
        "contract_type": "agentic_loop_complete_structured_context",
        "not_a_summary": True,
        "openwebui_usage": {
            "primary_answer_field": "answer_for_30b",
            "next_action_field": "next_action_for_30b",
            "rule": (
                "Use answer_for_30b to respond to the user. Use the structured "
                "history/evidence only to justify or continue; never invent missing evidence."
            ),
        },
        "job": {
            "job_id": job_id,
            "status": status,
            "goal": state.get("goal"),
            "workspace": str(job_root),
            "planner_model": state.get("planner_model") or planner_model,
            "planner_url": state.get("planner_url") or planner_url,
        },
        "contract": {
            "planner_decides": True,
            "controller_validates_only": True,
            "controller_must_not_replace_planner_with_auto_tool_sequence": True,
            "invalid_planner_decision_flow": "planner_decision -> planner_decision_rejected/controller_guard -> next planner_decision",
            "final_requires_planner_final_action": True,
        },
        "execution_contract": {
            "planner_decides": True,
            "controller_validates_only": True,
            "controller_must_not_replace_planner_with_auto_tool_sequence": True,
            "invalid_planner_decision_flow": "planner_decision -> planner_decision_rejected/controller_guard -> next planner_decision",
            "final_requires_planner_final_action": True,
        },
        "final_answer": final_summary,
        "answer_for_30b": answer,
        "composed_answer": composed_answer,
        "artifacts": artifacts,
        "partial_products_for_30b": partial_products,
        "best_partial_product_for_30b": best_partial_product,
        "limits": public_tool_context_limits(artifacts),
        "evidence_digest_for_30b": evidence_digest,
        "evidence_view_for_30b": evidence_view,
        "initial_orientation_surface": initial_orientation,
        "next_action_for_30b": next_action,
        "planner": {
            "planner_model": state.get("planner_model") or planner_model,
            "history_count": len(history),
            "terminal_decision": terminal_decision or None,
            "decisions": decisions,
            "validation_rejections": validation_rejections,
            "ollama_turns": turn_memory.get("ollama_turns", []),
        },
        "turn_memory": turn_memory,
        "ollama_turns": turn_memory.get("ollama_turns", []),
        "successful_tool_turns": turn_memory.get("successful_tool_turns", []),
        "evidence_contract_at_finish": evidence_contract,
        "evidence_contract_at_terminal": evidence_contract,
        "planner_memory": state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else {},
        "controller_memory": controller_memory,
        "agent_flow_diagnostics": diagnostics,
        "executed_tools": executed_tools,
        "history_count": len(history),
        "history": planner_history_ledger(history),
        "result_digest": result_digest,
        "planner_decision": result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else None,
        "blocked_by": result.get("blocked_by"),
        "local_references_omitted_for_openwebui": True,
    }
    return strip_public_local_references(context)
