from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from aicarmine_broker.application.planner.validator import (  # noqa: E402
    validate_planner_decision_against_evidence,
)
from aicarmine_broker.application.tool_surface.batch_contract import canonical_batch_args  # noqa: E402
from aicarmine_broker.application.prompt.tool_contract import (  # noqa: E402
    hard_budget_tool_shape_examples_for_prompt,
)
from aicarmine_broker.application.tool_surface.candidate_actions import (  # noqa: E402
    enforce_required_scratchpad_read_continuation_contract,
    preserve_required_next_tool_call_for_prompt,
)
from aicarmine_broker.application.tool_surface.turn_surface_policy import (  # noqa: E402
    ToolSurfacePolicy,
)


def _any_argument_group_present(args: dict[str, Any], groups: list[list[str]]) -> bool:
    return any(all(args.get(name) not in (None, "", [], {}) for name in group) for group in groups)


def _planner_scratchpad_read_selector_present(args: dict[str, Any]) -> bool:
    kind = str(args.get("kind") or "")
    if kind in {"prompt_context_window", "code_product_build_state"}:
        return _any_argument_group_present(args, [["document_id"], ["section"], ["tag"], ["query"], ["target_file"]])
    return _any_argument_group_present(args, [["document_id"], ["section"], ["tag"], ["query"], ["kind"]])


def _matches_prompt_context_continuation(decision: dict[str, Any], required: dict[str, Any]) -> bool:
    required_args = required.get("arguments") if isinstance(required.get("arguments"), dict) else {}
    decision_args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    return (
        decision.get("tool") == required.get("tool")
        and decision_args.get("kind") == required_args.get("kind")
        and decision_args.get("document_id") == required_args.get("document_id")
        and decision_args.get("offset") == required_args.get("offset")
        and decision_args.get("max_chars") == required_args.get("max_chars")
    )


def _deps() -> dict[str, Any]:
    return {
        "agentic_v2_decision_paths": lambda tool, args: [],
        "agentic_v2_goal_scope": lambda goal, contract: "",
        "agentic_v2_read_has_window": lambda args: False,
        "agentic_v2_successful_read_paths": lambda history: [],
        "any_argument_group_present": _any_argument_group_present,
        "apply_duplicate_window_replan_contract": lambda contract, **kwargs: contract,
        "apply_unverified_old_text_replan_contract": lambda contract, **kwargs: contract,
        "argument_value_present": lambda args, name: args.get(name) not in (None, "", [], {}),
        "canonical_invalid_code_product_decision_signature": lambda decision, violations: None,
        "code_product_build_state_duplicate_write": lambda *args, **kwargs: False,
        "code_product_build_state_has_collecting_progress": lambda state: True,
        "code_product_build_state_parse": lambda text: {},
        "code_product_build_state_ready_payload": lambda state: True,
        "code_product_low_signal_target": lambda path, contract: False,
        "code_product_payload_violations": lambda proposal, verified_paths: [],
        "contract_final_required_now": lambda contract: True,
        "copyable_example_text": lambda value: False,
        "decision_matches_prompt_context_continuation": _matches_prompt_context_continuation,
        "decision_paths": lambda args: [],
        "enforce_required_scratchpad_read_continuation_contract": (
            enforce_required_scratchpad_read_continuation_contract
        ),
        "final_answer_is_action_plan_without_code_product": lambda answer: False,
        "final_composition_tool_names_from_candidates": lambda contract: set(),
        "repo_analysis_final_answer_quality": lambda answer, contract: {"violations": []},
        "invalid_code_product_decision_signature_count": lambda history, signature: 0,
        "invalid_decision_signature_key": lambda signature: "",
        "native_required_tool_decision_has_transport_provenance": (
            lambda decision: decision.get("native_tool_call") is True
            and isinstance(decision.get("raw_native_tool_call"), dict)
        ),
        "normalize_terminal_planner_decision": lambda decision: decision,
        "normalize_tool_name": lambda name: str(name or "").strip(),
        "old_text_verified_by_repo_read": lambda history, path, text: False,
        "path_exists_repo_relative": lambda path: True,
        "path_under_scope": lambda path, scope: True,
        "planner_scratchpad_read_selector_present": _planner_scratchpad_read_selector_present,
        "planner_scratchpad_window_signature": lambda args: (
            args.get("kind"),
            args.get("document_id"),
            args.get("offset"),
            args.get("max_chars"),
        ),
        "prompt_window_consumed_offsets": lambda history: {},
        "prompt_window_tracking_metadata_errors": lambda history: [],
        "repo_analysis_goal": lambda goal: False,
        "repo_path_kind": lambda path: "file",
        "repo_read_selector_present": lambda args: _any_argument_group_present(args, [["path"], ["paths"], ["item"], ["items"]]),
        "repo_read_window_signature": lambda args: None,
        "repo_readable_evidence_file": lambda path: True,
        "repo_rel_token": lambda path: str(path or ""),
        "repeated_tool_call_count": lambda history, tool, args: 0,
        "scope_claim_conflict_for_path": lambda path, claims: None,
        "successful_code_edit_proposals": lambda history: [],
        "successful_window_signatures": lambda history, tool: set(),
        "target_scope_conflict_resolved": lambda path, args, contract: False,
        "latest_file_list_result": lambda history: {},
        "goal_requires_code_product_report": lambda goal: False,
        "planner_evidence_contract": lambda goal, history: {
            "finalization_contract": {"final_allowed": True},
            "candidate_next_actions": [],
            "code_product_contract": {},
        },
        "validate_unified_diff_text": lambda **kwargs: [],
    }


