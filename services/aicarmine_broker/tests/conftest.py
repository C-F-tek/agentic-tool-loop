"""Shared pytest fixtures for aicarmine_broker tests."""
import pytest
from pathlib import Path
from typing import Any, Dict, List


@pytest.fixture
def mock_deps() -> Dict[str, Any]:
    """Return dict with all required deps (dispatch_tool, write_json, etc.)."""
    return {
        "agent_flow_diagnostics": lambda goal, history, memory: {},
        "agentic_tool_allowed": lambda tool, args, mode: (True, ""),
        "cached_tool_result": lambda hit, key: {"ok": True},
        "cached_vulkan_repair_result": lambda decision, history: None,
        "compact_tool_result_for_planner": lambda tool, result: {"tool": tool, "ok": True},
        "controller_file_code_product_orientation_preseed_plan": lambda *a: {},
        "controller_guard_count": lambda history, guard_type: 0,
        "controller_guard_rejection_signature": lambda *a: {},
        "controller_guard_rejection_signature_count": lambda history, sig: 0,
        "controller_initial_area_list_plans": lambda goal, args: [],
        "controller_initial_area_read_plan": lambda goal, args: {},
        "controller_initial_doc_preseed_plan": lambda goal, args: {},
        "controller_initial_orientation_candidate_pool": lambda root_result: [],
        "controller_memory_target_key": lambda goal, contract: "repo",
        "controller_orientation_model_select": lambda goal, candidates: {},
        "controller_preplanner_rag_preseed_plan": lambda goal, args: (None, {}, []),
        "controller_preplanner_rag_query_plan": lambda goal: {},
        "controller_preseed_plan": lambda goal, args: {},
        "decision_memory_claim_text": lambda decision: "",
        "dispatch_tool": lambda *a, **k: {"ok": True},
        "evaluate_initial_orientation_shadow": lambda *a, **k: {},
        "finalization_contract_available": lambda history: True,
        "initial_orientation_surface_from_history": lambda goal, history: [],
        "is_unrecoverable_plain_text_planner_output": lambda text: False,
        "load_agent_job_state": lambda job_id: {"goal": "test", "status": "running_agentic"},
        "normalize_tool_name": lambda name: name,
        "orientation_legacy_selected_candidate_ids": lambda candidates, doc_plan, area_plans: [],
        "orientation_shadow_effective_mode": lambda requested_mode: "shadow",
        "orientation_shadow_selection_metrics": lambda legacy, model: {},
        "planner_decision": lambda *a, **k: {"action": "tool", "tool": "repo_read", "arguments": {}},
        "planner_evidence_contract": lambda goal, history: {"ok": True},
        "planner_history_ledger": [],
        "planner_memory_surface": lambda args, root: {},
        "repeated_tool_call_count": lambda history, tool, args: 0,
        "sanitize_tool_args": lambda tool, args, original, public: dict(args),
        "should_attempt_vulkan_repair": lambda decision, validation, history: False,
        "tool_cache_hit": lambda history, tool, args: None,
        "tool_cache_key": lambda tool, args: "",
        "validate_planner_decision_against_evidence": lambda *a, **k: {"ok": True},
        "vulkan_repair_invalid_planner_decision": lambda *a, **k: {},
        "write_agent_job_state": lambda state: None,
        "write_json": lambda path, data: None,
        "write_loop_turn_memory": lambda job_id, step, memory: None,
        "planner_incomprehensible_retry_count": lambda history, goal: 0,
        "planner_memory_false_unavailable_claim": lambda args, root: False,
        "raw_planner_text_classification": lambda text: {"category": "tool", "confidence": 0.9},
        "should_retry_incomprehensible_planner_output": lambda decision, history: False,
        "normalize_terminal_planner_decision": lambda decision: decision,
        "native_required_repaired_tool_decision_disallowed": lambda *a: False,
        "specialist_route_audit": lambda *a, **k: {},
        "planner_replan_specialist_for_validation": lambda *a, **k: {},
    }


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Return dict with AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES, AGENT_MAX_STEPS, etc."""
    return {
        "AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES": 3,
        "AGENT_DEFAULT_MAX_STEPS": 50,
        "AGENT_MAX_STEPS": 100,
        "OLLAMA_TASK_MODEL": "qwen3:8b",
        "OLLAMA_TASK_URL": "http://127.0.0.1:11435",
        "PLANNER_MODEL": "qwen3:30b",
        "PLANNER_URL": "http://127.0.0.1:3572",
        "VALID_INTERNAL_TOOLS": ["repo_read", "repo_write", "repo_list_files", "terminal"],
    }


@pytest.fixture
def mock_state() -> Dict[str, Any]:
    """Return dict with goal, status, max_steps, user_consent."""
    return {
        "goal": "Test goal for unit testing",
        "status": "running_agentic",
        "max_steps": 10,
        "user_consent": "",
        "approval_mode": "safe_write_lab",
        "public_tool_name": "vulkan_helper",
        "original_args": {},
    }


@pytest.fixture
def mock_history() -> List[Dict[str, Any]]:
    """Return list of history rows."""
    return [
        {
            "step": 1,
            "decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "test.py"}},
            "tool_result": {"ok": True, "tool": "repo_read"},
        },
    ]


@pytest.fixture
def mock_root(tmp_path: Path) -> Path:
    """Return temporary root directory for test jobs."""
    return tmp_path