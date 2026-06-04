from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_domain_decision_and_validation_imports() -> None:
    from aicarmine_broker.domain import (
        EvidenceContract,
        FinalDecision,
        PlannerDecision,
        ToolDecision,
        ValidationResult,
    )

    decision = PlannerDecision(
        action="tool",
        tool_call=ToolDecision(tool="repo_read", arguments={"path": "AGENTS.md"}),
    )
    evidence = EvidenceContract(goal="read AGENTS", final_allowed=False)
    result = ValidationResult(ok=True)

    assert decision.tool_call is not None
    assert decision.tool_call.tool == "repo_read"
    assert evidence.goal == "read AGENTS"
    assert result.violations == ()
    assert FinalDecision(final_answer="done").source == "final_answer"


def test_evidence_window_requires_real_tracking_metadata() -> None:
    from aicarmine_broker.domain import EvidenceWindow

    window = EvidenceWindow(
        document_id="doc-1",
        section="required_working_set",
        text="abc",
        window_start=0,
        window_end=3,
        full_chars=3,
        window_chars=3,
        complete=True,
        has_more_before=False,
        has_more_after=False,
        sha256="full",
        window_sha256="window",
    )

    assert window.has_tracking_metadata()


def test_contract_protocols_import_without_runtime_side_effects() -> None:
    from aicarmine_broker.contracts import (
        AgenticTool,
        CommandResult,
        JobRepository,
        PlannerClient,
        PlannerValidator,
        PromptStore,
        RepoFilesystem,
        ToolDispatcher,
    )

    assert AgenticTool is not None
    assert CommandResult(returncode=0, stdout="", stderr="").returncode == 0
    assert JobRepository is not None
    assert PlannerClient is not None
    assert PlannerValidator is not None
    assert PromptStore is not None
    assert RepoFilesystem is not None
    assert ToolDispatcher is not None
