from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_repo_validate_stops_on_failure_by_default(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_validate")
    calls: list[str] = []

    def fake_run_ps(command: str, timeout: int = 300) -> dict[str, object]:
        calls.append(command)
        return {"returncode": 1, "stdout_tail": "", "stderr_tail": "failed"}

    monkeypatch.setattr(module, "_run_ps", fake_run_ps)

    result = module.repo_validate(
        {"commands": ["python -m pytest first", "python -m pytest second"]},
        tmp_path,
    )

    assert result["ok"] is False
    assert calls == ["python -m pytest first"]
    assert result["results"][0]["command_class"] == "validation"
    assert result["results"][0]["stderr_tail"] == "failed"


def test_repo_validate_continue_on_failure_runs_all_commands(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_validate")
    returncodes = iter([1, 0])

    def fake_run_ps(command: str, timeout: int = 300) -> dict[str, object]:
        return {"returncode": next(returncodes), "stdout_tail": command, "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_ps", fake_run_ps)

    result = module.repo_validate(
        {
            "commands": ["python -m pytest first", "python -m pytest second"],
            "continue_on_failure": True,
        },
        tmp_path,
    )

    assert result["ok"] is False
    assert [item["command"] for item in result["results"]] == [
        "python -m pytest first",
        "python -m pytest second",
    ]
    assert [item["command_class"] for item in result["results"]] == [
        "validation",
        "validation",
    ]
    assert Path(tmp_path / "tool-results").exists()


def test_repo_validate_blocks_unknown_custom_command_without_running(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_validate")
    calls: list[str] = []

    def fake_run_ps(command: str, timeout: int = 300) -> dict[str, object]:
        calls.append(command)
        return {"returncode": 0, "stdout_tail": command, "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_ps", fake_run_ps)

    result = module.repo_validate({"commands": ["custom-tool --do-thing"]}, tmp_path)

    assert result["ok"] is False
    assert calls == []
    assert result["results"][0]["error"] == "command_requires_consent"
    assert result["results"][0]["command_class"] == "unknown"
    assert result["results"][0]["consent_required"] is True


def test_repo_validate_default_compile_uses_resolved_targets(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_validate")
    repo_root = tmp_path / "repo"
    package = repo_root / "src" / "demo_pkg"
    package.mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    calls: list[str] = []

    def fake_run_ps(command: str, timeout: int = 300) -> dict[str, object]:
        calls.append(command)
        return {"returncode": 0, "stdout_tail": command, "stderr_tail": ""}

    monkeypatch.setattr(module, "LAB_REPO", repo_root)
    monkeypatch.setattr(module, "_run_ps", fake_run_ps)

    result = module.repo_validate({}, tmp_path / "job")

    assert result["ok"] is True
    assert calls[0] == "git diff --check"
    assert "src/demo_pkg" in calls[1]
    assert "ia_carmine" not in calls[1]
    assert "Tools" not in calls[1]
    assert [item["command_class"] for item in result["results"]] == ["readonly", "validation"]
    assert result["compile_target_resolution"]["targets"] == ("src/demo_pkg",)


def test_repo_tools_facade_exports_repo_validate() -> None:
    from aicarmine_broker.repo_tools import repo_validate as facade_repo_validate
    from aicarmine_broker.tools.repo_validate import repo_validate

    assert facade_repo_validate is repo_validate
