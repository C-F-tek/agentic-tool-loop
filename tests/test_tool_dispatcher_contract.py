from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_dispatch_registry_contains_all_valid_internal_tools() -> None:
    from aicarmine_broker.application import build_default_dispatcher
    from aicarmine_broker.tool_registry import VALID_INTERNAL_TOOLS_LIST

    registered = set(build_default_dispatcher().tool_names())

    assert registered == set(VALID_INTERNAL_TOOLS_LIST)


def test_dispatch_registry_has_no_extra_public_leakage() -> None:
    from aicarmine_broker.application import build_default_dispatcher
    from aicarmine_broker.tool_registry import HELPER_PUBLIC_ALIASES
    from vulkan_bridge.app import OPENWEBUI_VISIBLE_TOOL_ALIASES

    registered = set(build_default_dispatcher().tool_names())

    assert OPENWEBUI_VISIBLE_TOOL_ALIASES == ("vulkan_helper",)
    assert registered.isdisjoint(HELPER_PUBLIC_ALIASES)
    assert "vulkan_helper" in registered


def test_dispatch_unknown_tool_returns_unknown_internal_tool(tmp_path: Path) -> None:
    from aicarmine_broker.application import DispatchRequest, build_default_dispatcher

    result = build_default_dispatcher().dispatch(
        DispatchRequest(
            name="does_not_exist",
            args={},
            root=tmp_path,
            allow_command=False,
            user_consent="",
        )
    )

    assert result == {
        "ok": False,
        "tool": "does_not_exist",
        "error": "unknown internal tool",
    }


def test_dispatch_known_tool_same_payload_shape(monkeypatch, tmp_path: Path) -> None:
    import aicarmine_broker.application.tool_surface.dispatcher as dispatcher_module
    from aicarmine_broker.application import DispatchRequest, build_default_dispatcher

    def fake_repo_status(args, root):
        return {"ok": True, "tool": "repo_status", "args": args, "root": str(root)}

    monkeypatch.setattr(dispatcher_module, "repo_status", fake_repo_status)

    result = build_default_dispatcher().dispatch(
        DispatchRequest(
            name="repo_status",
            args={"short": True},
            root=tmp_path,
            allow_command=False,
            user_consent="",
        )
    )

    assert result == {
        "ok": True,
        "tool": "repo_status",
        "args": {"short": True},
        "root": str(tmp_path),
    }


def test_dispatch_write_guarded_tool_receives_consent(monkeypatch, tmp_path: Path) -> None:
    import aicarmine_broker.application.tool_surface.dispatcher as dispatcher_module
    from aicarmine_broker.application import DispatchRequest, build_default_dispatcher

    captured = {}

    def fake_hyperfine(args, root, *, allow_command, user_consent):
        captured.update({
            "args": args,
            "root": root,
            "allow_command": allow_command,
            "user_consent": user_consent,
        })
        return {"ok": True, "tool": "repo_hyperfine_benchmark"}

    monkeypatch.setattr(dispatcher_module, "repo_hyperfine_benchmark", fake_hyperfine)

    result = build_default_dispatcher().dispatch(
        DispatchRequest(
            name="repo_hyperfine_benchmark",
            args={"command": "pytest"},
            root=tmp_path,
            allow_command=True,
            user_consent="explicit",
        )
    )

    assert result["ok"] is True
    assert captured == {
        "args": {"command": "pytest"},
        "root": tmp_path,
        "allow_command": True,
        "user_consent": "explicit",
    }


def test_dispatch_readonly_tool_does_not_require_consent(monkeypatch, tmp_path: Path) -> None:
    import aicarmine_broker.application.tool_surface.dispatcher as dispatcher_module
    from aicarmine_broker.application import DispatchRequest, build_default_dispatcher

    def fake_repo_tree(args, root):
        return {"ok": True, "tool": "repo_tree", "path": args.get("path"), "root": str(root)}

    monkeypatch.setattr(dispatcher_module, "repo_tree", fake_repo_tree)

    result = build_default_dispatcher().dispatch(
        DispatchRequest(
            name="repo_tree",
            args={"path": "."},
            root=tmp_path,
            allow_command=False,
            user_consent="",
        )
    )

    assert result == {"ok": True, "tool": "repo_tree", "path": ".", "root": str(tmp_path)}


def test_dispatch_facade_matches_registry_unknown_shape(tmp_path: Path) -> None:
    from aicarmine_broker.tool_dispatch import dispatch_tool

    result = dispatch_tool(
        "does_not_exist",
        {},
        tmp_path,
        allow_command=False,
        user_consent="",
    )

    assert result["ok"] is False
    assert result["error"] == "unknown internal tool"
