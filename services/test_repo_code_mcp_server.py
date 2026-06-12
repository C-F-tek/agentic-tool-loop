from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def _drop_repo_code_modules() -> None:
    prefixes = (
        "aicarmine_broker.config",
        "aicarmine_broker.tools.repo_code_product",
        "aicarmine_broker.tools.repo_deterministic",
        "aicarmine_broker.tools.repo_patch",
    )
    for module_name in list(sys.modules):
        if module_name in {"repo_mcp_common", "codex_bridge.repo_code_mcp_server"}:
            sys.modules.pop(module_name, None)
            continue
        if any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in prefixes):
            sys.modules.pop(module_name, None)


def _load_server(monkeypatch: pytest.MonkeyPatch, codex_root: Path, broker_lab_shadow: Path) -> ModuleType:
    monkeypatch.setenv("CODEX_WORKSPACE_ROOT", str(codex_root))
    monkeypatch.setenv("AICARMINE_LAB_REPO", str(broker_lab_shadow))
    monkeypatch.delenv("AICARMINE_CODEX_MCP_REPO_ROOT", raising=False)
    _drop_repo_code_modules()
    return importlib.import_module("codex_bridge.repo_code_mcp_server")


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_repo_code_mcp_apply_patch_requires_explicit_source_write(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-selected-root"
    broker_lab_shadow = tmp_path / "broker-lab-shadow"
    _git_init(codex_root)
    _git_init(broker_lab_shadow)
    target = codex_root / "sample.py"
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    module = _load_server(monkeypatch, codex_root, broker_lab_shadow)
    tools = module._tools()
    tool = tools["aicarmine_repo_code_apply_patch"]

    denied = tool.handler(
        {
            "path": "sample.py",
            "old_text": "VALUE = 'old'",
            "new_text": "VALUE = 'new'",
        },
        codex_root,
    )

    assert denied["ok"] is False
    assert denied["error"] == "source_write_not_enabled"
    assert denied["source_writes_performed"] is False
    assert denied["patch_application_performed"] is False
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"

    applied = tool.handler(
        {
            "path": "sample.py",
            "old_text": "VALUE = 'old'",
            "new_text": "VALUE = 'new'",
            "allow_source_write": True,
        },
        codex_root,
    )

    assert applied["ok"] is True
    assert applied["changed"] is True
    assert applied["source_writes_performed"] is True
    assert applied["patch_application_performed"] is True
    assert applied["write_scope"] == "exact_old_text_new_text_only"
    assert os.environ["AICARMINE_LAB_REPO"] == str(codex_root.resolve())
    assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"


def test_repo_code_mcp_exposes_only_incubating_code_tools(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-selected-root"
    broker_lab_shadow = tmp_path / "broker-lab-shadow"
    codex_root.mkdir(parents=True)
    broker_lab_shadow.mkdir(parents=True)

    module = _load_server(monkeypatch, codex_root, broker_lab_shadow)
    tool_names = set(module._tools())

    assert "aicarmine_repo_code_propose_edit" in tool_names
    assert "aicarmine_repo_code_unidiff_validate" in tool_names
    assert "aicarmine_repo_code_git_apply_check" in tool_names
    assert "aicarmine_repo_code_apply_patch" in tool_names
    assert "repo_write_file" not in tool_names
    assert "repo_command" not in tool_names
