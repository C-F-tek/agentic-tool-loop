from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_normalize_terminal_path_repairs_users_path(monkeypatch, tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Users" / "carmi"))
    home = tmp_path / "Users" / "carmi"
    home.mkdir(parents=True)

    result = module.normalize_terminal_path("\\Users\\carmi", base=tmp_path)

    assert str(result).lower().endswith("users\\carmi")


def test_terminal_list_files_and_search_use_real_directory(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    work = tmp_path / "work"
    work.mkdir()
    (work / "alpha.txt").write_text("needle\n", encoding="utf-8")
    (work / "beta.md").write_text("other\n", encoding="utf-8")

    listed = module.terminal_list_files({"directory": str(work), "pattern": "*.txt"}, tmp_path / "job")
    searched = module.terminal_search_files({"directory": str(work), "query": "needle", "content": True}, tmp_path / "job")

    assert listed["ok"] is True
    assert [item["name"] for item in listed["items"]] == ["alpha.txt"]
    assert searched["ok"] is True
    assert searched["matches"][0]["match_type"] == "content"


def test_terminal_run_command_rejects_unix_command_before_running(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")

    result = module.terminal_run_command_wait(
        {"command": "ls -la", "cwd": str(tmp_path)},
        tmp_path / "job",
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["error_type"] == "invalid_command_for_windows_shell"
    assert result["tool"] == "terminal_run_command_wait"


def test_terminal_run_command_wait_uses_bounded_runner(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    observed: dict[str, object] = {}

    def fake_run_powershell_body(body: str, cwd: Path, timeout: int) -> dict[str, object]:
        observed["body"] = body
        observed["cwd"] = cwd
        observed["timeout"] = timeout
        return {"returncode": 0, "stdout": "ok", "stderr": "", "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_powershell_body", fake_run_powershell_body)

    result = module.terminal_run_command_wait(
        {"command": "Write-Output ok", "cwd": str(tmp_path), "timeout_seconds": 5},
        tmp_path / "job",
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is True
    assert str(observed["body"]).endswith("| Out-String")
    assert observed["cwd"] == tmp_path.resolve(strict=False)
    assert observed["timeout"] == 5
    assert Path(result["artifact"]).exists()


def test_repo_tools_facade_exports_terminal_tools() -> None:
    from aicarmine_broker.repo_tools import terminal_environment_contract, terminal_list_files
    from aicarmine_broker.tools.terminal import terminal_environment_contract as split_contract
    from aicarmine_broker.tools.terminal import terminal_list_files as split_list_files

    assert terminal_environment_contract is split_contract
    assert terminal_list_files is split_list_files
