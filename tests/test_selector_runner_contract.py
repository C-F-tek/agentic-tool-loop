from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aicarmine_broker.application.job.selector_runner import SelectorRunner


def _runner_fixture(
    tmp_path: Path,
    *,
    selected_tool: str | None = "repo_read",
    selector_response: dict[str, Any] | None = None,
    fallback_tool: str | None = None,
    composite_review: bool = False,
):
    calls: dict[str, Any] = {
        "select": [],
        "fallback": [],
        "sanitize": [],
        "dispatch": [],
        "wrapper": [],
        "fail": [],
        "writes": [],
    }

    def select_internal_tool(**kwargs):
        calls["select"].append(kwargs)
        return selected_tool, {"path": "README.md"}, selector_response or {"raw": True}

    def selector_fallback_tool(public_tool_name, task, original_args, response):
        calls["fallback"].append((public_tool_name, task, original_args, response))
        return fallback_tool, {"path": "fallback.md"}

    def fail_selector(public_tool_name, task, original_args, root, response):
        calls["fail"].append((public_tool_name, task, original_args, root, response))
        return {"ok": False, "error": "selector_failed"}

    def sanitize_tool_args(internal_tool, raw_args, original_args, public_tool_name):
        calls["sanitize"].append(
            (internal_tool, dict(raw_args), dict(original_args), public_tool_name)
        )
        return dict(raw_args)

    def needs_composite_review(*args):
        return composite_review

    def dispatch_tool(internal_tool, internal_args, root, allow_command, user_consent):
        calls["dispatch"].append(
            (internal_tool, dict(internal_args), root, allow_command, user_consent)
        )
        return {"ok": True, "payload": "tool result"}

    def public_wrapper(**kwargs):
        calls["wrapper"].append(kwargs)
        return {"ok": True, "wrapped_tool": kwargs["internal_tool"]}

    def write_json(path: Path, payload: Any) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        calls["writes"].append((path, payload))
        return str(path)

    runner = SelectorRunner(
        select_internal_tool=select_internal_tool,
        selector_fallback_tool=selector_fallback_tool,
        fail_selector=fail_selector,
        sanitize_tool_args=sanitize_tool_args,
        needs_composite_review=needs_composite_review,
        dispatch_tool=dispatch_tool,
        public_wrapper=public_wrapper,
        write_json=write_json,
        now=lambda: 123,
    )
    return runner, calls


def test_selector_runner_dispatches_selected_tool(tmp_path: Path) -> None:
    runner, calls = _runner_fixture(tmp_path)

    result = runner.run(
        public_tool_name="vulkan_helper",
        task="read readme",
        original_args={"request": "read readme"},
        root=tmp_path,
        allow_command=True,
        user_consent="",
        timeout_seconds=30,
    )

    assert result == {"ok": True, "wrapped_tool": "repo_read"}
    assert calls["select"][0]["timeout_seconds"] == 30
    assert calls["dispatch"][0][0] == "repo_read"
    assert calls["dispatch"][0][1] == {"path": "README.md"}
    wrapper_payload = calls["wrapper"][0]
    assert wrapper_payload["dispatcher_result"]["called_by_vulkan"] == "repo_read"
    assert wrapper_payload["dispatcher_result"]["artifact"].endswith(
        "123-repo_read-dispatcher-v6.json"
    )
    assert (tmp_path / "broker-session.json").exists()


def test_selector_runner_uses_fallback_when_selector_emits_no_tool(tmp_path: Path) -> None:
    runner, calls = _runner_fixture(
        tmp_path,
        selected_tool=None,
        fallback_tool="repo_tree",
        selector_response={"native": False},
    )

    result = runner.run(
        public_tool_name="vulkan_helper",
        task="inspect",
        original_args={},
        root=tmp_path,
        allow_command=False,
        user_consent="no",
        timeout_seconds=30,
    )

    assert result == {"ok": True, "wrapped_tool": "repo_tree"}
    assert calls["dispatch"][0][0] == "repo_tree"
    assert calls["sanitize"][0][1] == {"path": "fallback.md"}
    assert calls["wrapper"][0]["selector_response"]["aicarmine_selector_fallback"][
        "forced_internal_tool"
    ] == "repo_tree"


def test_selector_runner_writes_selector_failure_envelope(tmp_path: Path) -> None:
    runner, calls = _runner_fixture(tmp_path, selected_tool=None, fallback_tool=None)

    result = runner.run(
        public_tool_name="vulkan_helper",
        task="inspect",
        original_args={},
        root=tmp_path,
        allow_command=False,
        user_consent="",
        timeout_seconds=30,
    )

    assert result == {"ok": False, "error": "selector_failed"}
    assert calls["dispatch"] == []
    assert calls["wrapper"] == []
    assert calls["fail"]
    assert json.loads((tmp_path / "broker-session.json").read_text(encoding="utf-8"))[
        "error"
    ] == "selector_failed"


def test_selector_runner_forces_composite_review_guard(tmp_path: Path) -> None:
    runner, calls = _runner_fixture(tmp_path, selected_tool="repo_search", composite_review=True)

    result = runner.run(
        public_tool_name="vulkan_helper",
        task="analyze repo",
        original_args={"request": "analyze repo"},
        root=tmp_path,
        allow_command=True,
        user_consent="",
        timeout_seconds=30,
    )

    assert result == {"ok": True, "wrapped_tool": "vulkan_helper"}
    assert calls["dispatch"][0][0] == "vulkan_helper"
    assert calls["dispatch"][0][1]["force_composite_review"] is True
    assert calls["dispatch"][0][1]["arguments"] == {"request": "analyze repo"}
    assert calls["wrapper"][0]["selector_response"]["aicarmine_selector_guard"][
        "forced_internal_tool"
    ] == "vulkan_helper"
