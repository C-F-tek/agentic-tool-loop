from __future__ import annotations

import sys
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import agentic_loop_client_mcp_server  # noqa: E402


def test_endpoint_validation_rejects_non_3572_agentic_loop() -> None:
    endpoint, problem = agentic_loop_client_mcp_server._validate_endpoint(
        "http://127.0.0.1:3571/vulkan/agent",
        expected_path="/vulkan/agent",
    )
    wrong_path, wrong_path_problem = agentic_loop_client_mcp_server._validate_endpoint(
        "http://127.0.0.1:3579/health",
        expected_path="/vulkan/agent",
    )
    dedicated, dedicated_problem = agentic_loop_client_mcp_server._validate_endpoint(
        "",
        expected_path="/vulkan/agent",
        port=3579,
    )

    assert endpoint is None
    assert problem is not None
    assert problem["error"] == "agentic_loop_endpoint_not_allowlisted"
    assert problem["reason"] == "reserved_port"
    assert wrong_path is None
    assert wrong_path_problem is not None
    assert wrong_path_problem["reason"] == "path_mismatch"
    assert dedicated == "http://127.0.0.1:3579/vulkan/agent"
    assert dedicated_problem is None


def test_run_requires_explicit_confirmation_before_http(monkeypatch, tmp_path) -> None:
    def fail_get_health(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("broker health must not be called without confirmation")

    def fail_post_agent(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("agentic loop must not be called without confirmation")

    monkeypatch.setattr(agentic_loop_client_mcp_server, "_get_health", fail_get_health)
    monkeypatch.setattr(agentic_loop_client_mcp_server, "_post_agent", fail_post_agent)

    result = agentic_loop_client_mcp_server._run({"task": "Analyze project"}, tmp_path)

    assert result["ok"] is False
    assert result["error"] == "explicit_agentic_loop_confirmation_required"
    assert result["agentic_loop_called"] is False


def test_run_blocks_when_broker_root_differs_from_codex_root(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-root"
    broker_root = tmp_path / "broker-root"
    codex_root.mkdir()
    broker_root.mkdir()

    monkeypatch.setattr(
        agentic_loop_client_mcp_server,
        "_get_health",
        lambda *_args, **_kwargs: {"ok": True, "payload": {"ok": True, "lab_repo": str(broker_root)}},
    )
    monkeypatch.setattr(
        agentic_loop_client_mcp_server,
        "_post_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("agentic loop must not start on wrong root")),
    )

    result = agentic_loop_client_mcp_server._run(
        {
            "task": "Analyze project",
            "confirm_agentic_loop": agentic_loop_client_mcp_server.CONFIRM_RUN,
        },
        codex_root,
    )

    assert result["ok"] is False
    assert result["error"] == "broker_repo_root_mismatch"
    assert result["agentic_loop_called"] is False
    assert result["root_check"]["broker_lab_repo"] == str(broker_root)
    assert result["root_check"]["codex_mcp_repo_root"] == str(codex_root.resolve(strict=False))


def test_run_posts_codex_root_context_when_broker_root_matches(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-root"
    codex_root.mkdir()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        agentic_loop_client_mcp_server,
        "_get_health",
        lambda *_args, **_kwargs: {"ok": True, "payload": {"ok": True, "lab_repo": str(codex_root)}},
    )

    def fake_post_agent(endpoint: str, payload: dict[str, object], timeout_seconds: int) -> dict[str, object]:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {
            "ok": True,
            "http_status": 200,
            "payload": {
                "ok": True,
                "job_id": "job-test",
                "status": "completed",
                "answer_for_30b": "Done with services/codex_bridge/agentic_loop_client_mcp_server.py",
                "tool_context_for_30b": {"history": [{"step": 1, "tool": "repo_read", "ok": True, "path": "AGENTS.md"}]},
            },
        }

    monkeypatch.setattr(agentic_loop_client_mcp_server, "_post_agent", fake_post_agent)

    result = agentic_loop_client_mcp_server._run(
        {
            "task": "Analyze project",
            "confirm_agentic_loop": agentic_loop_client_mcp_server.CONFIRM_RUN,
            "wait_seconds": 3,
            "max_steps": 4,
        },
        codex_root,
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    arguments = payload["arguments"]
    context = payload["context"]
    assert isinstance(arguments, dict)
    assert isinstance(context, dict)
    assert payload["lab_repo"] == str(codex_root.resolve(strict=False))
    assert payload["codex_mcp_repo_root"] == str(codex_root.resolve(strict=False))
    assert captured["endpoint"] == "http://127.0.0.1:3579/vulkan/agent"
    assert arguments["lab_repo"] == str(codex_root.resolve(strict=False))
    assert context["expected_broker_lab_repo"] == str(codex_root.resolve(strict=False))
    assert result["ok"] is True
    assert result["terminal"] is True
    assert result["job_id"] == "job-test"
    assert result["root_check"]["ok"] is True
    assert result["tool_history_digest"][0]["tool"] == "repo_read"


def test_status_and_result_use_canonical_router_payload(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    def fake_post_agent(endpoint: str, payload: dict[str, object], timeout_seconds: int) -> dict[str, object]:
        calls.append({"endpoint": endpoint, "payload": payload, "timeout_seconds": timeout_seconds})
        return {"ok": True, "http_status": 200, "payload": {"ok": True, "job_id": "job-test", "status": "completed"}}

    monkeypatch.setattr(agentic_loop_client_mcp_server, "_post_agent", fake_post_agent)

    status = agentic_loop_client_mcp_server._status(
        {"job_id": "job-test", "confirm_agentic_loop": agentic_loop_client_mcp_server.CONFIRM_STATUS},
        tmp_path,
    )
    result = agentic_loop_client_mcp_server._result(
        {"job_id": "job-test", "confirm_agentic_loop": agentic_loop_client_mcp_server.CONFIRM_RESULT},
        tmp_path,
    )

    assert status["ok"] is True
    assert result["ok"] is True
    assert calls[0]["endpoint"] == "http://127.0.0.1:3579/vulkan/agent"
    assert calls[1]["endpoint"] == "http://127.0.0.1:3579/vulkan/agent"
    status_payload = calls[0]["payload"]
    result_payload = calls[1]["payload"]
    assert isinstance(status_payload, dict)
    assert isinstance(result_payload, dict)
    assert status_payload["job_action"] == "status"
    assert result_payload["job_action"] == "result"
    result_arguments = result_payload["arguments"]
    assert isinstance(result_arguments, dict)
    assert result_arguments["audience"] == "openwebui"


def test_ensure_broker_starts_dedicated_port_when_free(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        agentic_loop_client_mcp_server,
        "_get_health",
        lambda *_args, **_kwargs: {"ok": False, "error": "request_failed"},
    )
    monkeypatch.setattr(agentic_loop_client_mcp_server, "_port_listening", lambda **kwargs: False)

    def fake_start(root: Path, *, port: int, startup_timeout_seconds: int) -> dict[str, object]:
        calls["root"] = root
        calls["port"] = port
        calls["startup_timeout_seconds"] = startup_timeout_seconds
        return {"ok": True, "started": True, "pid": 123, "root_check": {"ok": True}}

    monkeypatch.setattr(agentic_loop_client_mcp_server, "_start_broker_process", fake_start)

    result = agentic_loop_client_mcp_server._ensure_broker(
        {
            "confirm_ensure_broker": agentic_loop_client_mcp_server.CONFIRM_ENSURE,
            "port": 3579,
            "startup_timeout_seconds": 9,
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert result["broker_started"] is True
    assert calls["root"] == tmp_path
    assert calls["port"] == 3579
    assert calls["startup_timeout_seconds"] == 9
