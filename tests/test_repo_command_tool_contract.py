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
    assert result["command_class"] == "destructive"
    assert result["required_consent"] == "confirm command execution"
    assert result["policy"] == "destructive command requires explicit consent"
    assert result["command_execution_policy"]["schema"] == "command_execution_policy.v1"
    assert result["command_execution_policy"]["diagnostic_only"] is True


def test_repo_command_success_payload_contains_command_class_and_policy(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")

    def fake_run_ps(command: str, timeout: int = 120) -> dict[str, object]:
        return {"returncode": 0, "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(module, "run_ps", fake_run_ps)

    result = module.repo_command(
        {"command": "git status --short"},
        tmp_path,
        allow_command=True,
        user_consent="",
    )

    assert result["ok"] is True
    assert result["command_class"] == "readonly"
    assert result["consent_required"] is False
    assert result["policy"] == "readonly command allowed by policy"
    assert result["command_execution_policy"]["schema"] == "command_execution_policy.v1"
    assert result["command_execution_policy"]["does_not_execute"] is True


def test_command_classification_requires_consent_for_unknown_write_and_destructive() -> None:
    from aicarmine_broker.tools.command_safety import classify_command

    assert classify_command("git status --short").command_class == "readonly"
    assert classify_command("git branch --show-current").command_class == "readonly"
    assert classify_command("git diff --name-status HEAD").command_class == "readonly"
    assert classify_command("git grep -n -- needle").command_class == "readonly"
    assert classify_command("rg -n needle .").command_class == "readonly"
    assert classify_command("fd needle .").command_class == "readonly"
    assert classify_command("Format-Table -AutoSize").command_class == "readonly"
    assert classify_command("python -m pytest").command_class == "validation"
    assert classify_command("Set-Content a.txt x").command_class == "write"
    assert classify_command("Remove-Item -Recurse .").command_class == "destructive"
    assert classify_command("git apply --check patch.diff; git apply patch.diff").command_class == "write"
    assert classify_command("rm old.txt").command_class == "destructive"
    assert classify_command("format C:").command_class == "destructive"
    assert classify_command("custom-tool --do-thing").command_class == "unknown"
    assert classify_command("custom-tool --do-thing").consent_required is True


def test_repo_command_runs_with_consent_and_compile_alias(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    observed: dict[str, object] = {}
    (tmp_path / "services" / "aicarmine_broker").mkdir(parents=True)
    (tmp_path / "services" / "vulkan_bridge").mkdir(parents=True)

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
    assert "services/aicarmine_broker" in str(observed["command"])
    assert "services/vulkan_bridge" in str(observed["command"])
    assert observed["timeout"] == 12
    assert Path(result["artifact"]).exists()


def test_compile_alias_uses_core_services_as_last_layout_fallback(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "services" / "aicarmine_broker").mkdir(parents=True)
    (tmp_path / "services" / "vulkan_bridge").mkdir(parents=True)

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ("services/aicarmine_broker", "services/vulkan_bridge")
    assert resolution["source"] == "configured_core_services"


def test_compile_alias_uses_core_evidence_from_tool_history(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    package = tmp_path / "services" / "aicarmine_broker"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "planner.py").write_text("x = 1\n", encoding="utf-8")
    history = [
        {
            "decision": {"tool": "repo_read", "arguments": {"path": "services/aicarmine_broker/planner.py"}},
            "tool_result": {
                "tool": "repo_read",
                "ok": True,
                "items": [{"ok": True, "path": "services/aicarmine_broker/planner.py"}],
            },
        }
    ]

    resolution = module.resolve_compile_targets({}, tmp_path, history=history)

    assert resolution["targets"] == ("services/aicarmine_broker",)
    assert resolution["source"] == "core_project_evidence"


def test_compile_alias_uses_pyproject_src_layout_when_no_evidence(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    package = tmp_path / "src" / "demo_pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ("src/demo_pkg",)
    assert resolution["source"] == "pyproject"


def test_compile_alias_uses_pyproject_setuptools_packages(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.setuptools]\npackages=['demo_pkg']\n",
        encoding="utf-8",
    )
    package = tmp_path / "demo_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    ignored = tmp_path / "ignored_pkg"
    ignored.mkdir()
    (ignored / "__init__.py").write_text("", encoding="utf-8")

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ("demo_pkg",)
    assert resolution["source"] == "pyproject"


def test_compile_alias_uses_pyproject_setuptools_find_where(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.setuptools.packages.find]\nwhere=['lib']\n",
        encoding="utf-8",
    )
    package = tmp_path / "lib" / "demo_pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ("lib/demo_pkg",)
    assert resolution["source"] == "pyproject"


def test_compile_alias_uses_explicit_path_even_when_core_dirs_exist(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "services" / "aicarmine_broker").mkdir(parents=True)
    (tmp_path / "services" / "vulkan_bridge").mkdir(parents=True)
    target = tmp_path / "package"
    target.mkdir()

    resolution = module.resolve_compile_targets({"path": "package"}, tmp_path)

    assert resolution["targets"] == ("package",)
    assert resolution["source"] == "explicit_path"


def test_compile_alias_uses_configured_targets(tmp_path: Path, monkeypatch) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "services" / "aicarmine_broker").mkdir(parents=True)
    (tmp_path / "services" / "vulkan_bridge").mkdir(parents=True)
    target = tmp_path / "configured"
    target.mkdir()
    monkeypatch.setenv("AICARMINE_COMPILE_TARGETS", "configured")

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ("configured",)
    assert resolution["source"] == "configured_targets"


def test_compile_alias_does_not_default_to_ia_carmine_tools(tmp_path: Path) -> None:
    module = import_module("aicarmine_broker.tools.repo_command")
    (tmp_path / "ia_carmine").mkdir()
    (tmp_path / "Tools").mkdir()

    resolution = module.resolve_compile_targets({}, tmp_path)

    assert resolution["targets"] == ()
    assert resolution["errors"] == ("compile_targets_not_resolved",)


def test_repo_tools_facade_exports_repo_command_and_safety() -> None:
    from aicarmine_broker.repo_tools import dangerous_command, repo_command
    from aicarmine_broker.tools.command_safety import dangerous_command as split_safety
    from aicarmine_broker.tools.repo_command import repo_command as split_command

    assert repo_command is split_command
    assert dangerous_command is split_safety
