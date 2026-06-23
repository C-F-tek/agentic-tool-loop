"""Test rewrite_latch state-machine helpers."""

import pytest


class TestCoerceLatchState:
    """Test coerce_latch_state normalisation."""

    def test_coerce_valid_inactive(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import coerce_latch_state
        assert coerce_latch_state("inactive") == "inactive"
        assert coerce_latch_state("INACTIVE") == "inactive"
        assert coerce_latch_state("  inactive  ") == "inactive"

    def test_coerce_valid_rewrite_required(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import coerce_latch_state
        assert coerce_latch_state("rewrite_required") == "rewrite_required"
        assert coerce_latch_state("REWRITE_REQUIRED") == "rewrite_required"

    def test_coerce_valid_required_gap_only(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import coerce_latch_state
        assert coerce_latch_state("required_gap_only") == "required_gap_only"
        assert coerce_latch_state("REQUIRED_GAP_ONLY") == "required_gap_only"

    def test_coerce_valid_terminal_block_required(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import coerce_latch_state
        assert coerce_latch_state("terminal_block_required") == "terminal_block_required"
        assert coerce_latch_state("TERMINAL_BLOCK_REQUIRED") == "terminal_block_required"

    def test_coerce_invalid_returns_inactive(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import coerce_latch_state
        assert coerce_latch_state("invalid_state") == "inactive"
        assert coerce_latch_state("") == "inactive"
        assert coerce_latch_state(None) == "inactive"
        assert coerce_latch_state(123) == "inactive"
        assert coerce_latch_state("unknown") == "inactive"


class TestNextLatchState:
    """Test next_latch_state transitions."""

    def test_terminal_block_is_sticky(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("terminal_block_required", reject_count=0, has_gap_route=True) == "terminal_block_required"
        assert next_latch_state("terminal_block_required", reject_count=5, has_gap_route=False) == "terminal_block_required"

    def test_first_rejection_starts_rewrite_required(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("inactive", reject_count=1, has_gap_route=True) == "rewrite_required"
        assert next_latch_state("inactive", reject_count=1, has_gap_route=False) == "rewrite_required"

    def test_second_rejection_forces_terminal_block(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("inactive", reject_count=2, has_gap_route=True) == "terminal_block_required"
        assert next_latch_state("inactive", reject_count=10, has_gap_route=False) == "terminal_block_required"

    def test_required_gap_only_with_gap_route(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("required_gap_only", reject_count=0, has_gap_route=True) == "required_gap_only"
        assert next_latch_state("required_gap_only", reject_count=1, has_gap_route=True) == "required_gap_only"

    def test_required_gap_only_without_gap_route(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("required_gap_only", reject_count=0, has_gap_route=False) == "terminal_block_required"
        assert next_latch_state("required_gap_only", reject_count=1, has_gap_route=False) == "terminal_block_required"

    def test_inactive_to_rewrite_required(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("inactive", reject_count=1, has_gap_route=True) == "rewrite_required"
        assert next_latch_state("inactive", reject_count=1, has_gap_route=False) == "rewrite_required"

    def test_rewrite_required_transition(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("rewrite_required", reject_count=0, has_gap_route=True) == "rewrite_required"
        assert next_latch_state("rewrite_required", reject_count=2, has_gap_route=True) == "terminal_block_required"

    def test_string_current_normalized(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import next_latch_state
        assert next_latch_state("INACTIVE", reject_count=1, has_gap_route=True) == "rewrite_required"
        assert next_latch_state("", reject_count=1, has_gap_route=True) == "rewrite_required"
        assert next_latch_state(None, reject_count=1, has_gap_route=True) == "rewrite_required"


class TestEscalateTerminalBlockState:
    """Test escalate_terminal_block_state contract mutations."""

    def test_escalate_cuda_max_exceeded(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 2,
            "final_rewrite_latch": "rewrite_required",
            "planner_cuda_rewrite_required": True,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        # _force_terminal_block sets finalization_contract but not final_rewrite_latch
        assert result["planner_cuda_rewrite_required"] is False
        assert result["finalization_contract"]["final_allowed"] is False
        assert result["finalization_contract"]["planner_may_choose_final"] is False

    def test_escalate_normal_flow(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 0,
            "final_rewrite_latch": "rewrite_required",
            "planner_cuda_rewrite_required": True,
            "planner_final_quality_reject_count": 0,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        assert result["planner_final_quality_reject_count"] == 1
        assert result["final_rewrite_latch"] == "rewrite_required"
        assert result["planner_may_choose_block"] is False
        assert result["finalization_contract"]["reason"] == "planner_cuda_rewrite_required_retry_continue"

    def test_escalate_gap_only_flow(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 0,
            "final_rewrite_latch": "required_gap_only",
            "planner_cuda_rewrite_required": True,
            "planner_final_quality_reject_count": 0,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        assert result["final_rewrite_latch"] == "required_gap_only"
        assert result["finalization_contract"]["reason"] == "planner_cuda_rewrite_required_retry_gap_only"

    def test_escalate_terminal_block_already_set(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 0,
            "final_rewrite_latch": "terminal_block_required",
            "planner_cuda_rewrite_required": True,
            "planner_final_quality_reject_count": 0,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        assert result["planner_may_choose_block"] is True

    def test_escalate_invalid_latch_state(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 0,
            "final_rewrite_latch": "invalid_state",
            "planner_cuda_rewrite_required": True,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        assert result is contract

    def test_escalate_cuda_flag_not_true(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        contract: dict = {
            "planner_rewrite_stuck_count": 0,
            "final_rewrite_latch": "rewrite_required",
            "planner_cuda_rewrite_required": False,
        }
        result = escalate_terminal_block_state(contract, has_gap_route=True)
        assert result is contract

    def test_escalate_empty_contract(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        result = escalate_terminal_block_state({}, has_gap_route=True)
        assert result == {}

    def test_escalate_non_dict_contract(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import escalate_terminal_block_state
        result = escalate_terminal_block_state("not_a_dict", has_gap_route=True)
        assert result == {}


class TestClearTerminalBlockState:
    """Test clear_terminal_block_state contract reset."""

    def test_clear_resets_latch(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        contract: dict = {
            "final_rewrite_latch": "terminal_block_required",
            "planner_may_choose_block": True,
            "planner_may_choose_final": False,
            "planner_cuda_rewrite_required": True,
            "planner_forced_terminal_block": True,
            "required_next_tool_call": {},
        }
        result = clear_terminal_block_state(contract)
        assert result["final_rewrite_latch"] == "inactive"
        assert result["planner_may_choose_block"] is False
        assert result["planner_may_choose_final"] is True
        assert "planner_cuda_rewrite_required" not in result
        assert "planner_forced_terminal_block" not in result
        assert "required_next_tool_call" not in result

    def test_clear_resets_finalization_contract(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        contract: dict = {
            "finalization_contract": {
                "final_allowed": False,
                "planner_may_choose_final": False,
                "planner_may_choose_block": True,
                "reason": "planner_cuda_rewrite_required_repeated_retry_block_required",
            }
        }
        result = clear_terminal_block_state(contract)
        fc = result["finalization_contract"]
        assert fc["final_allowed"] is True
        assert fc["planner_may_choose_final"] is True
        assert fc["planner_may_choose_block"] is False
        assert "reason" not in fc

    def test_clear_removes_stale_reason_codes(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        for stale_reason in (
            "repo_analysis_final_quality_no_runnable_gap_terminal_block",
            "repo_analysis_final_model_quality_rejected_no_runnable_gap",
            "planner_cuda_rewrite_required_repeated_retry_block_required",
            "planner_cuda_rewrite_required_retry_gap_only",
            "planner_cuda_rewrite_required_retry_continue",
            "required_next_tool_call_unknown_tool",
            "required_next_tool_call_not_in_current_surface",
        ):
            contract: dict = {
                "finalization_contract": {"reason": stale_reason}
            }
            result = clear_terminal_block_state(contract)
            assert "reason" not in result["finalization_contract"]

    def test_clear_filters_candidate_next_actions(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        contract: dict = {
            "candidate_next_actions": [
                {"source": "repo_analysis_final_model_quality", "id": 1},
                {"action_id": "repo_analysis_final_quality:test", "id": 2},
                {"source": "other", "id": 3},
            ]
        }
        result = clear_terminal_block_state(contract)
        # Only matching items are filtered; non-matching items remain
        assert result["candidate_next_actions"] == [{"source": "other", "id": 3}]

    def test_clear_keeps_non_matching_actions(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        contract: dict = {
            "candidate_next_actions": [
                {"source": "other", "id": 1},
                {"source": "another", "id": 2},
            ]
        }
        result = clear_terminal_block_state(contract)
        assert result["candidate_next_actions"] == [{"source": "other", "id": 1}, {"source": "another", "id": 2}]

    def test_clear_empty_contract(self) -> None:
        from aicarmine_broker.application.planner.validator.rewrite_latch import clear_terminal_block_state
        result = clear_terminal_block_state({})
        assert result["final_rewrite_latch"] == "inactive"
        assert result["planner_may_choose_block"] is False
        assert result["planner_may_choose_final"] is True