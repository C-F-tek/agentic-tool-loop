"""Test evidence module exports and functions."""

import pytest


class TestEvidenceGoalClassifier:
    """Test evidence.goal_classifier exports."""

    def test_goal_requires_code_product_report_true(self) -> None:
        """Test goal_requires_code_product_report returns True for code_product goals."""
        from aicarmine_broker.application.evidence.goal_classifier import goal_requires_code_product_report
        assert goal_requires_code_product_report("code_product report") is True
        assert goal_requires_code_product_report("generate a diff") is True

    def test_goal_requires_code_product_report_false(self) -> None:
        """Test goal_requires_code_product_report returns False for non-code goals."""
        from aicarmine_broker.application.evidence.goal_classifier import goal_requires_code_product_report
        assert goal_requires_code_product_report("simple task") is False
        assert goal_requires_code_product_report("read a file") is False


class TestEvidenceRequiredWorkingSet:
    """Test evidence.required_working_set exports."""

    def test_repo_readable_evidence_file_empty(self) -> None:
        """Test repo_readable_evidence_file with empty history."""
        from aicarmine_broker.application.evidence.required_working_set import repo_readable_evidence_file
        result = repo_readable_evidence_file([], "test.py")
        assert result == {}

    def test_repo_readable_evidence_file_returns_dict(self) -> None:
        """Test repo_readable_evidence_file returns dict type."""
        from aicarmine_broker.application.evidence.required_working_set import repo_readable_evidence_file
        result = repo_readable_evidence_file([], "test.py")
        assert isinstance(result, dict)


class TestEvidenceExecutionDigest:
    """Test evidence.execution_digest exports."""

    def test_latest_file_list_result_empty(self) -> None:
        """Test latest_file_list_result with empty history."""
        from aicarmine_broker.application.evidence.execution_digest import latest_file_list_result
        result = latest_file_list_result([], "test.py")
        assert result == {}

    def test_latest_file_list_result_returns_dict(self) -> None:
        """Test latest_file_list_result returns dict type."""
        from aicarmine_broker.application.evidence.execution_digest import latest_file_list_result
        result = latest_file_list_result([], "test.py")
        assert isinstance(result, dict)


class TestEvidenceFinalQuality:
    """Test evidence.final_quality exports."""

    def test_repo_analysis_final_answer_model_quality_basic(self) -> None:
        """Test repo_analysis_final_answer_model_quality returns dict."""
        from aicarmine_broker.application.evidence.final_quality import repo_analysis_final_answer_model_quality
        result = repo_analysis_final_answer_model_quality("test goal", [])
        assert isinstance(result, dict)
        assert result.get("schema") == "repo_analysis_final_answer_model_quality.v1"

    def test_repo_analysis_final_answer_model_quality_with_history(self) -> None:
        """Test repo_analysis_final_answer_model_quality with history."""
        from aicarmine_broker.application.evidence.final_quality import repo_analysis_final_answer_model_quality
        result = repo_analysis_final_answer_model_quality("test goal", [{"step": 1}], target_kind="file")
        assert isinstance(result, dict)
        assert result.get("history_count") == 1


class TestEvidenceAuditGuidance:
    """Test evidence.audit_guidance exports."""

    def test_import_audit_guidance(self) -> None:
        """Test audit_guidance can be imported."""
        from aicarmine_broker.application.evidence.audit_guidance import (
            audit_guidance_for_goal,
            final_audit_red_flags,
            goal_requests_semantic_audit,
            pending_read_or_search_actions,
            role_guidance_for_goal,
        )
        assert callable(audit_guidance_for_goal)
        assert callable(final_audit_red_flags)
        assert callable(goal_requests_semantic_audit)
        assert callable(pending_read_or_search_actions)
        assert callable(role_guidance_for_goal)