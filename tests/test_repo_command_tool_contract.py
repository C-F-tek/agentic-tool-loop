from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_dangerous_command_detection() -> None:
    from aicarmine_broker.tools.command_safety import dangerous_command

    assert dangerous_command("git reset --hard")
    assert dangerous_command("Remove-Item -Recurse .")
    assert not dangerous_command("git status --short")


def test_repo_command_respects_allow_command(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")

    result = module.repo_command(
        {"command": "git status"},
        tmp_path,
        allow_command=False,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["error"] == "commands disabled by request"


def test_repo_command_blocks_dangerous_without_consent(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")

    result = module.repo_command(
        {"command": "git reset --hard"},
        tmp_path,
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["needs_consent"] is True


def test_repo_command_runs_with_consent_and_compile_alias(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    observed: dict[str, object] = {}

    def fake_run_ps(command: str, timeout: int = 120) -> dict[str, object]:
        observed["command"] = command
        observed["timeout"] = timeout
        return {"returncode": 0, "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(module, "run_ps", fake_run_ps)

    result = module.repo_command(
        {"command": "compile", "timeout_seconds": 12},
        tmp_path,
        allow_command=True,
        user_consent="confirm",
    )

    assert result["ok"] is True
    assert "compileall" in str(observed["command"])
    assert observed["timeout"] == 12
    assert Path(result["artifact"]).exists()


def test_repo_tools_facade_exports_repo_command_and_safety() -> None:
    from aicarmine_broker.repo_tools import dangerous_command, repo_command
    from aicarmine_broker.tools.command_safety import dangerous_command as split_safety
    from aicarmine_broker.tools.repo_command import repo_command as split_command

    assert repo_command is split_command
    assert dangerous_command is split_safety
