from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import ops_mcp_server  # noqa: E402


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def _frame(payload: dict[str, object]) -> bytes:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def test_parse_content_length_mcp_messages() -> None:
    messages = [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
    ]
    raw = b"".join(_frame(message) for message in messages)

    assert ops_mcp_server._parse_mcp_messages(raw, "content-length") == messages


def test_mcp_smoke_list_targets_is_static_allowlist(tmp_path) -> None:
    result = ops_mcp_server.mcp_smoke_list_targets({}, tmp_path)
    names = {item["name"] for item in result["targets"]}

    assert result["ok"] is True
    assert result["allowlist_only"] is True
    assert "aicarmine_repo_state" in names
    assert "aicarmine_project_memory" in names
    assert "vulkan_helper" not in names


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_mcp_smoke_run_repo_state_content_length(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    _git_init(root)
    monkeypatch.setenv("CODEX_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("AICARMINE_LAB_REPO", str(root))

    result = ops_mcp_server.mcp_smoke_run(
        {
            "servers": ["aicarmine_repo_state"],
            "transport": "content-length",
            "timeout_seconds": 30,
            "call_health": True,
        },
        root,
    )

    assert result["ok"] is True
    server = result["servers"][0]
    assert server["initialize_ok"] is True
    assert server["tools_list_ok"] is True
    assert server["health_ok"] is True
    assert "aicarmine_repo_state_health" in server["tools"]


def test_service_state_logs_bounds_reads_and_rejects_outside_root(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_path = logs_dir / "demo.log"
    log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = ops_mcp_server.service_state_logs(
        {
            "paths": ["logs/demo.log", "..\\outside.log"],
            "max_lines": 2,
            "max_bytes": 1024,
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert result["entry_count"] == 1
    assert result["entries"][0]["tail"] == "two\nthree"
    assert result["rejected"] == ["..\\outside.log"]


def test_process_command_lines_are_redacted() -> None:
    rows = [
        {
            "ProcessId": 123,
            "Name": "python.exe",
            "CommandLine": "python app.py --api-key abc123 token=def456 password=secret",
        }
    ]

    redacted = ops_mcp_server.redact_process_rows(rows)

    assert redacted[0]["CommandLine"] == "python app.py --api-key <redacted> token=<redacted> password=<redacted>"


def test_ops_mcp_server_does_not_probe_http_health() -> None:
    source = Path(ops_mcp_server.__file__).read_text(encoding="utf-8")

    assert "Invoke-RestMethod" not in source
    assert "Invoke-WebRequest" not in source
    assert "curl.exe" not in source
    assert "/health" not in source
