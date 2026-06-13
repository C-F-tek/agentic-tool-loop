from __future__ import annotations

import subprocess
import sys
import types
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


def test_endpoint_and_task_model_are_rejected() -> None:
    endpoint, problem = local_subagent_mcp_server._validate_ollama_endpoint("http://127.0.0.1:11435/api/chat")
    model, model_problem = local_subagent_mcp_server._validate_model("gpu0/qwen3-task-8k")

    assert endpoint is None
    assert problem is not None
    assert problem["error"] == "ollama_endpoint_not_allowlisted"
    assert 11435 in problem["forbidden_ports"]
    assert model is None
    assert model_problem is not None
    assert model_problem["error"] == "reserved_task_model_rejected"


def test_repo_read_is_path_sandboxed(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("hello\nworld\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    ok = local_subagent_mcp_server._repo_read({"path": "README.md"}, root)
    rejected = local_subagent_mcp_server._repo_read({"path": str(outside)}, root)

    assert ok["ok"] is True
    assert ok["content"] == "hello\nworld"
    assert rejected["ok"] is False
    assert rejected["error"] == "path_not_under_codex_mcp_repo_root"


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="git unavailable")
def test_capabilities_report_readonly_surface(tmp_path) -> None:
    _git_init(tmp_path)

    capabilities = local_subagent_mcp_server._capabilities({}, tmp_path)
    surface = local_subagent_mcp_server._tool_surface({}, tmp_path)

    assert capabilities["ok"] is True
    assert capabilities["codex_app_subagents_inherited"] is False
    assert capabilities["write_tools"] == []
    assert "repo_read" in surface["tool_names"]
    assert "git_diff" in surface["tool_names"]
    assert all("apply" not in name for name in surface["tool_names"])


def test_explicit_empty_allowed_tools_means_no_tools(tmp_path) -> None:
    surface = local_subagent_mcp_server._tool_surface({"allowed_tools": []}, tmp_path)

    assert surface["ok"] is True
    assert surface["tool_names"] == []
    assert surface["ollama_tools"] == []


def test_run_readonly_rejects_no_tools_without_diagnostic_flag(monkeypatch, tmp_path) -> None:
    def fail_chat(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("Ollama should not be called for operational no-tool runs")

    monkeypatch.setattr(local_subagent_mcp_server, "_ollama_chat", fail_chat)

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Say one word.",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3.5:9b-coding",
            "allowed_tools": [],
            "include_project_preseed": False,
        },
        tmp_path,
    )

    assert result["ok"] is False
    assert result["error"] == "no_tools_requires_diagnostic_flag"


def test_run_readonly_uses_mocked_ollama_tool_loop(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("project facts\n", encoding="utf-8")
    responses = [
        {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "repo_read", "arguments": {"path": "README.md", "max_chars": 4000}}}]}},
        {"message": {"role": "assistant", "content": "README.md contains project facts."}},
    ]

    def fake_chat(endpoint: str, payload: dict[str, object], timeout_seconds: int) -> dict[str, object]:
        assert endpoint == "http://127.0.0.1:11434/api/chat"
        assert payload["model"] == "qwen3.5:9b-coding"
        assert timeout_seconds == 120
        return responses.pop(0)

    monkeypatch.setattr(local_subagent_mcp_server, "_ollama_chat", fake_chat)

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Read the README and summarize one fact.",
            "model": "qwen3.5:9b-coding",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "allowed_tools": ["repo_read"],
            "required_tools": ["repo_read"],
            "min_tool_calls": 1,
            "max_tool_rounds": 2,
            "include_project_preseed": False,
        },
        root,
    )

    assert result["ok"] is True
    assert result["response"] == "README.md contains project facts."
    assert result["tool_call_count"] == 1
    assert result["successful_tool_call_count"] == 1
    assert result["tool_transcript"][0]["tool"] == "repo_read"
    assert result["tool_transcript"][0]["ok"] is True


def test_repo_search_handles_empty_stdout_from_rg(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    class FakeCompletedProcess:
        returncode = 1
        stdout = None
        stderr = None

    monkeypatch.setattr(local_subagent_mcp_server.shutil, "which", lambda _name: "rg.exe")
    monkeypatch.setattr(local_subagent_mcp_server.subprocess, "run", lambda *args, **kwargs: FakeCompletedProcess())

    result = local_subagent_mcp_server._repo_search_rg({"path": ".", "pattern": "missing"}, root)

    assert result["ok"] is True
    assert result["matches"] == []
    assert result["stderr_tail"] == ""


def test_run_readonly_reports_empty_final_response(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    monkeypatch.setattr(
        local_subagent_mcp_server,
        "_ollama_chat",
        lambda _endpoint, _payload, _timeout_seconds: {"message": {"role": "assistant", "content": ""}},
    )

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Say one word.",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3.5:9b-coding",
            "allowed_tools": [],
            "diagnostic_no_tools": True,
            "include_project_preseed": False,
        },
        root,
    )

    assert result["ok"] is False
    assert result["error"] == "empty_final_response"
    assert result["tool_call_count"] == 0


