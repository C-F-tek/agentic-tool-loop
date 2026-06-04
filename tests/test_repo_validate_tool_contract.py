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

    result = module.repo_validate({"commands": ["first", "second"]}, tmp_path)

    assert result["ok"] is False
    assert calls == ["first"]
    assert result["results"][0]["stderr_tail"] == "failed"


def test_repo_validate_continue_on_failure_runs_all_commands(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_validate")
    returncodes = iter([1, 0])

    def fake_run_ps(command: str, timeout: int = 300) -> dict[str, object]:
        return {"returncode": next(returncodes), "stdout_tail": command, "stderr_tail": ""}

    monkeypatch.setattr(module, "_run_ps", fake_run_ps)

    result = module.repo_validate(
        {"commands": ["first", "second"], "continue_on_failure": True},
        tmp_path,
    )

    assert result["ok"] is False
    assert [item["command"] for item in result["results"]] == ["first", "second"]
    assert Path(tmp_path / "tool-results").exists()


def test_repo_tools_facade_exports_repo_validate() -> None:
    from aicarmine_broker.repo_tools import repo_validate as facade_repo_validate
    from aicarmine_broker.tools.repo_validate import repo_validate

    assert facade_repo_validate is repo_validate