def _config() -> dict[str, Any]:
    return {
        "AGENTIC_PLANNER_NATIVE_TOOLS": True,
        "CODE_PRODUCT_BUILD_STATE_KIND": "code_product_build_state",
        "VALID_INTERNAL_TOOLS": {
            "planner_scratchpad_read",
            "planner_scratchpad_write",
            "runtime_sqlite_memory_search",
            "runtime_sqlite_memory_write",
        },
    }


def test_required_prompt_context_continuation_is_not_blocked_by_final_gate() -> None:
    continuation_args = {
        "kind": "prompt_context_window",
        "document_id": "prompt-context-smoke",
        "offset": 11135,
        "max_chars": 500,
    }
    continuation_required = {
        "tool": "planner_scratchpad_read",
        "arguments": continuation_args,
    }

    result = validate_planner_decision_against_evidence(
        "read AGENTS.md",
        {
            "action": "tool",
            "tool": "planner_scratchpad_read",
            "arguments": continuation_args,
            "allowed_tool_names": ["planner_scratchpad_read"],
            "allowed_native_tool_names": ["planner_scratchpad_read"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_read"}},
            "prompt_context_continuation_required": continuation_required,
        },
        [],
        deps=_deps(),
        config=_config(),
    )

    assert result["ok"] is True
    assert "final_required_tool_call_disallowed" not in result["violations"]


def test_prompt_context_continuation_surface_preempts_terminal_empty_surface() -> None:
    policy = ToolSurfacePolicy(order_tool_names=lambda names: sorted(names))
    contract: dict[str, Any] = {
        "finalization_contract": {"final_allowed": True},
        "required_next_progress": "Quality gate is satisfied. produce action=final.",
        "candidate_next_actions": [],
    }
    policy.apply(contract)

    names = policy.tools_for_turn(
        goal="read-only technical analysis",
        evidence_contract=contract,
        intrinsic_context={},
        prompt_context_continuation_required={
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": "prompt-context-smoke",
                "offset": 32768,
                "max_chars": 32768,
            },
        },
    )

    assert names == ["planner_scratchpad_read"]


def test_prompt_context_continuation_rejection_contract_disables_final() -> None:
    continuation_required = {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "prompt-context-smoke",
            "offset": 32768,
            "max_chars": 32768,
        },
        "reason": "Continue consuming prompt context before final.",
    }

    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "final",
            "final_answer": "premature final",
            "allowed_tool_names": ["planner_scratchpad_read"],
            "allowed_native_tool_names": ["planner_scratchpad_read"],
            "prompt_context_continuation_required": continuation_required,
        },
        [],
        deps=_deps(),
        config=_config(),
    )

    contract = result["evidence_contract"]
    final_contract = contract["finalization_contract"]
    assert result["ok"] is False
    assert "prompt_context_continuation_required" in result["violations"]
    assert final_contract["final_allowed"] is False
    assert final_contract["planner_may_choose_final"] is False
    assert contract["planner_may_choose_final"] is False
    assert contract["required_next_tool_call"]["arguments"]["document_id"] == "prompt-context-smoke"
    assert contract["candidate_next_actions"] == [
        {
            "action": "tool",
            "tool": "planner_scratchpad_read",
            "arguments": continuation_required["arguments"],
            "reason": "Continue consuming prompt context before final.",
        }
    ]