def test_run_readonly_fails_when_required_tool_is_not_used(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    monkeypatch.setattr(
        local_subagent_mcp_server,
        "_ollama_chat",
        lambda _endpoint, _payload, _timeout_seconds: {"message": {"role": "assistant", "content": "Answer without evidence."}},
    )

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Read the README and summarize one fact.",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3.5:9b-coding",
            "allowed_tools": ["repo_read"],
            "required_tools": ["repo_read"],
            "min_tool_calls": 1,
            "include_project_preseed": False,
        },
        root,
    )

    assert result["ok"] is False
    assert result["error"] == "required_tool_evidence_missing"
    assert result["missing_required_tools"] == ["repo_read"]
    assert result["successful_tool_call_count"] == 0


def test_run_readonly_retries_final_after_successful_tool_evidence(monkeypatch, tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("project facts\n", encoding="utf-8")
    responses = [
        {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "repo_read", "arguments": {"path": "README.md"}}}]}},
        {"message": {"role": "assistant", "content": ""}},
        {"message": {"role": "assistant", "content": "Final answer from README evidence."}},
    ]

    def fake_chat(_endpoint: str, payload: dict[str, object], _timeout_seconds: int) -> dict[str, object]:
        if len(responses) == 1:
            assert "tools" not in payload
        return responses.pop(0)

    monkeypatch.setattr(local_subagent_mcp_server, "_ollama_chat", fake_chat)

    result = local_subagent_mcp_server._run_readonly(
        {
            "task": "Read the README and summarize one fact.",
            "endpoint": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3.5:9b-coding",
            "allowed_tools": ["repo_read"],
            "required_tools": ["repo_read"],
            "min_tool_calls": 1,
            "include_project_preseed": False,
        },
        root,
    )

    assert result["ok"] is True
    assert result["response"] == "Final answer from README evidence."
    assert result["tool_call_count"] == 1
    assert result["successful_tool_call_count"] == 1
    assert result["finalization_retry_performed"] is True


def test_repo_list_files_matches_query_terms(tmp_path) -> None:
    root = tmp_path / "repo"
    target = root / "services" / "codex_bridge" / "local_subagent_mcp_server.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('x')\n", encoding="utf-8")

    result = local_subagent_mcp_server._repo_list_files(
        {"query": "codex_bridge mcp local subagent", "suffix": ".py"},
        root,
    )

    assert result["ok"] is True
    assert result["files"] == ["services\\codex_bridge\\local_subagent_mcp_server.py"] or result["files"] == ["services/codex_bridge/local_subagent_mcp_server.py"]


def test_memory_search_normalizes_project_local_scope(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_search(args: dict[str, object], _root: Path) -> dict[str, object]:
        captured.update(args)
        return {"ok": True, "records": [], "count": 0}

    monkeypatch.setitem(sys.modules, "project_memory_mcp_server", types.SimpleNamespace(_search=fake_search))

    result = local_subagent_mcp_server._memory_search({"query": "approval", "scope": "project-local"}, tmp_path)

    assert result["ok"] is True
    assert captured["scope"] == "repo"
    assert result["proxied_by"] == "aicarmine_local_subagent"


def test_unwrap_mcp_text_json_result() -> None:
    result = local_subagent_mcp_server._unwrap_mcp_text_json(
        {"content": [{"type": "text", "text": "{\"ok\": true, \"chunks\": []}"}]}
    )

    assert result["ok"] is True
    assert result["chunks"] == []
    assert result["mcp_text_unwrapped"] is True


def test_rag_context_caps_large_model_requests(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_context(args: dict[str, object]) -> dict[str, object]:
        captured.update(args)
        return {"ok": True, "chunks": [], "used_chars": 0}

    monkeypatch.setitem(sys.modules, "rag_mcp_server", types.SimpleNamespace(_handle_context_tool=fake_context))

    result = local_subagent_mcp_server._rag_context(
        {
            "query": "local subagent",
            "top_k": 20,
            "candidate_limit": 200,
            "max_total_chars": 50000,
            "max_chunk_chars": 20000,
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert captured["top_k"] == 8
    assert captured["candidate_limit"] == 120
    assert captured["max_total_chars"] == 16000
    assert captured["max_chunk_chars"] == 6000


def test_project_preseed_reads_known_repo_files(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("agent contract", encoding="utf-8")
    (root / "README.md").write_text("readme contract", encoding="utf-8")

    context, sources, truncated = local_subagent_mcp_server._project_preseed(
        {"preseed_paths": ["AGENTS.md", "README.md"], "preseed_max_chars": 2000},
        root,
    )

    assert "agent contract" in context
    assert "readme contract" in context
    assert [source["path"] for source in sources] == ["AGENTS.md", "README.md"]
    assert truncated is False


def test_health_keeps_codex_root_isolation_fields(tmp_path, monkeypatch) -> None:
    _git_init(tmp_path)
    monkeypatch.setenv("AICARMINE_CODEX_MCP_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AICARMINE_LAB_REPO", "C:\\agentic-loop-shadow")
    tools = local_subagent_mcp_server._tools()

    health = local_subagent_mcp_server._health({}, tmp_path, tools)

    assert health["ok"] is True
    assert health["repo_root"] == str(tmp_path)
    assert health["root_isolation"]["codex_mcp_repo_root"] == str(tmp_path)
    assert "process" in health["root_isolation"]["note"]
