"""Test validate_decision orchestrator helpers."""

import pytest


class TestNormalizeTerminalPlannerDecision:
    """Test _normalize_terminal_planner_decision lazy-import pattern.
    
    NOTE: This function uses lazy imports that require the full broker context,
    so we skip direct testing and verify the module imports correctly instead.
    """

    def test_function_exists(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _normalize_terminal_planner_decision
        assert callable(_normalize_terminal_planner_decision)


class TestListOrEmpty:
    """Test _list_or_empty list normalization."""

    def test_list_returns_as_is(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _list_or_empty
        assert _list_or_empty([1, 2, 3]) == [1, 2, 3]

    def test_none_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _list_or_empty
        assert _list_or_empty(None) == []

    def test_string_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _list_or_empty
        assert _list_or_empty("not_a_list") == []

    def test_dict_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _list_or_empty
        assert _list_or_empty({"key": "value"}) == []


class TestRepoPathIsConcrete:
    """Test _repo_path_is_concrete delegation."""

    def test_python_file_is_concrete(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _repo_path_is_concrete
        assert _repo_path_is_concrete("services/test.py") is True

    def test_placeholder_is_not_concrete(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _repo_path_is_concrete
        assert _repo_path_is_concrete("services") is False


class TestCoalesceRepoReadPaths:
    """Test _coalesce_repo_read_paths delegation."""

    def test_list_deduplicated(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _coalesce_repo_read_paths
        result = _coalesce_repo_read_paths(["a.py", "b.py", "a.py"])
        assert result == ["a.py", "b.py"]

    def test_none_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _coalesce_repo_read_paths
        assert _coalesce_repo_read_paths(None) == []


class TestNextFinalRewriteLatch:
    """Test _next_final_rewrite_latch delegation."""

    def test_inactive_to_rewrite(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _next_final_rewrite_latch
        result = _next_final_rewrite_latch("inactive", reject_count=1, has_gap_route=True)
        assert result == "rewrite_required"

    def test_terminal_block_sticky(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _next_final_rewrite_latch
        result = _next_final_rewrite_latch("terminal_block_required", reject_count=0, has_gap_route=True)
        assert result == "terminal_block_required"


class TestCollectRepoPaths:
    """Test _collect_repo_paths delegation."""

    def test_dict_values_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _collect_repo_paths
        result = _collect_repo_paths({"a": "services/test.py"})
        assert result == {"services/test.py"}

    def test_list_values_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _collect_repo_paths
        result = _collect_repo_paths(["services/test.py", "src/main.py"])
        assert result == {"services/test.py", "src/main.py"}


class TestKnownContractRepoPaths:
    """Test _known_contract_repo_paths delegation."""

    def test_empty_contract_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _known_contract_repo_paths
        assert _known_contract_repo_paths({}) == set()

    def test_standard_keys_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _known_contract_repo_paths
        contract: dict = {"validator_admissible_repo_read_paths": ["services/test.py"]}
        result = _known_contract_repo_paths(contract)
        assert result == {"services/test.py"}


class TestKnownContractRepoDirs:
    """Test _known_contract_repo_dirs delegation."""

    def test_root_always_included(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _known_contract_repo_dirs
        result = _known_contract_repo_dirs({})
        assert result == {"."}

    def test_ancestor_dirs_derived(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _known_contract_repo_dirs
        contract: dict = {"validator_admissible_repo_read_paths": ["services/aicarmine_broker/file.py"]}
        result = _known_contract_repo_dirs(contract)
        assert result == {".", "services", "services/aicarmine_broker"}


class TestFinalQualityRepoReadAllowlist:
    """Test _final_quality_repo_read_allowlist delegation."""

    def test_empty_contract_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _final_quality_repo_read_allowlist
        assert _final_quality_repo_read_allowlist({}) == set()

    def test_standard_keys_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _final_quality_repo_read_allowlist
        contract: dict = {"validator_admissible_repo_read_paths": ["services/test.py"]}
        result = _final_quality_repo_read_allowlist(contract)
        assert result == {"services/test.py"}


class TestClearFinalTerminalBlockState:
    """Test _clear_final_terminal_block_state delegation."""

    def test_clear_resets_latch(self) -> None:
        from aicarmine_broker.application.planner.validator.validate_decision import _clear_final_terminal_block_state
        contract: dict = {"final_rewrite_latch": "terminal_block_required"}
        result = _clear_final_terminal_block_state(contract)
        assert result["final_rewrite_latch"] == "inactive"
        assert result["planner_may_choose_block"] is False
        assert result["planner_may_choose_final"] is True