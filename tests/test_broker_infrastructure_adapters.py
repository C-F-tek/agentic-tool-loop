from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_safe_rel_path_rejects_absolute_path() -> None:
    from aicarmine_broker.infrastructure import safe_rel_path

    with pytest.raises(ValueError):
        safe_rel_path("C:/Users/carmi/AI/AGENTS.md")


def test_safe_rel_path_rejects_parent_escape() -> None:
    from aicarmine_broker.infrastructure import safe_rel_path

    with pytest.raises(ValueError):
        safe_rel_path("../AGENTS.md")


def test_filesystem_repo_reads_real_content(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import FilesystemRepo

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("hello", encoding="utf-8")
    repo = FilesystemRepo(tmp_path)

    assert repo.exists("docs/a.md")
    assert repo.read_text("docs/a.md") == "hello"
    assert repo.list_files("docs") == ("docs/a.md",)


def test_json_file_store_roundtrip(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import JsonFileStore

    store = JsonFileStore()
    target = tmp_path / "state" / "job.json"

    store.write(target, {"ok": True})

    assert store.read(target) == {"ok": True}


def test_executable_resolver_prefers_active_venv(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import ExecutableResolver

    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    python = scripts / "python.exe"
    python.write_text("", encoding="utf-8")
    tool = scripts / "demo.exe"
    tool.write_text("", encoding="utf-8")

    resolver = ExecutableResolver(active_python=python)

    assert resolver.resolve("demo") == str(tool.resolve(strict=False))


def test_command_runner_returns_returncode_stdout_stderr(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import SubprocessCommandRunner

    runner = SubprocessCommandRunner()
    result = runner.run(
        (sys.executable, "-c", "print('AIC_OK')"),
        cwd=tmp_path,
        timeout_seconds=10,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "AIC_OK"
    assert result.stderr == ""
