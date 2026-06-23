"""Test contract_utils read-only contract helpers."""

import pytest


class TestKnownContractRepoPaths:
    """Test known_contract_repo_paths extraction."""

    def test_empty_contract_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_paths
        assert known_contract_repo_paths({}) == set()
        assert known_contract_repo_paths(None) == set()

    def test_standard_path_keys_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_paths
        contract: dict = {
            "validator_admissible_repo_read_paths": ["services/test.py"],
            "read_admissible_paths": ["src/main.py"],
            "successful_repo_read_paths": ["tools/util.py"],
            "verified_content_reads": [{"path": "cache/data.json"}],
            "covered_owner_paths": ["docs/readme.md"],
            "candidate_owner_paths": ["config/settings.yaml"],
            "missing_owner_paths": ["missing/file.py"],
        }
        result = known_contract_repo_paths(contract)
        assert result == {
            "services/test.py", "src/main.py", "tools/util.py",
            "cache/data.json", "docs/readme.md", "config/settings.yaml",
            "missing/file.py",
        }

    def test_coverage_subcontract_paths_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_paths
        contract: dict = {
            "minimum_read_coverage": {
                "covered_owner_paths": ["coverage/covered.py"],
                "candidate_owner_paths": ["coverage/candidate.py"],
                "missing_owner_paths": ["coverage/missing.py"],
            }
        }
        result = known_contract_repo_paths(contract)
        assert result == {"coverage/covered.py", "coverage/candidate.py", "coverage/missing.py"}

    def test_finalization_contract_coverage_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_paths
        contract: dict = {
            "finalization_contract": {
                "minimum_read_coverage": {
                    "covered_owner_paths": ["final/covered.py"],
                    "candidate_owner_paths": ["final/candidate.py"],
                    "missing_owner_paths": ["final/missing.py"],
                }
            }
        }
        result = known_contract_repo_paths(contract)
        assert result == {"final/covered.py", "final/candidate.py", "final/missing.py"}

    def test_dot_paths_filtered(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_paths
        contract: dict = {
            "validator_admissible_repo_read_paths": ["."],
        }
        result = known_contract_repo_paths(contract)
        assert result == set()


class TestKnownContractRepoDirs:
    """Test known_contract_repo_dirs directory derivation."""

    def test_root_always_included(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_dirs
        result = known_contract_repo_dirs({})
        assert result == {"."}

    def test_ancestor_dirs_derived(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_dirs
        contract: dict = {
            "validator_admissible_repo_read_paths": ["services/aicarmine_broker/file.py"],
        }
        result = known_contract_repo_dirs(contract)
        assert result == {".", "services", "services/aicarmine_broker"}

    def test_multiple_paths_derive_dirs(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import known_contract_repo_dirs
        contract: dict = {
            "validator_admissible_repo_read_paths": [
                "services/test.py",
                "src/main.py",
            ]
        }
        result = known_contract_repo_dirs(contract)
        assert result == {".", "services", "src"}


class TestFinalQualityRepoReadAllowlist:
    """Test final_quality_repo_read_allowlist building."""

    def test_empty_contract_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        assert final_quality_repo_read_allowlist({}) == set()
        assert final_quality_repo_read_allowlist(None) == set()

    def test_standard_keys_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        contract: dict = {
            "validator_admissible_repo_read_paths": ["services/test.py"],
            "read_admissible_paths": ["src/main.py"],
            "successful_repo_read_paths": ["tools/util.py"],
        }
        result = final_quality_repo_read_allowlist(contract)
        assert result == {"services/test.py", "src/main.py", "tools/util.py"}

    def test_verified_content_reads_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        contract: dict = {
            "verified_content_reads": [
                {"path": "verified/file1.py"},
                {"repo_path": "verified/file2.py"},
            ]
        }
        result = final_quality_repo_read_allowlist(contract)
        assert result == {"verified/file1.py", "verified/file2.py"}

    def test_file_memory_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        contract: dict = {
            "file_memory": [
                {"path": "memory/file.py", "mentioned_paths": ["memory/dep.py"]},
            ]
        }
        result = final_quality_repo_read_allowlist(contract)
        assert result == {"memory/file.py", "memory/dep.py"}

    def test_read_notes_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        contract: dict = {
            "operational_notes": {
                "read_notes": [
                    {"path": "notes/file.py", "mentioned_paths": ["notes/dep.py"]},
                ]
            }
        }
        result = final_quality_repo_read_allowlist(contract)
        assert result == {"notes/file.py", "notes/dep.py"}

    def test_dict_values_extracted(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import final_quality_repo_read_allowlist
        contract: dict = {
            "validator_admissible_repo_read_paths": {
                "key1": {"path": "dict/path1.py"},
                "key2": {"repo_path": "dict/path2.py"},
            }
        }
        result = final_quality_repo_read_allowlist(contract)
        assert result == {"dict/path1.py", "dict/path2.py"}


class TestMinimumReadCoverageContract:
    """Test minimum_read_coverage_contract extraction."""

    def test_empty_contract_returns_empty_dict(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import minimum_read_coverage_contract
        assert minimum_read_coverage_contract({}) == {}

    def test_contract_coverage_returned(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import minimum_read_coverage_contract
        contract: dict = {"minimum_read_coverage": {"required": True}}
        assert minimum_read_coverage_contract(contract) == {"required": True}

    def test_finalization_coverage_returned(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import minimum_read_coverage_contract
        contract: dict = {
            "finalization_contract": {
                "minimum_read_coverage": {"required": False}
            }
        }
        assert minimum_read_coverage_contract(contract) == {"required": False}

    def test_contract_coverage_preferred(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import minimum_read_coverage_contract
        contract: dict = {
            "minimum_read_coverage": {"source": "contract"},
            "finalization_contract": {
                "minimum_read_coverage": {"source": "finalization"}
            }
        }
        assert minimum_read_coverage_contract(contract) == {"source": "contract"}


class TestIsCoverageRequired:
    """Test is_coverage_required logic."""

    def test_coverage_not_satisfied_required(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_required
        contract: dict = {"coverage_satisfied": False}
        assert is_coverage_required(contract) is True

    def test_coverage_satisfied_not_required(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_required
        contract: dict = {"coverage_satisfied": True}
        assert is_coverage_required(contract) is False

    def test_coverage_required_true(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_required
        contract: dict = {"minimum_read_coverage": {"required": True}}
        assert is_coverage_required(contract) is True

    def test_coverage_not_satisfied_default(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_required
        # When minimum_read_coverage.required is False, is_coverage_required returns False
        # (coverage is explicitly not required)
        contract: dict = {"minimum_read_coverage": {"required": False}}
        assert is_coverage_required(contract) is False


class TestIsCoverageSatisfied:
    """Test is_coverage_satisfied logic."""

    def test_coverage_satisfied_true(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_satisfied
        contract: dict = {"coverage_satisfied": True}
        assert is_coverage_satisfied(contract) is True

    def test_coverage_satisfied_false(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_satisfied
        contract: dict = {"coverage_satisfied": False}
        assert is_coverage_satisfied(contract) is False

    def test_coverage_satisfied_in_coverage_dict(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_satisfied
        contract: dict = {"minimum_read_coverage": {"coverage_satisfied": True}}
        assert is_coverage_satisfied(contract) is True

    def test_coverage_not_satisfied_in_coverage_dict(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import is_coverage_satisfied
        contract: dict = {"minimum_read_coverage": {"coverage_satisfied": False}}
        assert is_coverage_satisfied(contract) is False


class TestMissingCoverageOwnerPaths:
    """Test missing_coverage_owner_paths extraction."""

    def test_empty_contract_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import missing_coverage_owner_paths
        assert missing_coverage_owner_paths({}) == []

    def test_coverage_dict_missing_paths(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import missing_coverage_owner_paths
        contract: dict = {"minimum_read_coverage": {"missing_owner_paths": ["a.py", "b.py"]}}
        assert missing_coverage_owner_paths(contract) == ["a.py", "b.py"]

    def test_top_level_missing_paths(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import missing_coverage_owner_paths
        contract: dict = {"missing_owner_paths": ["top/file.py"]}
        assert missing_coverage_owner_paths(contract) == ["top/file.py"]

    def test_non_list_missing_paths_returns_empty(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import missing_coverage_owner_paths
        contract: dict = {"minimum_read_coverage": {"missing_owner_paths": "not_a_list"}}
        assert missing_coverage_owner_paths(contract) == []


class TestRequiredNextRouteHasDeterministicProof:
    """Test required_next_route_has_deterministic_proof verification."""

    def test_repo_read_always_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof({"tool": "repo_read"}, contract) is True

    def test_repo_list_files_root_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_list_files", "arguments": {"path": "."}}, contract
        ) is True

    def test_repo_list_files_known_dir_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {"validator_admissible_repo_read_paths": ["services/test.py"]}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_list_files", "arguments": {"path": "services"}}, contract
        ) is True

    def test_repo_list_files_unknown_dir_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_list_files", "arguments": {"path": "unknown"}}, contract
        ) is False

    def test_repo_list_files_prose_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_list_files", "arguments": {"path": "docs/config"}}, contract
        ) is False

    def test_repo_search_with_concrete_query_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_semantic_search", "arguments": {"query": "test function"}}, contract
        ) is True

    def test_repo_search_with_bad_query_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_semantic_search", "arguments": {"query": "8/2"}}, contract
        ) is False

    def test_repo_search_unknown_path_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "repo_semantic_search", "arguments": {"query": "test", "path": "unknown"}}, contract
        ) is False

    def test_scratchpad_read_with_document_id_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "planner_scratchpad_read", "arguments": {"document_id": "prompt_context"}}, contract
        ) is True

    def test_scratchpad_read_with_target_file_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {"validator_admissible_repo_read_paths": ["services/test.py"]}
        assert required_next_route_has_deterministic_proof(
            {"tool": "planner_scratchpad_read", "arguments": {"target_file": "services/test.py"}}, contract
        ) is True

    def test_unknown_tool_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof(
            {"tool": "unknown_tool"}, contract
        ) is False

    def test_empty_required_call_not_proven(self) -> None:
        from aicarmine_broker.application.planner.validator.contract_utils import required_next_route_has_deterministic_proof
        contract: dict = {}
        assert required_next_route_has_deterministic_proof({}, contract) is False