def test_turn_surface_policy_required_scratchpad_read_overrides_final_contract() -> None:
    policy = ToolSurfacePolicy(order_tool_names=lambda names: sorted(names))
    contract: dict[str, Any] = {
        "finalization_contract": {"final_allowed": True},
        "planner_may_choose_final": True,
        "required_next_progress": "Quality gate is satisfied. produce action=final.",
        "required_next_tool_call": {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": "prompt-context-smoke",
                "offset": 32768,
                "max_chars": 32768,
            },
            "reason": "Continue consuming prompt context before final.",
        },
    }

    policy.apply(contract)

    assert contract["finalization_contract"]["final_allowed"] is False
    assert contract["planner_may_choose_final"] is False
    assert contract["turn_tool_surface_policy"]["allowed_tool_names"] == ["planner_scratchpad_read"]


def test_required_scratchpad_read_exposes_readonly_batch_windows() -> None:
    contract = enforce_required_scratchpad_read_continuation_contract(
        {
            "finalization_contract": {"final_allowed": True},
            "planner_may_choose_final": True,
        },
        {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": "prompt-context-smoke",
                "offset": 1000,
                "max_chars": 500,
            },
            "batch_window": {
                "document_id": "prompt-context-smoke",
                "offset": 1000,
                "max_chars": 500,
                "full_chars": 2600,
                "max_batch_actions": 8,
            },
            "reason": "Continue consuming prompt context before final.",
        },
    )

    micro_batch = contract["micro_batch_contract"]
    actions = micro_batch["allowed_batch_actions"]
    offsets = [item["arguments"]["offset"] for item in actions]

    assert micro_batch["allowed"] is True
    assert micro_batch["allowed_tools"] == ["planner_scratchpad_read"]
    assert offsets == [1000, 1500, 2000, 2500]
    assert len({item["action_id"] for item in actions}) == len(actions)
    assert contract["finalization_contract"]["final_allowed"] is False


def test_required_scratchpad_read_batch_dedupes_semantic_duplicate_windows() -> None:
    contract = enforce_required_scratchpad_read_continuation_contract(
        {
            "micro_batch_contract": {
                "allowed_batch_actions": [
                    {
                        "action_id": "legacy-duplicate",
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": "prompt-context-smoke",
                            "offset": "1000",
                            "max_chars": "500",
                            "target_file": "",
                        },
                    }
                ],
            },
        },
        {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": "prompt-context-smoke",
                "offset": 1000,
                "max_chars": 500,
            },
            "batch_window": {
                "document_id": "prompt-context-smoke",
                "offset": 1000,
                "max_chars": 500,
                "full_chars": 1600,
                "max_batch_actions": 8,
            },
            "reason": "Continue consuming prompt context before final.",
        },
    )

    actions = contract["micro_batch_contract"]["allowed_batch_actions"]
    offsets = [item["arguments"]["offset"] for item in actions]

    assert offsets == [1000, 1500]
    assert all(item.get("action_id") != "legacy-duplicate" for item in actions)


def test_native_batch_arg_signature_normalizes_numeric_strings_and_empty_values() -> None:
    assert canonical_batch_args(
        {
            "kind": "prompt_context_window",
            "document_id": "prompt-context-smoke",
            "offset": "001000",
            "max_chars": "500",
            "target_file": "",
        }
    ) == canonical_batch_args(
        {
            "kind": "prompt_context_window",
            "document_id": "prompt-context-smoke",
            "offset": 1000,
            "max_chars": 500,
        }
    )


def test_hard_budget_native_tool_shape_examples_omit_verbose_examples() -> None:
    examples = hard_budget_tool_shape_examples_for_prompt(native_tools=True)

    assert examples["schema_source"] == "ollama_request.tools"
    assert examples["examples_omitted_for_prompt_budget"] is True
    assert "examples" not in examples
    assert examples["content_json_tool_calls_allowed"] is False


def test_preserve_required_next_tool_call_handles_legacy_single_read_candidate() -> None:
    payload = {
        "evidence_contract": {
            "finalization_contract": {"final_allowed": True},
            "planner_may_choose_final": True,
        }
    }
    continuation_action = {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "prompt-context-smoke",
            "offset": 1000,
            "max_chars": 500,
        },
        "batch_window": {
            "document_id": "prompt-context-smoke",
            "offset": 1000,
            "max_chars": 500,
            "full_chars": 1600,
        },
        "reason": "Continue consuming prompt context before final.",
    }

    preserve_required_next_tool_call_for_prompt(
        payload,
        {
            "candidate_next_actions": [continuation_action],
            "finalization_contract": {"final_allowed": False},
            "required_next_progress": "Continue consuming prompt context before final.",
            "planner_may_choose_final": False,
        },
    )

    evidence = payload["evidence_contract"]
    assert payload["required_next_tool_call"]["arguments"]["offset"] == 1000
    assert evidence["finalization_contract"]["final_allowed"] is False
    assert evidence["planner_may_choose_final"] is False
    assert evidence["micro_batch_contract"]["allowed"] is True


