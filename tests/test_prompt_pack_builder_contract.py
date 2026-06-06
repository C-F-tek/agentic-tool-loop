from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt.pack_builder import (  # noqa: E402
    build_planner_user_payload,
    explicit_request_context_from_state,
)


def _json_len(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _budget_report(payload: dict[str, Any], *, system_prompt: str = "", extra_prompt_sections: dict[str, int] | None = None) -> dict[str, Any]:
    extra = sum(int(v or 0) for v in (extra_prompt_sections or {}).values())
    total = len(system_prompt) + _json_len(payload) + extra
    return {
        "schema": "planner_prompt_budget.v1",
        "char_budget": 100000,
        "generation_headroom_char_budget": 80000,
        "generation_headroom_reserve_chars": 20000,
        "total_prompt_chars": total,
        "over_budget": False,
        "over_generation_headroom_budget": False,
        "extra_prompt_chars": extra,
        "sections": {"available_tools": _json_len(payload.get("available_tools"))},
    }


def _deps(**overrides):
    deps = {
        "available_tools_for_user_payload": lambda tools: tools,
        "available_tools_window_pack": lambda *_args, **_kwargs: {"schema": "planner_available_tools_window.v1"},
        "compact_evidence_contract_for_prompt": lambda contract, **_kwargs: dict(contract),
        "compact_tool_manifest_for_prompt": lambda tools: tools,
        "forbidden_repeated_prompt_window_calls": lambda _history, _action: [],
        "hard_budget_evidence_contract_for_prompt": lambda *_args, contract, **_kwargs: dict(contract),
        "json_char_len": _json_len,
        "native_history_message_reserve_chars": lambda _history, _window_chars: 0,
        "optional_context_for_prompt": lambda **_kwargs: {"schema": "optional"},
        "optional_context_window_pack": lambda *_args, **_kwargs: {"schema": "planner_optional_context_window_pack.v1"},
        "planner_system_for_current_mode": lambda: "system",
        "preserve_required_next_tool_call_for_prompt": lambda _payload, _previous: None,
        "prompt_budget_report": _budget_report,
        "prompt_compaction_threshold": lambda: 0,
        "prompt_generation_headroom_char_budget": lambda: 80000,
        "prompt_window_chars": lambda compact, attempt=0: 1000 if compact else 3000,
        "report_exceeds_generation_headroom": lambda _report, _headroom: False,
        "required_next_tool_call_from_action": lambda action: {},
        "required_working_set_continuation_action": lambda *_args, **_kwargs: None,
        "required_working_set_for_prompt": lambda *_args, **_kwargs: {"schema": "planner_required_working_set.v1", "errors": []},
        "tool_shape_examples_for_prompt": lambda: {"repo_read": {"arguments": {"path": "..."}}},
        "windowed_evidence_contract_for_prompt": lambda *_args, contract, **_kwargs: dict(contract),
        "agent_job_root": lambda job_id: Path("jobs") / job_id,
        "internal_tool_prompt": lambda **_kwargs: "repo_read|final",
    }
    deps.update(overrides)
    return deps


def _config(**overrides):
    config = {
        "AGENTIC_PLANNER_NATIVE_TOOLS": False,
        "AGENTIC_PLANNER_NUM_CTX": 12288,
        "AGENTIC_PLANNER_NUM_CTX_CAP": 12288,
        "AGENTIC_PLANNER_NUM_CTX_REQUESTED": 12288,
        "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET": 100000,
        "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO": 0.5,
        "LAB_REPO": Path("lab"),
    }
    config.update(overrides)
    return config


def test_build_planner_user_payload_keeps_prompt_contract_sections() -> None:
    payload, report = build_planner_user_payload(
        job_id="job-1",
        state={"goal": "analizza repo", "approval_mode": "safe", "max_steps": 5},
        step=2,
        history=[],
        tool_manifest=[{"name": "repo_read"}],
        evidence_contract={"finalization_contract": {"final_allowed": True}},
        planner_memory={},
        intrinsic_context={},
        last_tool_result={},
        deps=_deps(),
        config=_config(),
    )

    assert payload["job_id"] == "job-1"
    assert payload["goal"] == "analizza repo"
    assert payload["prompt_pack_contract"]["schema"] == "planner_prompt_pack.v1"
    assert payload["required_working_set"]["schema"] == "planner_required_working_set.v1"
    assert payload["optional_context"] == {"schema": "optional"}
    assert payload["evidence_contract"]["finalization_contract"]["final_allowed"] is True
    assert payload["required_response_format"]["json_only"] is True
    assert report["required_working_set_errors"] == []


def test_build_planner_user_payload_exposes_original_args_context() -> None:
    context = {
        "schema": "macro_runtime_loop_payload_case.v1",
        "target_internal_tool": "repo_read",
        "target_arguments": {"path": "ia_carmine/runtime/x.py", "max_chars": 20000},
    }

    payload, _report = build_planner_user_payload(
        job_id="job-1",
        state={
            "goal": "macro request without literal file path",
            "original_args": {"context": json.dumps(context, ensure_ascii=False)},
        },
        step=1,
        history=[],
        tool_manifest=[{"name": "repo_read"}],
        evidence_contract={"finalization_contract": {"final_allowed": False}},
        planner_memory={},
        intrinsic_context={},
        last_tool_result={},
        deps=_deps(),
        config=_config(),
    )

    assert explicit_request_context_from_state({"original_args": {"context": context}}) == context
    assert payload["explicit_request_context"] == context


def test_build_planner_user_payload_preserves_required_continuation_surface() -> None:
    continuation = {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
        },
        "reason": "continue required window",
    }

    payload, _report = build_planner_user_payload(
        job_id="job-1",
        state={"goal": "diff"},
        step=3,
        history=[],
        tool_manifest=[{"name": "planner_scratchpad_read"}],
        evidence_contract={"finalization_contract": {"final_allowed": True}},
        planner_memory={},
        intrinsic_context={},
        last_tool_result={},
        deps=_deps(
            required_working_set_continuation_action=lambda *_args, **_kwargs: continuation,
            required_next_tool_call_from_action=lambda _action: {
                "tool": "planner_scratchpad_read",
                "arguments": continuation["arguments"],
            },
            forbidden_repeated_prompt_window_calls=lambda _history, _action: [{"reason": "already_consumed"}],
        ),
        config=_config(),
    )

    assert payload["required_next_tool_call"] == {
        "tool": "planner_scratchpad_read",
        "arguments": continuation["arguments"],
    }
    assert payload["forbidden_repeated_tool_calls"] == [{"reason": "already_consumed"}]
    assert payload["evidence_contract"]["planner_may_choose_final"] is False
    assert payload["evidence_contract"]["finalization_contract"]["final_allowed"] is False
