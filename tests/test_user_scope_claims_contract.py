from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.user_scope_claims import (  # noqa: E402
    claim_area_from_user_token,
    normalize_scope_claim_text,
    scope_claim_conflict_for_path,
    user_scope_claims,
)


def test_normalize_scope_claim_text_preserves_path_semantics() -> None:
    assert normalize_scope_claim_text("Shared non è il core\\IA") == "shared non e il core/ia"


def test_claim_area_maps_shared_to_scoped_shared_when_it_exists() -> None:
    existing = {"ia_carmine/_shared"}

    assert claim_area_from_user_token(
        "shared",
        "ia_carmine",
        path_exists_repo_relative=existing.__contains__,
    ) == "ia_carmine/_shared"
    assert claim_area_from_user_token(
        "shared",
        "",
        path_exists_repo_relative=existing.__contains__,
    ) == "ia_carmine/_shared"


def test_user_scope_claims_extracts_not_core_claim_without_static_blocklist() -> None:
    claims = user_scope_claims(
        "Analizza ia_carmine: shared non e il core, e solo utility script.",
        "ia_carmine",
        path_exists_repo_relative={"ia_carmine/_shared"}.__contains__,
    )

    assert claims == [{
        "area": "ia_carmine/_shared",
        "claim": "not_core",
        "source": "user_request",
        "text": "Analizza ia_carmine: shared non e il core, e solo utility script.",
        "validator_effect": "requires_read_evidence_for_conflicting_patch_target",
    }]


def test_scope_claim_conflict_matches_exact_area_and_nested_shared() -> None:
    shared_claim = {"area": "_shared", "claim": "not_core"}
    scoped_claim = {"area": "ia_carmine/_shared", "claim": "not_core"}

    assert scope_claim_conflict_for_path("services/_shared/tool.py", [shared_claim]) == shared_claim
    assert scope_claim_conflict_for_path("ia_carmine/_shared/tool.py", [scoped_claim]) == scoped_claim
    assert scope_claim_conflict_for_path("ia_carmine/core.py", [scoped_claim]) == {}