def test_valid_support_primitive_is_allowed_during_final_required_gate() -> None:
    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "runtime_sqlite_memory_write",
            "arguments": {
                "kind": "turn_note",
                "tag": "analysis",
                "text": "validated temporary planner note",
            },
            "allowed_tool_names": ["runtime_sqlite_memory_write"],
            "allowed_native_tool_names": ["runtime_sqlite_memory_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "runtime_sqlite_memory_write"}},
        },
        [],
        deps=_deps(),
        config=_config(),
    )

    assert result["ok"] is True
    assert "final_required_tool_call_disallowed" not in result["violations"]


def test_invalid_support_primitive_still_fails_validation() -> None:
    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "planner_scratchpad_write",
            "arguments": {"kind": "turn_note"},
            "allowed_tool_names": ["planner_scratchpad_write"],
            "allowed_native_tool_names": ["planner_scratchpad_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_write"}},
        },
        [],
        deps=_deps(),
        config=_config(),
    )

    assert result["ok"] is False
    assert "planner_scratchpad_write_missing_text" in result["violations"]


def test_answer_chunk_requires_final_composition_contract() -> None:
    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "planner_scratchpad_write",
            "arguments": {
                "kind": "answer_chunk",
                "tag": "analysis-part-1",
                "text": "Section 1 of a large final answer.",
            },
            "allowed_tool_names": ["planner_scratchpad_write"],
            "allowed_native_tool_names": ["planner_scratchpad_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_write"}},
        },
        [],
        deps=_deps(),
        config=_config(),
    )

    assert result["ok"] is False
    assert "planner_answer_chunk_without_final_composition_contract" in result["violations"]


def test_answer_chunk_rejects_terminal_payload_shape_even_when_contract_allows_it() -> None:
    deps = _deps()
    deps["final_composition_tool_names_from_candidates"] = lambda contract: {"planner_scratchpad_write"}

    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "planner_scratchpad_write",
            "arguments": {
                "kind": "answer_chunk",
                "tag": "analysis-part-1",
                "text": "{\"final_answer\":\"complete answer incorrectly wrapped in a tool\"}",
            },
            "allowed_tool_names": ["planner_scratchpad_write"],
            "allowed_native_tool_names": ["planner_scratchpad_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_write"}},
        },
        [],
        deps=deps,
        config=_config(),
    )

    assert result["ok"] is False
    assert "planner_answer_chunk_tool_misused_for_terminal_payload" in result["violations"]


def test_answer_chunk_section_is_allowed_when_final_composition_contract_allows_it() -> None:
    deps = _deps()
    deps["final_composition_tool_names_from_candidates"] = lambda contract: {"planner_scratchpad_write"}

    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "planner_scratchpad_write",
            "arguments": {
                "kind": "answer_chunk",
                "tag": "analysis-part-1",
                "text": "Section 1: evidence and limits.",
            },
            "allowed_tool_names": ["planner_scratchpad_write"],
            "allowed_native_tool_names": ["planner_scratchpad_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_write"}},
        },
        [],
        deps=deps,
        config=_config(),
    )

    assert result["ok"] is True
    assert result["violations"] == []


def test_code_product_build_state_support_write_requires_code_product_contract() -> None:
    deps = _deps()
    deps["code_product_build_state_parse"] = lambda text: {
        "target_file": "services/example.py",
        "status": "collecting_source",
        "notes": ["progress"],
    }
    deps["code_product_build_state_has_collecting_progress"] = lambda state: True

    result = validate_planner_decision_against_evidence(
        "read-only technical analysis",
        {
            "action": "tool",
            "tool": "planner_scratchpad_write",
            "arguments": {
                "kind": "code_product_build_state",
                "target_file": "services/example.py",
                "text": "{\"target_file\":\"services/example.py\",\"status\":\"collecting_source\"}",
            },
            "allowed_tool_names": ["planner_scratchpad_write"],
            "allowed_native_tool_names": ["planner_scratchpad_write"],
            "native_tool_call": True,
            "raw_native_tool_call": {"function": {"name": "planner_scratchpad_write"}},
        },
        [],
        deps=deps,
        config=_config(),
    )

    assert result["ok"] is False
    assert "code_product_build_state_write_outside_code_product_contract" in result["violations"]
