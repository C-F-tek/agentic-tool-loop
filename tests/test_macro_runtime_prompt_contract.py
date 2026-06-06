from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicarmine_broker import planner
from aicarmine_broker.application.prompt.pack_builder import explicit_request_context_from_state
from macro_runtine_test.test_loop_payload_completo import (
    _request_for_case,
    _safe_job_id,
    _assert_3571_runtime_final_handoff,
    _target_tool_coverage_from_history,
)
from macro_runtine_test.tool_cases import build_tool_cases


def test_macro_repo_read_prompt_does_not_trigger_controller_preseed() -> None:
    cases = build_tool_cases(
        sample_file="README.md",
        sample_files=("README.md",),
        seed=123,
        run_id="unit",
    )
    case = cases["repo_read"]
    payload = _request_for_case(
        case,
        job_id=_safe_job_id("unit", "repo_read"),
        wait_seconds=1,
        default_max_steps=2,
    )
    goal = str(payload["request"])

    assert planner._should_preseed_root_surface(goal, payload) is False

    explicit_context = explicit_request_context_from_state({
        "goal": goal,
        "original_args": payload,
    })
    intrinsic_context = {"explicit_request_context": explicit_context}
    contract = planner.planner_evidence_contract(
        goal,
        [],
        intrinsic_context=intrinsic_context,
    )
    native_tool_names = planner._tool_surface_names_for_turn(
        goal=goal,
        evidence_contract=contract,
        intrinsic_context=intrinsic_context,
    )

    assert "repo_read" in native_tool_names


def test_macro_target_coverage_ignores_controller_preseed_only() -> None:
    coverage = _target_tool_coverage_from_history(
        [
            {
                "step": 0,
                "decision": {"action": "controller_preseed", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True, "controller_preseed": True},
            }
        ],
        "repo_read",
    )

    assert coverage["covered"] is False
    assert coverage["reason"] == "target_tool_not_attempted_after_planner"


def test_macro_target_coverage_requires_planner_step_attempt() -> None:
    coverage = _target_tool_coverage_from_history(
        [
            {
                "step": 1,
                "decision": {"action": "tool", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True},
            }
        ],
        "repo_read",
    )

    assert coverage["covered"] is True
    assert coverage["matched_step"] == 1
    assert coverage["matched_kind"] == "decision"


def test_macro_asserts_existing_3571_runtime_final_handoff() -> None:
    assertion = _assert_3571_runtime_final_handoff({
        "openwebui_final_handoff": {
            "terminal_result": True,
            "planner_unload_attempted": True,
            "planner_unload_ok": True,
            "reason": "free_planner_vram_before_returning_vulkan_helper_result_to_openwebui",
        },
        "openwebui_final_unload_planner": {
            "attempted": True,
            "ok": True,
            "planner_model": "qwen3-coder:30b",
            "planner_url": "http://127.0.0.1:11434/api/chat",
            "unload_endpoint": "http://127.0.0.1:11434/api/generate",
        },
    })

    assert assertion["ok"] is True
    assert assertion["unload"]["unload_endpoint"] == "http://127.0.0.1:11434/api/generate"
