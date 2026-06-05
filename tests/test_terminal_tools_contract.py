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


def test_terminal_list_files_payload_marks_path_normalization(monkeypatch, tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Users" / "carmi"))
    home = tmp_path / "Users" / "carmi"
    home.mkdir(parents=True)
    (home / "alpha.txt").write_text("x", encoding="utf-8")

    result = module.terminal_list_files(
        {"directory": "\\Users\\carmi", "pattern": "*.txt"},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["path_normalized"] is True
    assert result["normalization_reason"] == "missing_drive_under_users"
    assert result["input_directory"] == "\\Users\\carmi"


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
    assert searched["search_complete"] is True
    assert searched["search_quality"]["schema"] == "search_quality.v1"
    assert searched["search_quality"]["quality"] == "complete"
    assert searched["scanned_files"] == 2
    assert searched["content_read_attempts"] == 2
    assert searched["content_read_ok"] == 2


def test_terminal_run_command_repairs_readonly_unix_command(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    observed: dict[str, object] = {}

    def fake_run_powershell_body(body: str, cwd: Path, timeout: int) -> dict[str, object]:
        observed["body"] = body
        observed["cwd"] = cwd
        observed["timeout"] = timeout
        return {"returncode": 0, "stdout": "ok", "stderr": "", "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_powershell_body", fake_run_powershell_body)

    result = module.terminal_run_command_wait(
        {"command": "ls -la", "cwd": str(tmp_path)},
        tmp_path / "job",
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is True
    assert result["auto_repaired"] is True
    assert result["original_command"] == "ls -la"
    assert "Get-ChildItem" in result["repaired_command"]
    assert "Get-ChildItem" in str(observed["body"])
    assert result["tool"] == "terminal_run_command_wait"


def test_terminal_contract_distinguishes_external_and_internal_path_policy() -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    contract = module.terminal_environment_contract()

    assert contract["path_rules"]["external_open_terminal_requires_drive"] is True
    assert contract["path_rules"]["internal_tool_normalizes_missing_drive"] is True
    assert contract["path_rules"]["recommended_path_format"] == "C:\\Users\\..."


def test_terminal_repairs_pwd_find_and_grep_readonly(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    bodies: list[str] = []

    def fake_run_powershell_body(body: str, cwd: Path, timeout: int) -> dict[str, object]:
        bodies.append(body)
        return {"returncode": 0, "stdout": "ok", "stderr": "", "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_powershell_body", fake_run_powershell_body)

    for command in ("pwd", "find . -type f", "grep needle file.txt"):
        result = module.terminal_run_command_wait(
            {"command": command, "cwd": str(tmp_path)},
            tmp_path / "job",
            allow_command=True,
            user_consent="",
        )
        assert result["ok"] is True
        assert result["auto_repaired"] is True
        assert result["repair_class"] == "readonly"

    assert any("(Get-Location).Path" in body for body in bodies)
    assert any("Get-ChildItem -Recurse -File" in body for body in bodies)
    assert any("Select-String" in body for body in bodies)


def test_terminal_does_not_auto_repair_write_like_unix_command(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")

    result = module.terminal_run_command_wait(
        {"command": "rm -rf .", "cwd": str(tmp_path)},
        tmp_path / "job",
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["needs_consent"] is True
    assert result["command_class"] == "destructive"
    assert result["required_consent"] == "confirm command execution"
    assert result["policy"] == "destructive command requires explicit consent"
    assert result["command_execution_policy"]["schema"] == "command_execution_policy.v1"


def test_terminal_does_not_auto_repair_embedded_readonly_tail(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")

    result = module.terminal_run_command_wait(
        {"command": "rm -rf .; ls -la", "cwd": str(tmp_path)},
        tmp_path / "job",
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["needs_consent"] is True
    assert result["command_class"] == "destructive"
    assert result["required_consent"] == "confirm command execution"
    assert "auto_repaired" not in result


def test_terminal_search_marks_incomplete_on_limit_truncation(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    work = tmp_path / "work"
    work.mkdir()
    for index in range(3):
        (work / f"match-{index}.txt").write_text("needle\n", encoding="utf-8")

    result = module.terminal_search_files(
        {"directory": str(work), "query": "needle", "content": True, "limit": 1},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["search_complete"] is False
    assert result["count"] == 1


def test_terminal_search_counts_unreadable_files(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    work = tmp_path / "work"
    work.mkdir()
    (work / "ok.txt").write_text("needle\n", encoding="utf-8")
    (work / "blocked.txt").write_text("needle\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        if self.name == "blocked.txt":
            raise PermissionError("blocked")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = module.terminal_search_files(
        {"directory": str(work), "query": "needle", "content": True},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["search_complete"] is False
    assert result["unreadable_files"] == 1
    assert result["content_read_attempts"] == 2
    assert result["content_read_ok"] == 1
    assert result["skipped_errors_preview"][0]["error_type"] == "PermissionError"


def test_terminal_search_content_reads_filename_matches_for_completeness(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    work = tmp_path / "work"
    work.mkdir()
    (work / "needle-blocked.txt").write_text("x\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        if self.name == "needle-blocked.txt":
            raise PermissionError("blocked")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = module.terminal_search_files(
        {"directory": str(work), "query": "needle", "content": True},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["filename_matches"] == 1
    assert result["content_read_attempts"] == 1
    assert result["unreadable_files"] == 1
    assert result["search_complete"] is False


def test_terminal_search_errors_preview_is_bounded(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.terminal")
    work = tmp_path / "work"
    work.mkdir()
    for index in range(12):
        (work / f"blocked-{index}.txt").write_text("needle\n", encoding="utf-8")

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        raise PermissionError("blocked")

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = module.terminal_search_files(
        {"directory": str(work), "query": "needle", "content": True},
        tmp_path / "job",
    )

    assert result["ok"] is True
    assert result["search_complete"] is False
    assert result["unreadable_files"] == 12
    assert len(result["skipped_errors_preview"]) == 10


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
        user_consent="confirm",
    )

    assert result["ok"] is True
    assert str(observed["body"]).endswith("| Out-String")
    assert observed["cwd"] == tmp_path.resolve(strict=False)
    assert observed["timeout"] == 5
    assert result["command_class"] == "unknown"
    assert result["consent_required"] is True
    assert result["policy"] == "unknown command requires explicit consent"
    assert result["command_execution_policy"]["schema"] == "command_execution_policy.v1"
    assert Path(result["artifact"]).exists()


def test_repo_tools_facade_exports_terminal_tools() -> None:
    from aicarmine_broker.repo_tools import terminal_environment_contract, terminal_list_files
    from aicarmine_broker.tools.terminal import terminal_environment_contract as split_contract
    from aicarmine_broker.tools.terminal import terminal_list_files as split_list_files

    assert terminal_environment_contract is split_contract
    assert terminal_list_files is split_list_files
