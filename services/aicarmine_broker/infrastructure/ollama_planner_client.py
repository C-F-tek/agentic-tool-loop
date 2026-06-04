from __future__ import annotations

from typing import Any, Mapping, Sequence


class OllamaPlannerClient:
    """HTTP adapter for one planner turn."""

    def __init__(self, url: str, timeout_seconds: int = 120) -> None:
        self.url = url
        self.timeout_seconds = int(timeout_seconds)

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        options: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        from aicarmine_broker.planner_core.json_io import post_json

        payload = {
            "messages": list(messages),
            "tools": list(tools),
            "options": dict(options),
        }
        return post_json(self.url, payload, timeout=self.timeout_seconds)
