from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import logging
from typing import Any, Mapping, Sequence


logger = logging.getLogger(__name__)


class OllamaPlannerClient:
    """HTTP adapter for one planner turn."""

    def __init__(self, url: str, timeout_seconds: int = 120) -> None:
        self.url = url
        try:
            timeout = int(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"planner timeout_seconds must be an integer; got {timeout_seconds!r}") from exc
        self.timeout_seconds = max(1, min(timeout, 600))

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
        response = post_json(self.url, payload, timeout=self.timeout_seconds)
        if isinstance(response, dict) and response.get("ok") is False:
            diagnostics = response.get("planner_transport_diagnostics")
            diagnostics = diagnostics if isinstance(diagnostics, list) else []
            diagnostics.append(
                {
                    "schema": "ollama_planner_transport_diagnostic.v1",
                    "diagnostic_only": True,
                    "url": self.url,
                    "timeout_seconds": self.timeout_seconds,
                    "error_type": response.get("error_type"),
                    "backend_timeout": response.get("backend_timeout"),
                    "backend_unreachable": response.get("backend_unreachable"),
                }
            )
            response = {**response, "planner_transport_diagnostics": diagnostics}
            logger.debug(
                "Planner transport returned error. url=%s timeout_seconds=%s error_type=%s",
                self.url,
                self.timeout_seconds,
                response.get("error_type"),
            )
        return response
