from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_surface.action_proof_ledger import (  # noqa: E402
    attach_action_proof,
    stable_action_id,
)


def test_candidate_action_has_stable_action_id() -> None:
    action = {"tool": "repo_read", "arguments": {"path": "README.md"}}
    with_proof = attach_action_proof(action, source="test")

    assert with_proof["action_id"] == stable_action_id(action)
    assert stable_action_id(with_proof) == stable_action_id(action)


def test_candidate_action_has_action_proof() -> None:
    action = {"tool": "repo_read", "arguments": {"path": "README.md"}}

    with_proof = attach_action_proof(
        action,
        source="core_discovery_candidates",
        path_exists=True,
        path_readable=True,
        under_scope=True,
        validator_admissible=True,
    )

    assert with_proof["action_proof"] == {
        "source": "core_discovery_candidates",
        "path_exists": True,
        "path_readable": True,
        "under_scope": True,
        "validator_admissible": True,
        "source_step": None,
        "source_hash": "",
    }


def test_action_proof_not_added_for_invalid_candidate() -> None:
    assert attach_action_proof({}, source="test") == {}
