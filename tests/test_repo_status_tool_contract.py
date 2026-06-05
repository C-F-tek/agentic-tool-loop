from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_detect_stack_counts_repo_files(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_status")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo_root / "b.csproj").write_text("<Project />\n", encoding="utf-8")
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    stack = module.detect_stack()

    assert stack["python_file_count"] == 1
    assert stack["csproj_count"] == 1
    assert "dotnet build" in stack["canonical_commands"]


def test_detect_stack_compile_command_uses_resolved_targets(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_status")
    repo_root = tmp_path / "repo"
    package = repo_root / "src" / "demo_pkg"
    package.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "module.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(module, "LAB_REPO", repo_root)

    stack = module.detect_stack()
    compile_commands = [
        command for command in stack["canonical_commands"]
        if "compileall" in command
    ]

    assert compile_commands
    assert "src/demo_pkg" in compile_commands[0]
    assert "ia_carmine" not in compile_commands[0]
    assert "Tools" not in compile_commands[0]
    assert stack["compile_target_resolution"]["targets"] == ("src/demo_pkg",)


def test_repo_status_uses_runner_and_writes_command_artifacts(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_status")
    calls: list[str] = []

    def fake_run_ps(command: str, timeout: int = 120) -> dict[str, object]:
        calls.append(command)
        return {"returncode": 0, "stdout_tail": command, "stderr_tail": ""}

    monkeypatch.setattr(module, "run_ps", fake_run_ps)
    monkeypatch.setattr(module, "detect_stack", lambda: {"python_file_count": 0})

    result = module.repo_status({}, tmp_path / "job")

    assert result["ok"] is True
    assert result["tool"] == "repo_status"
    assert calls[0] == "git status --short --branch"
    assert result["results"]["status"]["command_class"] == "readonly"
    assert result["results"]["branch"]["command_class"] == "readonly"
    assert result["results"]["status"]["consent_required"] is False
    assert Path(result["results"]["status"]["artifact"]).exists()


def test_repo_capabilities_contains_registry_and_stack(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_status")
    monkeypatch.setattr(module, "detect_stack", lambda: {"python_file_count": 1})

    result = module.repo_capabilities({"source": "test"}, tmp_path / "job")

    assert result["ok"] is True
    assert result["tool"] == "repo_capabilities"
    assert "runtime_contract" in result["registry"]
    assert result["stack"]["python_file_count"] == 1
    assert result["input_args"] == {"source": "test"}


def test_repo_tools_facade_exports_status_tools() -> None:
    from aicarmine_broker.repo_tools import detect_stack, repo_capabilities, repo_status
    from aicarmine_broker.tools.repo_status import detect_stack as split_detect_stack
    from aicarmine_broker.tools.repo_status import repo_capabilities as split_capabilities
    from aicarmine_broker.tools.repo_status import repo_status as split_status

    assert detect_stack is split_detect_stack
    assert repo_capabilities is split_capabilities
    assert repo_status is split_status
