from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inline_evidence_contract_mentions_payload_index() -> None:
    text = (ROOT / "services" / "OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "payload_index_for_30b" in text
    assert "campi realmente presenti" in text


def test_inline_evidence_contract_forbids_local_paths_as_evidence() -> None:
    text = (ROOT / "services" / "OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    for forbidden in ("final_path", "artifact_path", "workspace", "sqlite_path"):
        assert forbidden in text
    assert "Non sono evidenza pubblica" in text


def test_inline_evidence_contract_requires_materialized_json() -> None:
    text = (ROOT / "services" / "OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "Solo JSON inline materializzato" in text
    assert "Objects are not evidence" in text
    assert "materialization_report" in text
