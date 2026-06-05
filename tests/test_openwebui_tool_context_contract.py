from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_payload.openwebui_tool_context import build_tool_context_for_30b  # noqa: E402


def test_build_tool_context_for_30b_preserves_public_shape_and_injected_sections() -> None:
    history = [{"step": 1, "decision": {"tool": "repo_read"}, "tool_result": {"tool": "repo_read", "ok": True}}]
    state = {
        "goal": "analyze repo",
        "planner_model": "state-model",
        "planner_url": "http://planner",
        "planner_memory_surface": {"available": True},
        "controller_memory_last_write": {"ok": True, "target_key": "repo"},
        "initial_orientation_skipped": ["skip"],
    }
    result = {"history": history, "planner_decision": {"action": "final", "final_answer": "done"}, "blocked_by": "none"}

    context = build_tool_context_for_30b(
        "job-1",
        state,
        "completed",
        "final summary",
        result,
        planner_model="default-model",
        planner_url="http://default",
        job_root_for_id=lambda job_id: Path("jobs") / job_id,
        planner_composed_answer=lambda _root: {"ok": False},
        agent_flow_diagnostics=lambda _goal, _history, _memory: {"diag": True},
        partial_products_for_30b=lambda _history: [{"kind": "partial"}],
        best_partial_product_for_30b=lambda _history: {"kind": "partial"},
        answer_for_openwebui=lambda _status, _summary, _result: "answer",
        execution_evidence_digest_text=lambda _result: "evidence",
        repo_read_content_views=lambda _history: [{"path": "a.py"}],
        next_action_for_openwebui=lambda _status, _result: {"action": "answer"},
        initial_orientation_surface_from_history=lambda _history, skipped: {"skipped": skipped},
        planner_decision_rows=lambda _history: [{"step": 1, "tool": "repo_read"}],
        validation_rejection_rows=lambda _history: [],
        executed_tool_rows=lambda _history: [{"tool": "repo_read"}],
        planner_turn_memory=lambda _history, _terminal: {"ollama_turns": [{"step": 1}], "successful_tool_turns": [{"tool": "repo_read"}]},
        compact_final_state_result=lambda _result: {"compact": True},
        public_tool_artifact_rows=lambda _history: [{"tool": "repo_read", "artifact": {"content": "x"}}],
        public_tool_context_limits=lambda _artifacts: [{"kind": "limit"}],
        planner_evidence_contract=lambda goal, _history: {"goal": goal},
        planner_history_ledger=lambda _history: [{"step": 1}],
        strip_public_local_references=lambda value: value,
    )

    assert context["type"] == "agentic_loop_complete_structured_context"
    assert context["job"]["job_id"] == "job-1"
    assert context["job"]["workspace"] == str(Path("jobs") / "job-1")
    assert context["job"]["planner_model"] == "state-model"
    assert context["top_level_evidence_guide_field"] == "evidence_guide_for_30b"
    for duplicate_key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "final_answer",
        "composed_answer",
        "evidence_guide_for_30b",
    ):
        assert duplicate_key not in context
    assert context["partial_products_for_30b"] == [{"kind": "partial"}]
    assert context["best_partial_product_for_30b"] == {"kind": "partial"}
    assert context["limits"] == [{"kind": "limit"}]
    assert context["evidence_digest_for_30b"] == "evidence"
    assert context["evidence_view_for_30b"] == [{"path": "a.py"}]
    assert context["initial_orientation_surface"] == {"skipped": ["skip"]}
    assert context["planner"]["terminal_decision"] == {"action": "final", "final_answer": "done"}
    assert context["planner"]["decisions"][-1]["terminal"] is True
    assert context["evidence_contract_at_finish"] == {"goal": "analyze repo"}
    assert context["evidence_contract_at_terminal"] == {"goal": "analyze repo"}
    assert context["agent_flow_diagnostics"]["controller_memory_records_written"] == 1
    assert context["agent_flow_diagnostics"]["controller_memory_target_key"] == "repo"


def test_build_tool_context_for_30b_completed_uses_composed_answer_when_available() -> None:
    context = build_tool_context_for_30b(
        "job-1",
        {"goal": "goal"},
        "completed",
        "final summary",
        {"history": []},
        planner_model="model",
        planner_url="url",
        job_root_for_id=lambda job_id: Path(job_id),
        planner_composed_answer=lambda _root: {"ok": True, "text": "composed"},
        agent_flow_diagnostics=lambda _goal, _history, _memory: {},
        partial_products_for_30b=lambda _history: [],
        best_partial_product_for_30b=lambda _history: {},
        answer_for_openwebui=lambda _status, _summary, _result: "answer",
        execution_evidence_digest_text=lambda _result: "",
        repo_read_content_views=lambda _history: [],
        next_action_for_openwebui=lambda _status, _result: {},
        initial_orientation_surface_from_history=lambda _history, _skipped: {},
        planner_decision_rows=lambda _history: [],
        validation_rejection_rows=lambda _history: [],
        executed_tool_rows=lambda _history: [],
        planner_turn_memory=lambda _history, _terminal: {},
        compact_final_state_result=lambda _result: {},
        public_tool_artifact_rows=lambda _history: [],
        public_tool_context_limits=lambda _artifacts: [],
        planner_evidence_contract=lambda _goal, _history: {},
        planner_history_ledger=lambda _history: [],
        strip_public_local_references=lambda value: value,
    )

    assert context["top_level_evidence_guide_field"] == "evidence_guide_for_30b"
    assert "answer_for_30b" not in context
    assert "composed_answer" not in context
    assert "final_answer" not in context
