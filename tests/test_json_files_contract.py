from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.infrastructure.json_files import (  # noqa: E402
    JsonFileStore,
    same_tool_artifact_payload,
)


def test_json_file_store_atomic_roundtrip(tmp_path: Path) -> None:
    store = JsonFileStore()
    target = tmp_path / "state.json"

    written = store.write(target, {"ok": True})

    assert written == target
    assert store.read(target) == {"ok": True}
    assert store.read(tmp_path / "missing.json", default={}) == {}


def test_json_file_store_retries_transient_permission_error_on_replace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JsonFileStore(replace_retries=1, replace_retry_delay_seconds=0)
    target = tmp_path / "state.json"
    original_replace = Path.replace
    calls: list[str] = []

    def flaky_replace(self: Path, replace_target: Path) -> Path:
        if Path(replace_target) == target and not calls:
            calls.append(str(self))
            raise PermissionError("target temporarily locked")
        return original_replace(self, replace_target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    store.write(target, {"ok": True})

    assert calls
    assert store.read(target) == {"ok": True}


def test_json_file_store_propagates_persistent_permission_error_and_cleans_tmp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JsonFileStore(replace_retries=1, replace_retry_delay_seconds=0)
    target = tmp_path / "state.json"

    def locked_replace(self: Path, replace_target: Path) -> Path:
        if Path(replace_target) == target:
            raise PermissionError("target locked")
        return self

    monkeypatch.setattr(Path, "replace", locked_replace)

    with pytest.raises(PermissionError):
        store.write(target, {"ok": True})

    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_same_tool_artifact_payload_loads_matching_successful_tool(tmp_path: Path) -> None:
    artifact = tmp_path / "tool.json"
    JsonFileStore().write(artifact, {"tool": "repo_read", "ok": True, "content": "full"})

    result = {"tool": "repo_read", "ok": True, "artifact": str(artifact), "content_preview": "ful"}

    assert same_tool_artifact_payload(result) == {"tool": "repo_read", "ok": True, "content": "full"}


def test_same_tool_artifact_payload_rejects_non_ok_missing_or_mismatched(tmp_path: Path) -> None:
    mismatch = tmp_path / "mismatch.json"
    JsonFileStore().write(mismatch, {"tool": "repo_tree", "ok": True})

    non_ok = {"tool": "repo_read", "ok": False, "artifact": str(mismatch)}
    missing = {"tool": "repo_read", "ok": True, "artifact": str(tmp_path / "missing.json")}
    mismatched = {"tool": "repo_read", "ok": True, "artifact": str(mismatch)}

    assert same_tool_artifact_payload(non_ok) is non_ok
    assert same_tool_artifact_payload(missing) is missing
    assert same_tool_artifact_payload(mismatched) is mismatched
