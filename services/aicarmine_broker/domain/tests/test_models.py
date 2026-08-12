#!/usr/bin/env python3
"""Tests for domain/models.py - Consolidated domain models for the 3572 agentic loop."""

from pathlib import Path

import pytest

from aicarmine_broker.domain.models import (
    EvidenceContract,
    EvidenceWindow,
    FinalDecision,
    PlannerDecision,
    PlannerRuntimeConfig,
    ToolDecision,
    ToolEvidence,
    ToolResult,
    ToolSpec,
    ValidationResult,
    AgentJobSnapshot,
    mapping_field_diagnostics,
)


class TestMappingFieldDiagnostics:
    """Tests for mapping_field_diagnostics."""

    def test_valid_mapping(self):
        result = mapping_field_diagnostics("field", {})
        assert result == ()

    def test_none_value(self):
        result = mapping_field_diagnostics("field", None)
        assert result == ("field:missing_mapping",)

    def test_invalid_type(self):
        result = mapping_field_diagnostics("field", "not_a_mapping")
        assert result == ("field:invalid_mapping_type:str",)

    def test_dict_is_valid(self):
        result = mapping_field_diagnostics("field", {"key": "value"})
        assert result == ()


class TestPlannerRuntimeConfig:
    """Tests for PlannerRuntimeConfig dataclass."""

    def test_frozen(self):
        config = PlannerRuntimeConfig(
            planner_url="http://localhost:11434",
            planner_model="qwen3",
            task_url="http://localhost:11434",
            task_model="qwen3",
            num_ctx_requested=8192,
            num_ctx_cap=32768,
            num_ctx_effective=8192,
            prompt_char_budget=16000,
            prompt_compact_threshold_chars=4000,
            generation_headroom_reserve_chars=2000,
        )
        with pytest.raises(Exception):
            config.planner_url = "new"

    def test_defaults(self):
        config = PlannerRuntimeConfig(
            planner_url="url",
            planner_model="model",
            task_url="url",
            task_model="model",
            num_ctx_requested=1,
            num_ctx_cap=1,
            num_ctx_effective=1,
            prompt_char_budget=1,
            prompt_compact_threshold_chars=1,
            generation_headroom_reserve_chars=1,
        )
        assert config.planner_url == "url"

    def test_validation_diagnostics_missing_url(self):
        config = PlannerRuntimeConfig(
            planner_url="",
            planner_model="model",
            task_url="url",
            task_model="model",
            num_ctx_requested=1,
            num_ctx_cap=1,
            num_ctx_effective=1,
            prompt_char_budget=1,
            prompt_compact_threshold_chars=1,
            generation_headroom_reserve_chars=1,
        )
        diagnostics = config.validation_diagnostics()
        assert any("planner_url:missing" in d for d in diagnostics)

    def test_validation_diagnostics_invalid_integer(self):
        config = PlannerRuntimeConfig(
            planner_url="url",
            planner_model="model",
            task_url="url",
            task_model="model",
            num_ctx_requested="not_int",
            num_ctx_cap=1,
            num_ctx_effective=1,
            prompt_char_budget=1,
            prompt_compact_threshold_chars=1,
            generation_headroom_reserve_chars=1,
        )
        diagnostics = config.validation_diagnostics()
        assert any("num_ctx_requested:invalid_integer" in d for d in diagnostics)

    def test_validation_diagnostics_not_positive(self):
        config = PlannerRuntimeConfig(
            planner_url="url",
            planner_model="model",
            task_url="url",
            task_model="model",
            num_ctx_requested=-1,
            num_ctx_cap=1,
            num_ctx_effective=1,
            prompt_char_budget=1,
            prompt_compact_threshold_chars=1,
            generation_headroom_reserve_chars=1,
        )
        diagnostics = config.validation_diagnostics()
        assert any("num_ctx_requested:not_positive" in d for d in diagnostics)

    def test_validation_diagnostics_exceeds_cap(self):
        config = PlannerRuntimeConfig(
            planner_url="url",
            planner_model="model",
            task_url="url",
            task_model="model",
            num_ctx_requested=100,
            num_ctx_cap=50,
            num_ctx_effective=100,
            prompt_char_budget=1,
            prompt_compact_threshold_chars=1,
            generation_headroom_reserve_chars=1,
        )
        diagnostics = config.validation_diagnostics()
        assert any("num_ctx_effective:exceeds_num_ctx_cap" in d for d in diagnostics)

    def test_validation_diagnostics_clean(self):
        config = PlannerRuntimeConfig(
            planner_url="http://localhost:11434",
            planner_model="qwen3",
            task_url="http://localhost:11434",
            task_model="qwen3",
            num_ctx_requested=8192,
            num_ctx_cap=32768,
            num_ctx_effective=8192,
            prompt_char_budget=16000,
            prompt_compact_threshold_chars=4000,
            generation_headroom_reserve_chars=2000,
        )
        diagnostics = config.validation_diagnostics()
        assert diagnostics == ()


