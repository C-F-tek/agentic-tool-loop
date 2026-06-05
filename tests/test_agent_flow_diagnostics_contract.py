from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.controller.diagnostics import agent_flow_diagnostics  # noqa: E402


def _contract(_goal: str, _history: list[dict]) -> dict:
    return {"finalization_contract": {"reason": "needs_more_evidence", "final_allowed": False}}


def _retry_count(history: list[dict]) -> int:
    return sum(1 for item in history if item.get("retry"))


def test_agent_flow_diagnostics_counts_terminal_signals() -> None:
    history = [
        {
            "decision": {"native_tool_call": True, "native_tool_calls_seen": 2, "deterministic_strip": True},
            "tool_result": {"tool": "repo_read", "ok": True, "preseed_reason": "explicit_file_request_needs_file_surface"},
        },
        {
            "tool_result": {
                "tool": "repo_tree",
                "ok": True,
                "path": ".",
                "controller_preseed": True,
                "preseed_reason": "explicit_directory_request_needs_scope_surface",
            },
        },
        {"tool_result": {"tool": "planner_scratchpad_write", "ok": True}},
        {"tool_result": {"tool": "runtime_sqlite_memory_write", "ok": True}},
        {"tool_result": {"tool": "runtime_sqlite_memory_cleanup", "dry_run": True}},
        {
            "decision": {"native_tool_call": True},
            "tool_result": {
                "tool": "controller_guard",
                "guard_type": "planner_retry_required",
                "cache_key": "same-call",
                "raw_planner_text_preview": "raw\ntext",
                "vulkan_repair": {"ok": False},
                "rejected_decision": {"native_tool_call": True},
            },
            "retry": True,
        },
        {"decision": {"action": "tool_batch"}, "tool_result": {"tool": "repo_list_files", "ok": True}},
    ]

    diagnostics = agent_flow_diagnostics(
        "goal",
        history,
        {"available": True, "record_count": 3},
        native_tools_enabled=True,
        evidence_contract_builder=_contract,
        planner_incomprehensible_retry_count=_retry_count,
    )

    assert diagnostics["planner_native_tools_enabled"] is True
    assert diagnostics["native_tool_calls_seen"] == 3
    assert diagnostics["native_tool_call_validated"] == 1
    assert diagnostics["native_tool_call_repaired_by_gpu0"] == 1
    assert diagnostics["native_tool_batch_executed"] == 1
    assert diagnostics["planner_retry_required_count"] == 1
    assert diagnostics["planner_retry_streak"] == 1
    assert diagnostics["vulkan_repair_attempted"] is True
    assert diagnostics["memory_tool_calls"] == 3
    assert diagnostics["scratchpad_entries"] == 1
    assert diagnostics["persistent_memory_records_written"] == 1
    assert diagnostics["persistent_memory_cleanup_dry_run"] == 1
    assert diagnostics["planner_memory_surface_available"] is True
    assert diagnostics["planner_memory_records_injected"] == 3
    assert diagnostics["preseed_root_surface"] is True
    assert diagnostics["preseed_scope_surface"] is True
    assert diagnostics["preseed_file_surface"] is True
    assert diagnostics["final_gate_blocker"] == "needs_more_evidence"
    assert diagnostics["final_allowed"] is False
    assert diagnostics["last_non_empty_raw_previews"] == ["raw text"]
    assert diagnostics["repeated_cache_keys"] == ["same-call"]
    assert diagnostics["guard_count"] == 1
    assert diagnostics["guard_counts_by_type"] == {"planner_retry_required": 1}
    assert diagnostics["deterministic_strip_count"] == 1


def test_agent_flow_diagnostics_counts_memory_false_unavailable_claim() -> None:
    diagnostics = agent_flow_diagnostics(
        "goal",
        [{"tool_result": {"tool": "controller_guard", "guard_type": "planner_memory_false_unavailable_claim"}}],
        None,
        native_tools_enabled=False,
        evidence_contract_builder=_contract,
        planner_incomprehensible_retry_count=_retry_count,
    )

    assert diagnostics["planner_native_tools_enabled"] is False
    assert diagnostics["planner_memory_false_unavailable_claims"] == 1
