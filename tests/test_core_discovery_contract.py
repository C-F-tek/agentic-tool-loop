from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.evidence.core_discovery import (  # noqa: E402
    add_core_discovery_candidate,
    core_discovery_candidates_from_intrinsic,
    core_discovery_read_paths,
)


def _under(path: str, scope: str) -> bool:
    return not scope or path == scope or path.startswith(scope.rstrip("/") + "/")


def _exists(path: str) -> bool:
    return path in {"ia_carmine/_shared/runtime.py", "ia_carmine/cli.py", "services/app.py"}


def _readable(path: str) -> bool:
    return path.endswith((".py", ".md"))


def test_add_core_discovery_candidate_adds_conflict_metadata() -> None:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    claim = {"area": "ia_carmine/_shared", "claim": "not_core"}

    added = add_core_discovery_candidate(
        out,
        seen,
        path="ia_carmine/_shared/runtime.py",
        source="retrieved_rag_chunks",
        rank=1,
        reason="read before deciding",
        read_ok=set(),
        target_scope="ia_carmine",
        user_scope_claims=[claim],
        lab_repo_label="C:/repo",
        path_under_scope=_under,
        path_exists_repo_relative=_exists,
        repo_readable_evidence_file=_readable,
        score=0.7,
        ranking_source="fts",
    )

    assert added
    assert out[0]["path"] == "ia_carmine/_shared/runtime.py"
    assert out[0]["claim_conflict"] is True
    assert out[0]["conflicting_user_scope_claim"] == claim
    assert out[0]["score"] == 0.7


def test_core_discovery_prefers_current_rag_candidates() -> None:
    candidates, status = core_discovery_candidates_from_intrinsic(
        intrinsic_context={
            "retrieved_rag_chunks": {
                "status": "ready",
                "ranking_source": "external",
                "items": [
                    {"path": "ia_carmine/cli.py", "score": 0.9},
                    {"path": "missing/file.py", "score": 0.8},
                ],
            },
        },
        list_rows=[],
        read_ok=[],
        target_scope="ia_carmine",
        user_scope_claims=[],
        lab_repo_label="C:/repo",
        path_under_scope=_under,
        path_exists_repo_relative=_exists,
        repo_readable_evidence_file=_readable,
        scope_read_candidates_from_evidence=lambda _rows, _scope, _read_ok: [],
        meaningful_read_candidates_from_evidence=lambda _rows, _read_ok: [],
    )

    assert [candidate["path"] for candidate in candidates] == ["ia_carmine/cli.py"]
    assert status["source"] == "rag_current_lab_repo"
    assert status["rag_stale_or_unusable_count"] == 1


def test_core_discovery_rebuilds_from_repo_evidence_when_rag_missing() -> None:
    candidates, status = core_discovery_candidates_from_intrinsic(
        intrinsic_context={},
        list_rows=[{"paths_preview": ["ia_carmine/cli.py"]}],
        read_ok=[],
        target_scope="ia_carmine",
        user_scope_claims=[],
        lab_repo_label="C:/repo",
        path_under_scope=_under,
        path_exists_repo_relative=_exists,
        repo_readable_evidence_file=_readable,
        scope_read_candidates_from_evidence=lambda _rows, _scope, _read_ok: ["ia_carmine/cli.py"],
        meaningful_read_candidates_from_evidence=lambda _rows, _read_ok: [],
    )

    assert candidates[0]["source"] == "lab_repo_evidence_rebuild"
    assert candidates[0]["ranking_source"] == "current_lab_repo_evidence"
    assert status["source"] == "ranking_rebuilt_from_lab_repo_evidence"


def test_core_discovery_read_paths_filters_already_read_and_out_of_scope() -> None:
    paths = core_discovery_read_paths(
        [
            {"path": "ia_carmine/cli.py"},
            {"path": "services/app.py"},
            {"path": "ia_carmine/_shared/runtime.py"},
        ],
        read_ok={"ia_carmine/cli.py"},
        target_scope="ia_carmine",
        limit=2,
        path_under_scope=_under,
        path_exists_repo_relative=_exists,
        repo_readable_evidence_file=_readable,
    )

    assert paths == ["ia_carmine/_shared/runtime.py"]