class TestToolDecision:
    """Tests for ToolDecision dataclass."""

    def test_frozen(self):
        decision = ToolDecision(tool="repo_read", arguments={"path": "test.py"})
        with pytest.raises(Exception):
            decision.tool = "new"

    def test_defaults(self):
        decision = ToolDecision(tool="test")
        assert decision.arguments == {}
        assert decision.reason == ""
        assert decision.native_tool_call is False

    def test_with_arguments(self):
        decision = ToolDecision(
            tool="repo_read",
            arguments={"path": "test.py", "max_chars": 1000},
            reason="Need to inspect file",
        )
        assert decision.tool == "repo_read"
        assert decision.arguments["path"] == "test.py"
        assert decision.reason == "Need to inspect file"


class TestFinalDecision:
    """Tests for FinalDecision dataclass."""

    def test_frozen(self):
        decision = FinalDecision(final_answer="The answer is 42")
        with pytest.raises(Exception):
            decision.final_answer = "new"

    def test_defaults(self):
        decision = FinalDecision(final_answer="answer")
        assert decision.source == "final_answer"

    def test_custom_source(self):
        decision = FinalDecision(final_answer="answer", source="custom")
        assert decision.source == "custom"


class TestPlannerDecision:
    """Tests for PlannerDecision dataclass."""

    def test_frozen(self):
        decision = PlannerDecision(action="tool_call")
        with pytest.raises(Exception):
            decision.action = "new"

    def test_defaults(self):
        decision = PlannerDecision(action="tool_call")
        assert decision.raw == {}
        assert decision.tool_call is None
        assert decision.final is None
        assert decision.violations == ()

    def test_with_tool_call(self):
        tool_dec = ToolDecision(tool="repo_read", arguments={"path": "test.py"})
        decision = PlannerDecision(
            action="tool_call",
            tool_call=tool_dec,
            violations=["violation1"],
        )
        assert decision.tool_call == tool_dec
        # The domain models may store violations as list in some contexts
        assert len(decision.violations) == 1
        assert "violation1" in decision.violations

    def test_with_final(self):
        final_dec = FinalDecision(final_answer="answer")
        decision = PlannerDecision(
            action="final",
            final=final_dec,
        )
        assert decision.final == final_dec


class TestEvidenceWindow:
    """Tests for EvidenceWindow dataclass."""

    def test_frozen(self):
        window = EvidenceWindow(
            document_id="doc1",
            section="intro",
            text="content",
            window_start=0,
            window_end=100,
            full_chars=200,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc123",
            window_sha256="def456",
        )
        with pytest.raises(Exception):
            window.document_id = "new"

    def test_defaults(self):
        window = EvidenceWindow(
            document_id="doc1",
            section="intro",
            text="content",
            window_start=0,
            window_end=100,
            full_chars=200,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc",
            window_sha256="def",
        )
        assert window.document_id == "doc1"

    def test_has_tracking_metadata_valid(self):
        # text must have length matching window_chars
        window = EvidenceWindow(
            document_id="doc1",
            section="intro",
            text="x" * 100,
            window_start=0,
            window_end=100,
            full_chars=200,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc",
            window_sha256="def",
        )
        assert window.has_tracking_metadata() is True

    def test_has_tracking_metadata_invalid_doc_id(self):
        window = EvidenceWindow(
            document_id="",
            section="intro",
            text="content",
            window_start=0,
            window_end=100,
            full_chars=200,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc",
            window_sha256="def",
        )
        assert window.has_tracking_metadata() is False

    def test_has_tracking_metadata_invalid_window_start(self):
        window = EvidenceWindow(
            document_id="doc1",
            section="intro",
            text="content",
            window_start=-1,
            window_end=100,
            full_chars=200,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc",
            window_sha256="def",
        )
        assert window.has_tracking_metadata() is False

    def test_has_tracking_metadata_invalid_full_chars(self):
        window = EvidenceWindow(
            document_id="doc1",
            section="intro",
            text="content",
            window_start=0,
            window_end=100,
            full_chars=50,
            window_chars=100,
            complete=True,
            has_more_before=False,
            has_more_after=False,
            sha256="abc",
            window_sha256="def",
        )
        assert window.has_tracking_metadata() is False


class TestToolEvidence:
    """Tests for ToolEvidence dataclass."""

    def test_frozen(self):
        evidence = ToolEvidence(tool="repo_read", ok=True)
        with pytest.raises(Exception):
            evidence.tool = "new"

    def test_defaults(self):
        evidence = ToolEvidence(tool="test", ok=True)
        assert evidence.target == ""
        assert evidence.facts == {}

    def test_with_target_and_facts(self):
        evidence = ToolEvidence(
            tool="repo_read",
            ok=True,
            target="test.py",
            facts={"lines": 100, "size": 2000},
        )
        assert evidence.target == "test.py"
        assert evidence.facts["lines"] == 100


