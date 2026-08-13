"""Selector and dispatch path for non-job public broker calls."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SelectInternalTool = Callable[..., tuple[str | None, dict[str, Any], dict[str, Any] | None]]
SelectorFallbackTool = Callable[..., tuple[str | None, dict[str, Any]]]
FailSelector = Callable[..., dict[str, Any]]
SanitizeToolArgs = Callable[..., dict[str, Any]]
NeedsCompositeReview = Callable[..., bool]
DispatchTool = Callable[..., dict[str, Any]]
PublicWrapper = Callable[..., dict[str, Any]]
WriteJson = Callable[[Path, Any], str]
NowSeconds = Callable[[], int]


@dataclass(frozen=True)
class SelectorRunner:
    """Run the selector/dispatch/public-wrapper path with injected adapters.

    Orchestrates the execution of the selector pipeline: selecting an internal
    tool from the planner, sanitizing arguments, dispatching execution, and
    wrapping the result as a public broker payload.
    """

    select_internal_tool: SelectInternalTool
    selector_fallback_tool: SelectorFallbackTool
    fail_selector: FailSelector
    sanitize_tool_args: SanitizeToolArgs
    needs_composite_review: NeedsCompositeReview
    dispatch_tool: DispatchTool
    public_wrapper: PublicWrapper
    write_json: WriteJson
    now: NowSeconds

    def run(
        self,
        *,
        public_tool_name: str,
        task: str,
        original_args: dict[str, Any],
        root: Path,
        allow_command: bool,
        user_consent: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        internal_tool, raw_internal_args, selector_response = self.select_internal_tool(
            public_tool_name=public_tool_name,
            task=task,
            original_args=original_args,
            timeout_seconds=timeout_seconds,
        )
        if not internal_tool:
            fallback_tool, fallback_args = self.selector_fallback_tool(
                public_tool_name,
                task,
                original_args,
                selector_response if isinstance(selector_response, dict) else {},
            )
            if fallback_tool:
                internal_tool = fallback_tool
                raw_internal_args = fallback_args
                selector_response = (
                    dict(selector_response or {})
                    if isinstance(selector_response, dict)
                    else {}
                )
                selector_response["aicarmine_selector_fallback"] = {
                    "forced_internal_tool": fallback_tool,
                    "reason": (
                        "11435/Vulkan was called but did not emit a usable native tool_call."
                    ),
                }
            else:
                envelope = self.fail_selector(
                    public_tool_name,
                    task,
                    original_args,
                    root,
                    selector_response if isinstance(selector_response, dict) else {},
                )
                self.write_json(root / "broker-session.json", envelope)
                return envelope
        internal_args = self.sanitize_tool_args(
            internal_tool,
            raw_internal_args,
            original_args,
            public_tool_name,
        )
        if self.needs_composite_review(
            public_tool_name,
            task,
            original_args,
            internal_tool,
            internal_args,
        ):
            selector_response = dict(selector_response or {})
            selector_response["aicarmine_selector_guard"] = {
                "reason": "generic_repo_analysis_requires_composite_evidence",
                "selected_tool_from_vulkan": internal_tool,
                "selected_args_from_vulkan": internal_args,
                "forced_internal_tool": "vulkan_helper",
            }
            internal_tool = "vulkan_helper"
            internal_args = {
                "public_tool_name": public_tool_name,
                "public_tool_x": public_tool_name,
                "task": task,
                "reason": (
                    "generic repo analysis must gather composite repo evidence, "
                    "not a single broad search"
                ),
                "arguments": original_args,
                "original_30b_arguments": original_args,
                "force_composite_review": True,
            }
        dispatcher_result = self.dispatch_tool(
            internal_tool,
            internal_args,
            root,
            allow_command,
            user_consent,
        )
        dispatcher_result = dict(dispatcher_result or {})
        dispatcher_result.setdefault("called_by_vulkan", internal_tool)
        dispatcher_artifact = (
            root / "tool-results" / f"{self.now()}-{internal_tool}-dispatcher-v6.json"
        )
        self.write_json(dispatcher_artifact, dispatcher_result)
        dispatcher_result.setdefault("artifact", str(dispatcher_artifact))
        envelope = self.public_wrapper(
            public_tool_name=public_tool_name,
            original_args=original_args,
            internal_tool=internal_tool,
            internal_args=internal_args,
            dispatcher_result=dispatcher_result,
            selector_response=selector_response if isinstance(selector_response, dict) else {},
            root=root,
        )
        self.write_json(root / "broker-session.json", envelope)
        return envelope
