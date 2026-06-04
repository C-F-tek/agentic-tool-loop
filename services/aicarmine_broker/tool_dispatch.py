"""Deterministic internal tool dispatch compatibility facade."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .application.tool_dispatcher import DispatchRequest, build_default_dispatcher


def dispatch_tool(
    name: str,
    args: dict[str, Any],
    root: Path,
    allow_command: bool,
    user_consent: str,
) -> dict[str, Any]:
    dispatcher = build_default_dispatcher()
    return dispatcher.dispatch(
        DispatchRequest(
            name=name,
            args=args,
            root=root,
            allow_command=allow_command,
            user_consent=user_consent,
        )
    )
