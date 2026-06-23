"""Test action_validators per-action validation logic."""

import pytest


class TestValidateToolArguments:
    """Test validate_tool_arguments per-tool argument checks."""

    def test_repo_search_missing_query(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "repo_search", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "repo_search_missing_query_pattern_or_symbol" in violations

    def test_repo_search_with_query_ok(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "repo_search", {"query": "test"}, violations,
            any_argument_group_present=lambda a, g: True,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "repo_search_missing_query_pattern_or_symbol" not in violations

    def test_repo_read_missing_path(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "repo_read", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "repo_read_missing_path_or_paths_items" in violations

    def test_planner_scratchpad_write_missing_text(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "planner_scratchpad_write", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "planner_scratchpad_write_missing_text" in violations

    def test_planner_scratchpad_read_missing_selector(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "planner_scratchpad_read", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "planner_scratchpad_read_missing_selector" in violations

    def test_unknown_tool_no_violations(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "unknown_tool", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert violations == []

    def test_repo_semantic_search_missing_query(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "repo_semantic_search", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "repo_semantic_search_missing_query" in violations

    def test_repo_rg_search_missing_pattern(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_tool_arguments
        violations: list[str] = []
        validate_tool_arguments(
            "repo_rg_search", {}, violations,
            any_argument_group_present=lambda a, g: False,
            argument_value_present=lambda a, k: False,
            repo_read_selector_present=lambda a: False,
            planner_scratchpad_read_selector_present=lambda a: False,
        )
        assert "repo_rg_search_missing_pattern" in violations


class TestValidateScratchpadWrite:
    """Test validate_scratchpad_write special checks."""

    def test_non_answer_chunk_kind_returns_ok(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_scratchpad_write
        violations: list[str] = []
        validate_scratchpad_write(
            {"kind": "other_kind", "text": "content"}, violations,
            contract={},
            final_composition_tool_names_from_candidates=lambda c: [],
            successful_answer_chunk_signatures=set(),
        )
        assert violations == []

    def test_answer_chunk_without_final_composition(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_scratchpad_write
        violations: list[str] = []
        validate_scratchpad_write(
            {"kind": "answer_chunk", "text": "content"}, violations,
            contract={},
            final_composition_tool_names_from_candidates=lambda c: [],
            successful_answer_chunk_signatures=set(),
        )
        assert "planner_answer_chunk_without_final_composition_contract" in violations

    def test_answer_chunk_with_final_composition_ok(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_scratchpad_write
        violations: list[str] = []
        validate_scratchpad_write(
            {"kind": "answer_chunk", "text": "content"}, violations,
            contract={},
            final_composition_tool_names_from_candidates=lambda c: ["planner_scratchpad_write"],
            successful_answer_chunk_signatures=set(),
        )
        assert "planner_answer_chunk_without_final_composition_contract" not in violations

    def test_answer_chunk_tag_already_written(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_scratchpad_write
        violations: list[str] = []
        validate_scratchpad_write(
            {"kind": "answer_chunk", "text": "content", "tag": "my_tag"}, violations,
            contract={},
            final_composition_tool_names_from_candidates=lambda c: ["planner_scratchpad_write"],
            successful_answer_chunk_signatures={"answer_chunk:my_tag"},
        )
        assert "planner_answer_chunk_tag_already_written_without_progress" in violations

    def test_answer_chunk_misuses_terminal_payload(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import validate_scratchpad_write
        violations: list[str] = []
        validate_scratchpad_write(
            {"kind": "answer_chunk", "text": '{"final_answer": "test"}'}, violations,
            contract={},
            final_composition_tool_names_from_candidates=lambda c: ["planner_scratchpad_write"],
            successful_answer_chunk_signatures=set(),
        )
        assert "planner_answer_chunk_tool_misused_for_terminal_payload" in violations


class TestCheckTerminalBlockDisallowsFinal:
    """Test _check_terminal_block_disallows_final internal helper."""

    def test_terminal_block_latch_disallows_final(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_terminal_block_disallows_final
        violations: list[str] = []
        contract: dict = {
            "final_rewrite_latch": "terminal_block_required",
            "planner_may_choose_block": True,
        }
        final_contract: dict = {}
        result = _check_terminal_block_disallows_final(violations, contract, final_contract)
        assert result[1] is True
        assert "terminal_block_required_final_disallowed" in violations

    def test_planner_forced_block_disallows_final(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_terminal_block_disallows_final
        violations: list[str] = []
        contract: dict = {}
        final_contract: dict = {
            "planner_forced_terminal_block": True,
            "planner_forced_terminal_block_reason": "test reason",
        }
        result = _check_terminal_block_disallows_final(violations, contract, final_contract)
        assert result[1] is True
        assert "terminal_block_required_final_disallowed" in violations

    def test_normal_state_allows_final(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_terminal_block_disallows_final
        violations: list[str] = []
        contract: dict = {
            "final_rewrite_latch": "inactive",
            "planner_may_choose_block": False,
        }
        final_contract: dict = {}
        result = _check_terminal_block_disallows_final(violations, contract, final_contract)
        assert result[1] is False
        assert violations == []


class TestExtractForcedBlock:
    """Test _extract_forced_block internal helper."""

    def test_dict_payload_with_enabled(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _extract_forced_block
        final_contract: dict = {
            "planner_forced_terminal_block": {"enabled": True, "reason": "test reason"},
        }
        forced, reason = _extract_forced_block(final_contract)
        assert forced is True
        assert reason == "test reason"

    def test_bool_payload_true(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _extract_forced_block
        final_contract: dict = {
            "planner_forced_terminal_block": True,
            "planner_forced_terminal_block_reason": "test reason",
        }
        forced, reason = _extract_forced_block(final_contract)
        assert forced is True
        assert reason == "test reason"

    def test_no_forced_block(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _extract_forced_block
        final_contract: dict = {}
        forced, reason = _extract_forced_block(final_contract)
        assert forced is False
        assert reason == ""


class TestApplyCoverageBlock:
    """Test _apply_coverage_block internal helper."""

    def test_coverage_block_applied(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _apply_coverage_block
        contract: dict = {}
        final_contract: dict = {}
        _apply_coverage_block(contract, final_contract)
        assert "required_next_progress" in contract
        assert "coverage_block" in contract
        assert contract["planner_may_choose_final"] is False
        assert final_contract["final_allowed"] is False
        assert final_contract["planner_may_choose_final"] is False


class TestFinalAnswerDeclaresMissingCoverage:
    """Test _final_answer_declares_missing_coverage internal helper."""

    def test_coverage_satisfied_false_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _final_answer_declares_missing_coverage
        assert _final_answer_declares_missing_coverage("coverage_satisfied=false") is True
        assert _final_answer_declares_missing_coverage("coverage_satisfied: false") is True
        assert _final_answer_declares_missing_coverage('"coverage_satisfied": false') is True

    def test_missing_coverage_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _final_answer_declares_missing_coverage
        assert _final_answer_declares_missing_coverage("missing_owner_paths") is True
        assert _final_answer_declares_missing_coverage("missing coverage") is True
        assert _final_answer_declares_missing_coverage("insufficient coverage") is True
        assert _final_answer_declares_missing_coverage("copertura mancante") is True
        assert _final_answer_declares_missing_coverage("mancanza di copertura") is True

    def test_normal_text_not_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _final_answer_declares_missing_coverage
        assert _final_answer_declares_missing_coverage("test complete") is False
        assert _final_answer_declares_missing_coverage("") is False
        assert _final_answer_declares_missing_coverage(None) is False


class TestAnswerChunkMisusesTerminalPayloadShape:
    """Test _answer_chunk_misuses_terminal_payload_shape internal helper."""

    def test_json_with_final_answer_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _answer_chunk_misuses_terminal_payload_shape
        assert _answer_chunk_misuses_terminal_payload_shape('{"final_answer": "test"}') is True
        assert _answer_chunk_misuses_terminal_payload_shape('{"answer": "test"}') is True
        assert _answer_chunk_misuses_terminal_payload_shape('{"summary": "test"}') is True

    def test_plain_text_not_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _answer_chunk_misuses_terminal_payload_shape
        assert _answer_chunk_misuses_terminal_payload_shape("plain text") is False
        assert _answer_chunk_misuses_terminal_payload_shape("") is False

    def test_json_without_terminal_keys_not_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _answer_chunk_misuses_terminal_payload_shape
        assert _answer_chunk_misuses_terminal_payload_shape('{"kind": "answer_chunk"}') is False
        assert _answer_chunk_misuses_terminal_payload_shape('{"tag": "test"}') is False


class TestCheckPlannerFormatFailures:
    """Test _check_planner_format_failures internal helper."""

    def test_empty_output_failure(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_planner_format_failures
        violations: list[str] = []
        contract: dict = {}
        result = _check_planner_format_failures(
            "planner_final_required_empty_output",
            "planner_final_required_empty_output",
            violations, contract
        )
        assert result is not None
        assert "planner_final_required_empty_output" in result[0]

    def test_native_tool_call_required(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_planner_format_failures
        violations: list[str] = []
        contract: dict = {}
        result = _check_planner_format_failures(
            "planner_native_tool_call_required",
            "planner_native_tool_call_required",
            violations, contract
        )
        assert result is not None
        assert "planner_native_tool_call_required" in result[0]

    def test_non_json_output_failure(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_planner_format_failures
        violations: list[str] = []
        contract: dict = {}
        result = _check_planner_format_failures(
            "planner_native_mode_non_json_output",
            "planner_native_mode_non_json_output",
            violations, contract
        )
        assert result is not None
        assert "planner_native_mode_non_json_output" in result[0]

    def test_unknown_reason_returns_none(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _check_planner_format_failures
        violations: list[str] = []
        contract: dict = {}
        result = _check_planner_format_failures(
            "unknown_reason",
            "unknown_reason",
            violations, contract
        )
        assert result is None


class TestIsDegenerateOutput:
    """Test _is_degenerate_output internal helper."""

    def test_invalid_planner_output(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("invalid_planner_output_non_json", "invalid_planner_output_non_json") is True

    def test_non_json_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("some non-json output", "some non-json output") is True
        # "no json here" doesn't contain any of the specific needles
        assert _is_degenerate_output("no json here", "no json here") is False

    def test_degenerate_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("degenerate output", "degenerate output") is True

    def test_timeout_detected(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("timeout occurred", "timeout occurred") is True

    def test_planner_degenerate_prefix(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("PLANNER_DEGENERATE_OUTPUT", "planner_degenerate_output") is True

    def test_normal_reason_not_degenerate(self) -> None:
        from aicarmine_broker.application.planner.validator.action_validators import _is_degenerate_output
        assert _is_degenerate_output("normal reason", "normal reason") is False
        assert _is_degenerate_output("quality gate satisfied", "quality gate satisfied") is False