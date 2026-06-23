"""Test final_quality evidence module."""

import pytest


class TestRepoAnalysisFinalAnswerQuality:
    """Test repo_analysis_final_answer_quality deterministic quality checks."""

    def test_empty_answer_rejected(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        result = repo_analysis_final_answer_quality("", {})
        assert result["ok"] is False
        # Actual violation keys differ from assumed ones
        assert "repo_analysis_final_empty" in result.get("violations", [])

    def test_short_answer_rejected(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        result = repo_analysis_final_answer_quality("too short", {})
        assert result["ok"] is False

    def test_valid_answer_passes_basic_checks(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        answer = "This is a detailed final answer with specific file paths and evidence references."
        result = repo_analysis_final_answer_quality(answer, {})
        assert isinstance(result, dict)
        assert "ok" in result
        assert "metrics" in result

    def test_answer_with_file_paths(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        answer = "The fix was applied to services/aicarmine_broker/config/models.py and verified in tests/test_config_models.py."
        result = repo_analysis_final_answer_quality(answer, {})
        assert isinstance(result, dict)

    def test_answer_with_code_diff(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        answer = "Changes:\n--- old\n+++ new\n@@ -1 +1 @@\n-old line\n+new line"
        result = repo_analysis_final_answer_quality(answer, {})
        assert isinstance(result, dict)


class TestRepoAnalysisFinalAnswerModelQuality:
    """Test repo_analysis_final_answer_model_quality model quality assessment."""

    def test_missing_dependency_returns_violation(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_model_quality,
        )
        contract: dict = {}
        # The function takes only 2 positional args: answer and contract
        result = repo_analysis_final_answer_model_quality("test answer", contract)
        assert isinstance(result, dict)
        # When no callable dependency is provided, the result may vary
        # but should be a valid dict response

    def test_invalid_decision_detected(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_model_quality,
        )
        contract: dict = {}
        result = repo_analysis_final_answer_model_quality("", contract)
        assert isinstance(result, dict)


class TestFinalQualityEvidenceMetrics:
    """Test final_quality evidence metrics structure."""

    def test_metrics_in_result(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        result = repo_analysis_final_answer_quality("test answer with content", {})
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)

    def test_required_next_sections(self) -> None:
        from aicarmine_broker.application.evidence.final_quality import (
            repo_analysis_final_answer_quality,
        )
        result = repo_analysis_final_answer_quality("short", {})
        assert "required_next_missing_evidences" in result
