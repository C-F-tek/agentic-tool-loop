"""Planner prompt construction and budget management."""
from typing import Any


class PromptBuilder:
    """Builds planner user payloads with budget tracking."""

    def __init__(self, config):
        self.config = config

    def build_user_payload(
        self,
        job_id: str,
        state: dict[str, Any],
        step: int,
        history: list[dict[str, Any]],
        tool_manifest: list[dict[str, Any]],
        evidence_contract: dict[str, Any],
        planner_memory: dict[str, Any],
        intrinsic_context: dict[str, Any],
        last_tool_result: dict[str, Any],
        native_tools_schema: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build the planner user payload with budget tracking.

        Delegates to application/prompt/pack_builder.build_planner_user_payload.
        """
        from ..application.prompt.pack_builder import (
            build_planner_user_payload as _impl,
        )
        return _impl(
            job_id=job_id,
            state=state,
            step=step,
            history=history,
            tool_manifest=tool_manifest,
            evidence_contract=evidence_contract,
            planner_memory=planner_memory,
            intrinsic_context=intrinsic_context,
            last_tool_result=last_tool_result,
            native_tools_schema=native_tools_schema,
        )

    def budget_report(self, user_payload: dict[str, Any]) -> dict[str, Any]:
        """Generate prompt budget report."""
        from ..application.prompt.budget import (
            prompt_budget_report as _budget_impl,
        )
        return _budget_impl(user_payload)