class TestEvidenceContract:
    """Tests for EvidenceContract dataclass."""

    def test_frozen(self):
        contract = EvidenceContract(goal="test goal", final_allowed=True)
        with pytest.raises(Exception):
            contract.goal = "new"

    def test_defaults(self):
        contract = EvidenceContract(goal="goal", final_allowed=True)
        assert contract.required_next_progress == ""
        assert contract.required_next_tool_call is None
        assert contract.verified_content_read_count == 0
        assert contract.known_paths == ()
        assert contract.raw == {}

    def test_with_values(self):
        contract = EvidenceContract(
            goal="analyze code",
            final_allowed=False,
            required_next_progress="read files",
            verified_content_read_count=5,
            known_paths=("test.py",),
        )
        assert contract.goal == "analyze code"
        assert contract.final_allowed is False
        assert contract.verified_content_read_count == 5
        assert contract.known_paths == ("test.py",)


class TestAgentJobSnapshot:
    """Tests for AgentJobSnapshot dataclass."""

    def test_frozen(self):
        snapshot = AgentJobSnapshot(job_id="job1", status="running", goal="test", workspace=Path("/tmp"))
        with pytest.raises(Exception):
            snapshot.job_id = "new"

    def test_defaults(self):
        snapshot = AgentJobSnapshot(job_id="job1", status="running", goal="test", workspace=Path("/tmp"))
        assert snapshot.history == ()
        assert snapshot.state == {}

    def test_with_history_and_state(self):
        snapshot = AgentJobSnapshot(
            job_id="job1",
            status="completed",
            goal="test",
            workspace=Path("/tmp"),
            history=[{"tool": "repo_read"}, {"tool": "repo_read"}],
            state={"progress": 0.5},
        )
        assert len(snapshot.history) == 2
        assert snapshot.state["progress"] == 0.5


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_frozen(self):
        result = ToolResult(tool="repo_read", ok=True)
        with pytest.raises(Exception):
            result.tool = "new"

    def test_defaults(self):
        result = ToolResult(tool="test", ok=True)
        assert result.artifact == {}
        assert result.errors == ()
        assert result.warnings == ()
        assert result.raw == {}

    def test_with_errors_and_warnings(self):
        result = ToolResult(
            tool="repo_read",
            ok=False,
            errors=["error1", "error2"],
            warnings=["warning1"],
        )
        assert result.ok is False
        # The domain models may store errors/warnings as list in some contexts
        assert len(result.errors) == 2
        assert "error1" in result.errors
        assert "error2" in result.errors
        assert len(result.warnings) == 1


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_frozen(self):
        result = ValidationResult(ok=True)
        with pytest.raises(Exception):
            result.ok = False

    def test_defaults(self):
        result = ValidationResult(ok=True)
        assert result.violations == ()
        assert result.blocker is None
        assert result.evidence_updates == {}

    def test_with_violations(self):
        result = ValidationResult(
            ok=False,
            violations=["violation1", "violation2"],
            blocker="critical_issue",
        )
        assert result.ok is False
        # The domain models may store violations as list in some contexts
        assert len(result.violations) == 2
        assert "violation1" in result.violations
        assert "violation2" in result.violations
        assert result.blocker == "critical_issue"


class TestToolSpec:
    """Tests for ToolSpec dataclass."""

    def test_frozen(self):
        spec = ToolSpec(name="repo_read", description="Reads files")
        with pytest.raises(Exception):
            spec.name = "new"

    def test_defaults(self):
        spec = ToolSpec(name="test", description="description")
        assert spec.parameters == {}
        assert spec.write_guarded is False
        assert spec.public_3571_visible is False

    def test_with_parameters(self):
        spec = ToolSpec(
            name="repo_read",
            description="Reads files",
            parameters={"path": "str", "max_chars": "int"},
            write_guarded=True,
        )
        assert spec.parameters["path"] == "str"
        assert spec.write_guarded is True


class TestDomainModelsIntegration:
    """Integration tests for domain models."""

    def test_tool_decision_to_planner_decision(self):
        tool_dec = ToolDecision(tool="repo_read", arguments={"path": "test.py"})
        planner_dec = PlannerDecision(action="tool_call", tool_call=tool_dec)
        assert planner_dec.tool_call == tool_dec
        assert planner_dec.action == "tool_call"

    def test_final_decision_in_planner_decision(self):
        final_dec = FinalDecision(final_answer="The answer is 42")
        planner_dec = PlannerDecision(action="final", final=final_dec)
        assert planner_dec.final == final_dec
        assert planner_dec.final.final_answer == "The answer is 42"

    def test_evidence_contract_with_goal(self):
        contract = EvidenceContract(goal="analyze codebase", final_allowed=False)
        assert contract.goal == "analyze codebase"
        assert contract.final_allowed is False

    def test_tool_result_with_artifact(self):
        result = ToolResult(
            tool="repo_read",
            ok=True,
            artifact={"content": "hello world", "lines": 10},
        )
        assert result.ok is True
        assert result.artifact["content"] == "hello world"

    def test_validation_result_with_evidence_updates(self):
        result = ValidationResult(
            ok=True,
            evidence_updates={"new_paths": ["test.py"]},
        )
        assert result.ok is True
        assert result.evidence_updates["new_paths"] == ["test.py"]