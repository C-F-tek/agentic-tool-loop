from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_dispatch_registry_contains_all_valid_internal_tools() -> None:
    from aicarmine_broker.application import build_default_dispatcher
    from aicarmine_broker.tool_registry import VALID_INTERNAL_TOOLS_LIST

    registered = set(build_default_dispatcher().tool_names())

    assert set(VALID_INTERNAL_TOOLS_LIST).issubset(registered)


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
