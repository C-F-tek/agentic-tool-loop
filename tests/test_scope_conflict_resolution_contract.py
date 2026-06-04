from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.scope_conflict_resolution import (  # noqa: E402
    SCOPE_CONFLICT_RATIONALE_TERMS,
    target_scope_conflict_resolved,
)


TARGET = "ia_carmine/_shared/runtime_tool_guidance.py"


def _contract() -> dict:
    return {
        "verified_content_reads": [{"path": TARGET}],
        "file_memory": [{
            "path": TARGET,
            "headings": ["Runtime Tool Guidance"],
            "key_lines": ["def validate_runtime_tool_request_object(request):"],
            "mentioned_paths": [],
            "content_excerpt": "validate_runtime_tool_request_object checks runtime request contract fields.",
        }],
    }


def _args(rationale: str) -> dict:
    return {
        "edit_kind": "unified_diff",
        "target_file": TARGET,
        "old_text": "old runtime validation code",
        "new_text": "new runtime validation code",
        "rationale": rationale,
    }


def test_target_scope_conflict_requires_verified_target_read() -> None:
    assert not target_scope_conflict_resolved(
        TARGET,
        _args("runtime core contract evidence read validate_runtime_tool_request_object now explains target"),
        {"verified_content_reads": [], "file_memory": []},
    )


def test_target_scope_conflict_requires_complete_code_product_payload() -> None:
    assert not target_scope_conflict_resolved(
        TARGET,
        {"edit_kind": "unified_diff", "target_file": TARGET, "rationale": "runtime core contract evidence read"},
        _contract(),
    )


def test_target_scope_conflict_requires_rationale_terms_and_file_anchor() -> None:
    anchor_contract = {
        "verified_content_reads": [{"path": TARGET}],
        "file_memory": [{
            "path": TARGET,
            "headings": ["Special Area"],
            "key_lines": ["def unique_anchor_xyz(request):"],
            "mentioned_paths": [],
            "content_excerpt": "unique_anchor_xyz handles selected behaviour.",
        }],
    }
    assert not target_scope_conflict_resolved(
        TARGET,
        _args("this is a long enough generic explanation but without required operational terms"),
        _contract(),
    )
    assert not target_scope_conflict_resolved(
        TARGET,
        _args("runtime core contract evidence was read but no matching anchor appears in this rationale"),
        anchor_contract,
    )

    assert target_scope_conflict_resolved(
        TARGET,
        _args(
            "runtime core contract evidence was read and validate_runtime_tool_request_object is the anchor proving scope"
        ),
        _contract(),
    )


def test_scope_conflict_rationale_terms_exports_current_terms() -> None:
    assert "runtime" in SCOPE_CONFLICT_RATIONALE_TERMS
    assert "contratto" in SCOPE_CONFLICT_RATIONALE_TERMS
