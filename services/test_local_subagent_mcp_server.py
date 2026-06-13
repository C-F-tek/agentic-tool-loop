from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import local_subagent_mcp_server  # noqa: E402


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="git unavailable")
def test_capabilities_report_agentic_loop_facade(tmp_path) -> None:
    _git_init(tmp_path)

    capabilities = local_subagent_mcp_server._capabilities({}, tmp_path)

    assert capabilities["ok"] is True
    assert capabilities["mode"] == "dedicated_agentic_loop_facade"
    assert capabilities["delegates_to"] == "aicarmine_agentic_loop_run"
    assert capabilities["default_port"] == 3579
    assert capabilities["codex_app_subagents_inherited"] is False
    assert capabilities["write_tools"] == []
    assert capabilities["direct_ollama_mode_removed"] is True
    assert capabilities["no_agentic_loop"] is False


def test_tools_do_not_expose_direct_ollama_or_local_tool_surface() -> None:
    tools = local_subagent_mcp_server._tools()

    assert set(tools) == {
        "aicarmine_local_subagent_health",
        "aicarmine_local_subagent_capabilities",
        "aicarmine_local_subagent_run_readonly",
    }
    schema = tools["aicarmine_local_subagent_run_readonly"].input_schema
    properties = schema["properties"]

    assert "model" not in properties
    assert "allowed_tools" not in properties
    assert "endpoint" in properties
    assert properties["port"]["default"] == 3579
    assert properties["endpoint"]["default"].startswith("http://127.0.0.1:3579/")


def test_run_readonly_delegates_to_agentic_loop_client(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run(args: dict[str, object], root: Path) -> dict[str, object]:
        captured["args"] = dict(args)
        captured["root"] = root
        return {
            "ok": True,
            "tool": "aicarmine_agentic_loop_run",
            "agentic_loop_called": True,
            "port": 3579,
            "codex_mcp_repo_root": str(root),
        }

    monkeypatch.setattr(local_subagent_mcp_server.agentic_loop_client, "_run", fake_run)

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Review the preplanner semantic intent routing.",
            "initial_context": "verified context",
            "confirm_agentic_loop": "aicarmine_agentic_loop_run",
            "ensure_broker": True,
            "confirm_ensure_broker": "aicarmine_agentic_loop_ensure_broker",
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert result["tool"] == "aicarmine_local_subagent_run_readonly"
    assert result["delegated_tool"] == "aicarmine_agentic_loop_run"
    assert result["delegated_to_agentic_loop"] is True
    assert result["direct_ollama_mode_removed"] is True
    assert result["no_agentic_loop"] is False
    args = captured["args"]
    assert isinstance(args, dict)
    assert args["approval_mode"] == "read_only"
    assert args["confirm_agentic_loop"] == "aicarmine_agentic_loop_run"
    assert "Contratto subagent locale" in str(args["task"])
    nested_args = args["arguments"]
    assert isinstance(nested_args, dict)
    context = nested_args["context"]
    assert isinstance(context, dict)
    assert context["local_subagent_initial_context"] == "verified context"
    assert context["local_subagent_contract"]["execution"] == "dedicated_agentic_loop"


def test_run_readonly_forces_read_only_even_if_caller_requests_write(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run(args: dict[str, object], root: Path) -> dict[str, object]:
        del root
        captured.update(args)
        return {"ok": True, "tool": "aicarmine_agentic_loop_run"}

    monkeypatch.setattr(local_subagent_mcp_server.agentic_loop_client, "_run", fake_run)

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Inspect a risky planner area.",
            "confirm_agentic_loop": "aicarmine_agentic_loop_run",
            "approval_mode": "apply",
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert captured["approval_mode"] == "read_only"


def test_run_readonly_requires_agentic_loop_confirmation(tmp_path) -> None:
    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Review the preplanner semantic intent routing.",
        },
        tmp_path,
    )

    assert result["ok"] is False
    assert result["error"] == "explicit_agentic_loop_confirmation_required"
    assert result["agentic_loop_called"] is False


def test_health_keeps_codex_root_isolation_fields(tmp_path, monkeypatch) -> None:
    _git_init(tmp_path)
    monkeypatch.setenv("AICARMINE_CODEX_MCP_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AICARMINE_LAB_REPO", "C:\\agentic-loop-shadow")
    tools = local_subagent_mcp_server._tools()

    health = local_subagent_mcp_server._health({}, tmp_path, tools)

    assert health["ok"] is True
    assert health["repo_root"] == str(tmp_path)
    assert health["root_isolation"]["codex_mcp_repo_root"] == str(tmp_path)
    assert health["mode"] == "dedicated_agentic_loop_facade"
    assert health["default_port"] == 3579
    assert health["no_broker_http"] is False
    assert health["direct_ollama_mode_removed"] is True
    assert health["no_agentic_loop"] is False
    assert health["root_isolation"]["openwebui_loop_ports_not_used"] == [3571, 3572]
