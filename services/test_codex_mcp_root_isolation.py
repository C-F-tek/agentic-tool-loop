from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_codex_app_mcp_root_overrides_inherited_broker_lab_shadow(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-selected-root"
    broker_lab_shadow = tmp_path / "broker-lab-shadow"
    _git_init(codex_root)
    _git_init(broker_lab_shadow)

    monkeypatch.setenv("CODEX_WORKSPACE_ROOT", str(codex_root))
    monkeypatch.setenv("AICARMINE_LAB_REPO", str(broker_lab_shadow))
    monkeypatch.delenv("AICARMINE_CODEX_MCP_REPO_ROOT", raising=False)

    sys.modules.pop("codex_bridge.mcp_server", None)
    module = importlib.import_module("codex_bridge.mcp_server")

    assert module._repo_root() == codex_root.resolve()
    assert module._sync_broker_import_root() == codex_root.resolve()
    assert os.environ["AICARMINE_LAB_REPO"] == str(codex_root.resolve())
    assert os.environ["AICARMINE_CODEX_MCP_REPO_ROOT"] == str(codex_root.resolve())


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_repo_mcp_common_syncs_broker_import_root_before_tool_import(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-selected-root"
    broker_lab_shadow = tmp_path / "broker-lab-shadow"
    _git_init(codex_root)
    _git_init(broker_lab_shadow)

    monkeypatch.setenv("CODEX_WORKSPACE_ROOT", str(codex_root))
    monkeypatch.setenv("AICARMINE_LAB_REPO", str(broker_lab_shadow))
    monkeypatch.delenv("AICARMINE_CODEX_MCP_REPO_ROOT", raising=False)

    sys.modules.pop("codex_bridge.repo_mcp_common", None)
    module = importlib.import_module("codex_bridge.repo_mcp_common")

    assert module.selected_repo_root() == codex_root.resolve()
    assert os.environ["AICARMINE_LAB_REPO"] == str(codex_root.resolve())
    assert os.environ["AICARMINE_CODEX_MCP_REPO_ROOT"] == str(codex_root.resolve())

    health = module.health_payload("test-mcp", ["health"])
    assert health["repo_root"] == str(codex_root.resolve())
    assert health["aicarmine_lab_repo"] == str(codex_root.resolve())
    assert health["initial_aicarmine_lab_repo"] == str(broker_lab_shadow)
