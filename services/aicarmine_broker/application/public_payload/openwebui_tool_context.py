"""Structured terminal context buildfrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

er returned to OpenWebUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..shared.evidence_contract_summary import (
    compact_evidence_contract_summary,
    coverage_status_from_contract,
)
from .tool_context import slim_public_tool_context


JobRootForId = Callable[[str], Any]
ComposedAnswerLoader = Callable[[Any], dict[str, Any]]
HistoryToRows = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
EvidenceContractBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
ResultToText = Callable[[dict[str, Any]], str]
ResultToDict = Callable[[dict[str, Any]], dict[str, Any]]
ValueCleaner = Callable[[Any], Any]


@dataclass(frozen=True)
class OpenWebUIPayloadBuilder:
    """Owner for OpenWebUI-visible structured terminal context."""

    _planner_model: str
    _planner_url: str
    _job_root_for_id: JobRootForId
    _planner_composed_answer: ComposedAnswerLoader
    _agent_flow_diagnostics: Callable[[str, list[dict[str, Any]], dict[str, Any] | None], dict[str, Any]]
    _partial_products_for_30b: HistoryToRows
    _best_partial_product_for_30b: Callable[[list[dict[str, Any]]], dict[str, Any]]
    _answer_for_openwebui: Callable[[str, str, dict[str, Any]], str]
    _execution_evidence_digest_text: ResultToText
    _repo_read_content_views: HistoryToRows
    _next_action_for_openwebui: Callable[[str, dict[str, Any]], dict[str, Any]]
    _initial_orientation_surface_from_history: Callable[[list[dict[str, Any]], list[Any]], dict[str, Any]]
    _planner_decision_rows: HistoryToRows
    _validation_rejection_rows: HistoryToRows
    _executed_tool_rows: HistoryToRows
    _planner_turn_memory: Callable[[list[dict[str, Any]], dict[str, Any]], dict[str, Any]]
    _compact_final_state_result: ResultToDict
    _public_tool_artifact_rows: HistoryToRows
    _public_tool_context_limits: HistoryToRows
    _planner_evidence_contract: EvidenceContractBuilder
    _planner_history_ledger: HistoryToRows
    _strip_public_local_references: ValueCleaner

    def build_terminal_payload(
        self,
        job_id: str,
        state: dict[str, Any],
        status: str,
        final_summary: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._build_context(job_id, state, status, final_summary, result)

    def _build_context(
        self,
        job_id: str,
        state: dict[str, Any],
        status: str,
        final_summary: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = result if isinstance(result, dict) else {}
        history = result.get("history") if isinstance(result.get("history"), list) else []
        terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
        goal = str(state.get("goal") or "")
        planner_memory = state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else None
        context_build_errors: list[dict[str, Any]] = []

        def build_section(name: str, default: Any, builder: Callable[[], Any]) -> Any:
            try:
                return builder()
            except Exception:
                pass
                context_build_errors.append({
                    "section": name,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                })
                return default

        diagnostics = build_section(
            "agent_flow_diagnostics",
            {
                "schema": "agent_flow_diagnostics.v1",
                "diagnostic_unavailable": True,
            },
            lambda: self._agent_flow_diagnostics(goal, history, planner_memory),
        )
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {
            "schema": "agent_flow_diagnostics.v1",
            "diagnostic_unavailable": True,
            "received_type": type(diagnostics).__name__,
        }
        result = dict(result)
        partial_products = build_section(
            "partial_products_for_30b",
            [],
            lambda: self._partial_products_for_30b(history),
        )
        partial_products = partial_products if isinstance(partial_products, list) else []
        best_partial_product = build_section(
            "best_partial_product_for_30b",
            {},
            lambda: self._best_partial_product_for_30b(history),
        )
        best_partial_product = best_partial_product if isinstance(best_partial_product, dict) else {}
        if partial_products:
            result["partial_products_for_30b"] = partial_products
        if best_partial_product:
            result["best_partial_product_for_30b"] = best_partial_product
        controller_memory = state.get("controller_memory_last_write") if isinstance(state.get("controller_memory_last_write"), dict) else {}
        if controller_memory:
            diagnostics["controller_memory_records_written"] = 1 if controller_memory.get("ok") else 0
            diagnostics["controller_memory_target_key"] = controller_memory.get("target_key")
        result["agent_flow_diagnostics"] = diagnostics
        job_root = build_section(
            "job_root",
            "",
            lambda: self._job_root_for_id(job_id),
        )
        evidence_digest = build_section(
            "evidence_digest_for_30b",
            "",
            lambda: self._execution_evidence_digest_text(result),
        )
        evidence_digest = str(evidence_digest or "")
        evidence_view = build_section(
            "evidence_view_for_30b",
            [],
            lambda: self._repo_read_content_views(history),
        )
        evidence_view = evidence_view if isinstance(evidence_view, list) else []
        next_action = build_section(
            "next_action_for_30b",
            {},
            lambda: self._next_action_for_openwebui(status, result),
        )
        next_action = next_action if isinstance(next_action, dict) else {}
        initial_orientation = (
            state.get("initial_orientation_surface")
            if isinstance(state.get("initial_orientation_surface"), dict)
            else build_section(
                "initial_orientation_surface",
                {},
                lambda: self._initial_orientation_surface_from_history(
                    history,
                    state.get("initial_orientation_skipped")
                    if isinstance(state.get("initial_orientation_skipped"), list)
                    else [],
                ),
            )
        )
        initial_orientation = initial_orientation if isinstance(initial_orientation, dict) else {}
        decisions = build_section(
            "planner_decision_rows",
            [],
            lambda: self._planner_decision_rows(history),
        )
        decisions = decisions if isinstance(decisions, list) else []
        if terminal_decision:
            decisions.append({
                "step": terminal_decision.get("step"),
                "action": terminal_decision.get("action"),
                "tool": terminal_decision.get("tool"),
                "reason": terminal_decision.get("reason"),
                "final_answer_preview": str(terminal_decision.get("final_answer") or "")[:700],
                "terminal": True,
            })
        validation_rejections = build_section(
            "validation_rejection_rows",
            [],
            lambda: self._validation_rejection_rows(history),
        )
        validation_rejections = validation_rejections if isinstance(validation_rejections, list) else []
        executed_tools = build_section(
            "executed_tool_rows",
            [],
            lambda: self._executed_tool_rows(history),
        )
        executed_tools = executed_tools if isinstance(executed_tools, list) else []
        turn_memory = build_section(
            "turn_memory",
            {},
            lambda: self._planner_turn_memory(history, terminal_decision),
        )
        turn_memory = turn_memory if isinstance(turn_memory, dict) else {}
        result_digest = build_section(
            "result_digest",
            {},
            lambda: self._compact_final_state_result(result),
        )
        result_digest = result_digest if isinstance(result_digest, dict) else {}
        artifacts = build_section(
            "artifacts",
            [],
            lambda: self._public_tool_artifact_rows(history),
        )
        artifacts = artifacts if isinstance(artifacts, list) else []
        evidence_contract = build_section(
            "evidence_contract",
            {},
            lambda: self._planner_evidence_contract(goal, history),
        )
        evidence_contract = evidence_contract if isinstance(evidence_contract, dict) else {}
        coverage_status = build_section(
            "coverage_status",
            {},
            lambda: coverage_status_from_contract(evidence_contract),
        )
        coverage_status = coverage_status if isinstance(coverage_status, dict) else {}
        evidence_contract_summary = build_section(
            "evidence_contract_summary",
            {},
            lambda: compact_evidence_contract_summary(
                evidence_contract,
                schema="planner_evidence_contract_public_summary.v1",
            ),
        )
        evidence_contract_summary = evidence_contract_summary if isinstance(evidence_contract_summary, dict) else {}
        history_ledger = build_section(
            "history_ledger",
            [],
            lambda: self._planner_history_ledger(history),
        )
        history_ledger = history_ledger if isinstance(history_ledger, list) else []
        limits = build_section(
            "limits",
            [],
            lambda: self._public_tool_context_limits(artifacts),
        )
        limits = limits if isinstance(limits, list) else []
        context_build_diagnostics = {
            "schema": "openwebui_tool_context_build_diagnostics.v1",
            "ok": not context_build_errors,
            "errors": context_build_errors,
            "partial_context": bool(context_build_errors),
        }
        context = {
            "type": "agentic_loop_complete_structured_context",
            "contract_type": "agentic_loop_complete_structured_context",
            "not_a_summary": True,
            "openwebui_usage": {
                "top_level_evidence_guide_field": "evidence_guide_for_30b",
                "next_action_field": "next_action_for_30b",
                "rule": (
                    "This tool_context_for_30b object is evidence/context only. "
                    "The global evidence_guide_for_30b field is outside this JSON. "
                    "Use the structured history/evidence here for detailed answers; "
                    "never invent missing evidence."
                ),
            },
            "job": {
                "job_id": job_id,
                "status": status,
                "goal": state.get("goal"),
                "workspace": str(job_root),
                "planner_model": state.get("planner_model") or self._planner_model,
                "planner_url": state.get("planner_url") or self._planner_url,
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
            "top_level_evidence_guide_field": "evidence_guide_for_30b",
            "artifacts": artifacts,
            "partial_products_for_30b": partial_products,
            "best_partial_product_for_30b": best_partial_product,
            "limits": limits,
            "evidence_digest_for_30b": evidence_digest,
            "evidence_view_for_30b": evidence_view,
            "initial_orientation_surface": initial_orientation,
            "next_action_for_30b": next_action,
            "planner": {
                "planner_model": state.get("planner_model") or self._planner_model,
                "history_count": len(history),
                "terminal_decision": terminal_decision or None,
                "decisions": decisions,
                "validation_rejections": validation_rejections,
                "ollama_turns": turn_memory.get("ollama_turns", []),
            },
            "turn_memory": turn_memory,
            "ollama_turns": turn_memory.get("ollama_turns", []),
            "successful_tool_turns": turn_memory.get("successful_tool_turns", []),
            "failed_tool_turns": turn_memory.get("failed_tool_turns", []),
            "evidence_contract_summary": evidence_contract_summary,
            "evidence_contract_at_finish": evidence_contract_summary,
            "evidence_contract_at_terminal": evidence_contract_summary,
            "evidence_contract_sha256": evidence_contract_summary.get("evidence_contract_sha256"),
            "evidence_contract_chars": evidence_contract_summary.get("evidence_contract_chars"),
            "coverage_status": coverage_status,
            "minimum_read_coverage": coverage_status.get("minimum_read_coverage"),
            "planner_memory": state.get("planner_memory_surface") if isinstance(state.get("planner_memory_surface"), dict) else {},
            "controller_memory": controller_memory,
            "agent_flow_diagnostics": diagnostics,
            "context_build_diagnostics": context_build_diagnostics,
            "executed_tools": executed_tools,
            "history_count": len(history),
            "history": history_ledger,
            "result_digest": result_digest,
            "planner_decision": result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else None,
            "blocked_by": result.get("blocked_by"),
            "local_references_omitted_for_openwebui": True,
        }
        public_context = slim_public_tool_context(context)
        return self._strip_public_local_references(public_context)


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
    """Compatibility entrypoint for the structured terminal context owner."""
    builder = OpenWebUIPayloadBuilder(
        _planner_model=planner_model,
        _planner_url=planner_url,
        _job_root_for_id=job_root_for_id,
        _planner_composed_answer=planner_composed_answer,
        _agent_flow_diagnostics=agent_flow_diagnostics,
        _partial_products_for_30b=partial_products_for_30b,
        _best_partial_product_for_30b=best_partial_product_for_30b,
        _answer_for_openwebui=answer_for_openwebui,
        _execution_evidence_digest_text=execution_evidence_digest_text,
        _repo_read_content_views=repo_read_content_views,
        _next_action_for_openwebui=next_action_for_openwebui,
        _initial_orientation_surface_from_history=initial_orientation_surface_from_history,
        _planner_decision_rows=planner_decision_rows,
        _validation_rejection_rows=validation_rejection_rows,
        _executed_tool_rows=executed_tool_rows,
        _planner_turn_memory=planner_turn_memory,
        _compact_final_state_result=compact_final_state_result,
        _public_tool_artifact_rows=public_tool_artifact_rows,
        _public_tool_context_limits=public_tool_context_limits,
        _planner_evidence_contract=planner_evidence_contract,
        _planner_history_ledger=planner_history_ledger,
        _strip_public_local_references=strip_public_local_references,
    )
    return builder.build_terminal_payload(job_id, state, status, final_summary, result)
