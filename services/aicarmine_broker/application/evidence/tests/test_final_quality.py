#!/usr/bin/env python3
"""Tests for services/aicarmine_broker/application/evidence/final_quality.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from aicarmine_broker.application.evidence.final_quality import (
    _append_unique,
    _clip_text,
    _compact_list,
    _compact_mapping,
    _verified_read_summary,
    _final_quality_rag_tool_surface,
    _final_quality_contract_summary,
    _read_note_rows,
    _evidence_paths,
    _path_hit_count,
    _repoish_path_token,
    _path_is_concrete_repo_path,
    _contract_read_allowlist,
    _coalesce_required_next_missing_paths,
    _final_path_tokens,
    _coalesce_unique_paths,
    _path_items,
    _repo_read_completed_paths,
    _repo_read_path_allowlist,
    _known_repo_paths,
    _known_repo_dirs,
    _route_token_is_prose_or_metric,
    _search_query_is_concrete,
    _record_invalid_required_next_tool_call,
    _allowed_concrete_repo_path,
    _normalize_required_next_tool_call_paths,
    _required_next_output_sections,
    _required_next_missing_evidences,
    _known_path_tokens,
    _unverified_final_path_tokens,
    _concept_present,
    _absolute_no_issue_claim,
    _absolute_repo_no_issue_claim,
    _declares_partial_or_limited_coverage,
    _claims_deep_or_complete_review,
    _repo_content_analysis_summary,
    repo_analysis_final_answer_quality,
    repo_analysis_final_answer_model_quality_request,
    _violation_code,
    _sanitize_required_next_tool_call,
    _sanitize_required_next_output_sections,
    _sanitize_required_next_missing_evidences,
    sanitize_repo_analysis_final_model_quality,
    repo_analysis_final_answer_too_shallow,
)


def test_append_unique():
    """Test _append_unique."""
    values: list[str] = []
    _append_unique(values, "a")
    _append_unique(values, "b")
    _append_unique(values, "a")  # duplicate
    assert len(values) == 2
    assert values == ["a", "b"]
    print("✓ test_append_unique")


def test_clip_text():
    """Test _clip_text."""
    result = _clip_text("hello world", 5)
    assert isinstance(result, str)
    
    result = _clip_text(12345, 5)
    assert isinstance(result, str)
    print("✓ test_clip_text")


def test_compact_list():
    """Test _compact_list."""
    result = _compact_list([1, 2, 3, 4, 5], limit=3)
    assert isinstance(result, list)
    assert len(result) <= 3
    print("✓ test_compact_list")


def test_compact_mapping():
    """Test _compact_mapping."""
    result = _compact_mapping({"key": "value"}, text_limit=50, list_limit=8)
    assert isinstance(result, dict)
    print("✓ test_compact_mapping")


def test_verified_read_summary():
    """Test _verified_read_summary."""
    contract = {
        "verified_content_reads": [
            {"path": "/src/file.py"},
        ]
    }
    result = _verified_read_summary(contract)
    assert isinstance(result, dict)
    print("✓ test_verified_read_summary")


def test_final_quality_rag_tool_surface():
    """Test _final_quality_rag_tool_surface."""
    contract = {}
    result = _final_quality_rag_tool_surface(contract)
    assert isinstance(result, dict)
    print("✓ test_final_quality_rag_tool_surface")


def test_final_quality_contract_summary():
    """Test _final_quality_contract_summary."""
    contract = {}
    result = _final_quality_contract_summary(contract)
    assert isinstance(result, dict)
    print("✓ test_final_quality_contract_summary")


def test_read_note_rows():
    """Test _read_note_rows."""
    contract = {}
    result = _read_note_rows(contract)
    assert isinstance(result, list)
    print("✓ test_read_note_rows")


def test_evidence_paths():
    """Test _evidence_paths."""
    contract = {}
    result = _evidence_paths(contract)
    assert isinstance(result, list)
    print("✓ test_evidence_paths")


def test_path_hit_count():
    """Test _path_hit_count."""
    result = _path_hit_count("hello world", ["world"])
    assert isinstance(result, int)
    print("✓ test_path_hit_count")


def test_repoish_path_token():
    """Test _repoish_path_token."""
    result = _repoish_path_token("/src/file.py")
    assert isinstance(result, str)
    print("✓ test_repoish_path_token")


def test_path_is_concrete_repo_path():
    """Test _path_is_concrete_repo_path."""
    result = _path_is_concrete_repo_path("/src/file.py")
    assert isinstance(result, bool)
    print("✓ test_path_is_concrete_repo_path")


def test_contract_read_allowlist():
    """Test _contract_read_allowlist."""
    contract = {}
    result = _contract_read_allowlist(contract)
    assert isinstance(result, set)
    print("✓ test_contract_read_allowlist")


def test_coalesce_required_next_missing_paths():
    """Test _coalesce_required_next_missing_paths."""
    result = _coalesce_required_next_missing_paths([])
    assert isinstance(result, list)
    print("✓ test_coalesce_required_next_missing_paths")


def test_final_path_tokens():
    """Test _final_path_tokens."""
    result = _final_path_tokens("hello world")
    assert isinstance(result, list)
    print("✓ test_final_path_tokens")


def test_coalesce_unique_paths():
    """Test _coalesce_unique_paths."""
    result = _coalesce_unique_paths(["a", "b", "a"], limit=10)
    assert isinstance(result, list)
    assert len(result) == 2
    print("✓ test_coalesce_unique_paths")


def test_path_items():
    """Test _path_items."""
    result = _path_items(["/src/file.py"])
    assert isinstance(result, list)
    print("✓ test_path_items")


def test_repo_read_completed_paths():
    """Test _repo_read_completed_paths."""
    contract = {}
    result = _repo_read_completed_paths(contract)
    assert isinstance(result, set)
    print("✓ test_repo_read_completed_paths")


def test_repo_read_path_allowlist():
    """Test _repo_read_path_allowlist."""
    contract = {}
    result = _repo_read_path_allowlist(contract)
    assert isinstance(result, set)
    print("✓ test_repo_read_path_allowlist")


def test_known_repo_paths():
    """Test _known_repo_paths."""
    contract = {}
    result = _known_repo_paths(contract)
    assert isinstance(result, set)
    print("✓ test_known_repo_paths")


def test_known_repo_dirs():
    """Test _known_repo_dirs."""
    result = _known_repo_dirs({"/src", "/tests"})
    assert isinstance(result, set)
    print("✓ test_known_repo_dirs")


def test_route_token_is_prose_or_metric():
    """Test _route_token_is_prose_or_metric."""
    result = _route_token_is_prose_or_metric("hello")
    assert isinstance(result, bool)
    print("✓ test_route_token_is_prose_or_metric")


def test_search_query_is_concrete():
    """Test _search_query_is_concrete."""
    result = _search_query_is_concrete("find file.py")
    assert isinstance(result, bool)
    print("✓ test_search_query_is_concrete")


def test_record_invalid_required_next_tool_call():
    """Test _record_invalid_required_next_tool_call."""
    # Function signature: _record_invalid_required_next_tool_call(diagnostics=None, *, reason=..., paths=..., query=...)
    diagnostics: dict[str, Any] = {}
    _record_invalid_required_next_tool_call(diagnostics, reason="test_reason")
    assert "invalid_required_next_tool_call_reason" in diagnostics
    print("✓ test_record_invalid_required_next_tool_call")


def test_allowed_concrete_repo_path():
    """Test _allowed_concrete_repo_path."""
    result = _allowed_concrete_repo_path("/src/file.py", {"/src"})
    assert isinstance(result, str)
    print("✓ test_allowed_concrete_repo_path")


def test_normalize_required_next_tool_call_paths():
    """Test _normalize_required_next_tool_call_paths."""
    # Function signature: _normalize_required_next_tool_call_paths(tool, arguments)
    result = _normalize_required_next_tool_call_paths("repo_read", {"paths": ["/src/file.py"]})
    assert isinstance(result, dict)
    print("✓ test_normalize_required_next_tool_call_paths")


def test_required_next_output_sections():
    """Test _required_next_output_sections."""
    result = _required_next_output_sections([], {})
    assert isinstance(result, list)
    print("✓ test_required_next_output_sections")


def test_required_next_missing_evidences():
    """Test _required_next_missing_evidences."""
    # Function signature: _required_next_missing_evidences(violations, metrics, hard_pending_actions, contract)
    result = _required_next_missing_evidences([], {}, [], {})
    assert isinstance(result, list)
    print("✓ test_required_next_missing_evidences")


def test_known_path_tokens():
    """Test _known_path_tokens."""
    result = _known_path_tokens({}, ["/src/file.py"], [])
    assert isinstance(result, set)
    print("✓ test_known_path_tokens")


def test_unverified_final_path_tokens():
    """Test _unverified_final_path_tokens."""
    # Function signature: _unverified_final_path_tokens(final_answer, contract, *, paths, core_paths)
    result = _unverified_final_path_tokens("hello", {}, paths=[], core_paths=[])
    assert isinstance(result, list)
    print("✓ test_unverified_final_path_tokens")


def test_concept_present():
    """Test _concept_present."""
    result = _concept_present("deep analysis", ("deep", "complete"))
    assert isinstance(result, bool)
    print("✓ test_concept_present")


def test_absolute_no_issue_claim():
    """Test _absolute_no_issue_claim."""
    result = _absolute_no_issue_claim("no issues found")
    assert isinstance(result, bool)
    print("✓ test_absolute_no_issue_claim")


def test_absolute_repo_no_issue_claim():
    """Test _absolute_repo_no_issue_claim."""
    result = _absolute_repo_no_issue_claim("no repo issues")
    assert isinstance(result, bool)
    print("✓ test_absolute_repo_no_issue_claim")


def test_declares_partial_or_limited_coverage():
    """Test _declares_partial_or_limited_coverage."""
    result = _declares_partial_or_limited_coverage("partial coverage")
    assert isinstance(result, bool)
    print("✓ test_declares_partial_or_limited_coverage")


def test_claims_deep_or_complete_review():
    """Test _claims_deep_or_complete_review."""
    result = _claims_deep_or_complete_review("deep review")
    assert isinstance(result, bool)
    print("✓ test_claims_deep_or_complete_review")


def test_repo_content_analysis_summary():
    """Test _repo_content_analysis_summary."""
    # Function signature: _repo_content_analysis_summary(contract)
    contract = {
        "verified_content_reads": [
            {"path": "/src/file.py", "line_count": 100, "content_preview": "def hello(): pass"},
        ],
        "successful_repo_read_paths": ["/src/file.py"],
        "covered_owner_paths": [],
        "missing_owner_paths": [],
        "candidate_owner_paths": [],
    }
    result = _repo_content_analysis_summary(contract)
    assert isinstance(result, dict)
    assert "schema" in result
    assert "analysis_depth" in result
    print("✓ test_repo_content_analysis_summary")


def test_repo_analysis_final_answer_quality():
    """Test repo_analysis_final_answer_quality."""
    # Function signature: repo_analysis_final_answer_quality(final_answer, contract)
    final_answer = "The codebase is secure with no critical issues found."
    contract = {}
    output = repo_analysis_final_answer_quality(final_answer, contract)
    assert isinstance(output, dict)
    print("✓ test_repo_analysis_final_answer_quality")


def test_repo_analysis_final_answer_model_quality_request():
    """Test repo_analysis_final_answer_model_quality_request."""
    # Function signature: repo_analysis_final_answer_model_quality_request(final_answer, contract, *, goal)
    final_answer = "The codebase is secure with no critical issues found."
    contract = {
        "verified_content_reads": [
            {"path": "/src/file.py", "line_count": 100, "content_preview": "def hello(): pass"},
        ],
        "successful_repo_read_paths": ["/src/file.py"],
        "covered_owner_paths": [],
        "missing_owner_paths": [],
        "candidate_owner_paths": [],
    }
    goal = "analyze codebase"
    output = repo_analysis_final_answer_model_quality_request(final_answer, contract, goal=goal)
    assert isinstance(output, dict)
    assert "system" in output
    assert "user_payload" in output
    print("✓ test_repo_analysis_final_answer_model_quality_request")


def test_violation_code():
    """Test _violation_code."""
    result = _violation_code({"code": "test"})
    assert isinstance(result, str)
    print("✓ test_violation_code")


def test_sanitize_required_next_tool_call():
    """Test _sanitize_required_next_tool_call."""
    # Function signature: _sanitize_required_next_tool_call(value, contract, diagnostics=None)
    result = _sanitize_required_next_tool_call({}, {}, None)
    assert isinstance(result, dict)
    print("✓ test_sanitize_required_next_tool_call")


def test_sanitize_required_next_output_sections():
    """Test _sanitize_required_next_output_sections."""
    result = _sanitize_required_next_output_sections([])
    assert isinstance(result, list)
    print("✓ test_sanitize_required_next_output_sections")


def test_sanitize_required_next_missing_evidences():
    """Test _sanitize_required_next_missing_evidences."""
    result = _sanitize_required_next_missing_evidences([], {})
    assert isinstance(result, list)
    print("✓ test_sanitize_required_next_missing_evidences")


def test_sanitize_repo_analysis_final_model_quality():
    """Test sanitize_repo_analysis_final_model_quality."""
    result = {}
    output = sanitize_repo_analysis_final_model_quality(result)
    assert isinstance(output, dict)
    print("✓ test_sanitize_repo_analysis_final_model_quality")


def test_repo_analysis_final_answer_too_shallow():
    """Test repo_analysis_final_answer_too_shallow."""
    # Function signature: repo_analysis_final_answer_too_shallow(final_answer, contract)
    final_answer = "The codebase is secure."
    contract = {}
    output = repo_analysis_final_answer_too_shallow(final_answer, contract)
    assert isinstance(output, bool)
    print("✓ test_repo_analysis_final_answer_too_shallow")


if __name__ == "__main__":
    tests = [
        test_append_unique,
        test_clip_text,
        test_compact_list,
        test_compact_mapping,
        test_verified_read_summary,
        test_final_quality_rag_tool_surface,
        test_final_quality_contract_summary,
        test_read_note_rows,
        test_evidence_paths,
        test_path_hit_count,
        test_repoish_path_token,
        test_path_is_concrete_repo_path,
        test_contract_read_allowlist,
        test_coalesce_required_next_missing_paths,
        test_final_path_tokens,
        test_coalesce_unique_paths,
        test_path_items,
        test_repo_read_completed_paths,
        test_repo_read_path_allowlist,
        test_known_repo_paths,
        test_known_repo_dirs,
        test_route_token_is_prose_or_metric,
        test_search_query_is_concrete,
        test_record_invalid_required_next_tool_call,
        test_allowed_concrete_repo_path,
        test_normalize_required_next_tool_call_paths,
        test_required_next_output_sections,
        test_required_next_missing_evidences,
        test_known_path_tokens,
        test_unverified_final_path_tokens,
        test_concept_present,
        test_absolute_no_issue_claim,
        test_absolute_repo_no_issue_claim,
        test_declares_partial_or_limited_coverage,
        test_claims_deep_or_complete_review,
        test_repo_content_analysis_summary,
        test_repo_analysis_final_answer_quality,
        test_repo_analysis_final_answer_model_quality_request,
        test_violation_code,
        test_sanitize_required_next_tool_call,
        test_sanitize_required_next_output_sections,
        test_sanitize_required_next_missing_evidences,
        test_sanitize_repo_analysis_final_model_quality,
        test_repo_analysis_final_answer_too_shallow,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: EXCEPTION: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")
    
    sys.exit(0 if failed == 0 else 1)