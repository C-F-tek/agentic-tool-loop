from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def vulkan_helper_completed_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "ok": {"type": "boolean"},
            "service": {"type": "string"},
            "mode": {"type": "string"},
            "required_top_level_keys": {
                "type": "array",
                "description": "Primary top-level fields expected by the public wrapper response.",
                "items": {"type": "string"},
            },
            "result": {
                "description": "Optional existing flow result. When present, it is preserved and not rewritten by the wrapper.",
            },
            "evidence_guide_for_30b": {
                "type": "string",
                "description": (
                    "The only top-level narrative guide for completed terminal jobs. "
                    "It is not a replacement for concrete payloads; it tells the model "
                    "how to read payload_index_for_30b, priority_evidence_for_30b and "
                    "tool_context_for_30b for detailed answers."
                ),
            },
            "payload_index_for_30b": {
                "type": "object",
                "description": (
                    "Expected top-level result field. Read this first. It separates concrete "
                    "results from description/review metadata and points to exact fields containing diffs, "
                    "structured operations or file content."
                ),
                "additionalProperties": True,
                "properties": {
                    "index_kind": {"type": "string", "example": "openwebui_payload_index.v1"},
                    "job_completed": {"type": "boolean"},
                    "internal_job_status": {
                        "type": "object",
                        "description": "Internal 3572 job status. This is diagnostic state, not the public tool-call status.",
                        "additionalProperties": True,
                    },
                    "same_request_rule": {
                        "type": "string",
                        "description": "For completed jobs, answer now from the indexed fields; do not call vulkan_helper again for the same request.",
                    },
                    "concrete_results": {
                        "type": "array",
                        "description": "Concrete useful payload locations: diffs, structured edits and full file contents.",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "kind": {"type": "string"},
                                "payload_type": {
                                    "type": "string",
                                    "description": "unified_diff, structured_operations, file_content or related concrete payload type.",
                                },
                                "target_file": {"type": "string"},
                                "path": {"type": "string"},
                                "payload_is_complete": {"type": "boolean"},
                                "primary_location": {
                                    "type": "string",
                                    "description": "Exact top-level field path, for example priority_evidence_for_30b.items[0].unified_diff.",
                                },
                                "full_context_location": {
                                    "type": "string",
                                    "description": "Mirror location inside tool_context_for_30b.artifacts[*].artifact.",
                                },
                                "role": {"type": "string"},
                            },
                        },
                    },
                    "descriptive_only": {
                        "type": "array",
                        "description": "Fields that are prose/summary/description only, not concrete payloads.",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "suggestions_or_review_metadata_only": {
                        "type": "array",
                        "description": "Validation suggestions, manual review flags and limits; not reasons to repeat a completed call.",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "search_order": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "priority_evidence_for_30b": {
                "type": "object",
                "description": "High-priority inline concrete payloads. Code proposals expose unified_diff or structured_operations here.",
                "additionalProperties": True,
            },
            "tool_context_for_30b": {
                "type": "string",
                "description": (
                    "Pretty-printed JSON string whose public useful payload is "
                    "tool_context_for_30b.artifacts[*].artifact. Artifact means real "
                    "tool result, not a local path. This is not the primary reading "
                    "surface and is not a full job dump."
                ),
            },
            "openwebui_usage": {
                "type": "object",
                "description": "Runtime instructions naming the primary payload fields and concrete evidence locations.",
                "additionalProperties": True,
            },
        },
    }


def annotate_vulkan_helper_openapi_response(schema: dict[str, Any]) -> None:
    operation = (
        schema.get("paths", {})
        .get("/vulkan_helper", {})
        .get("post")
    )
    if not isinstance(operation, dict):
        return
    operation["description"] = (
        str(operation.get("description") or "").rstrip()
        + "\n\nCompleted response schema: read `evidence_guide_for_30b` as the guide, then `payload_index_for_30b`. "
        "`evidence_guide_for_30b` is the single top-level narrative guide; "
        "`payload_index_for_30b.concrete_results[*].primary_location` points to exact useful payload fields "
        "such as `priority_evidence_for_30b.items[*].unified_diff`; "
        "for file content, prefer `priority_evidence_for_30b.items[0].content`; "
        "only after that inspect `tool_context_for_30b.artifacts[*].artifact`; "
        "`descriptive_only` and `suggestions_or_review_metadata_only` are not the concrete result. "
        "`answer_for_30b`, `message_for_30b`, `summary_for_30b`, `next_action_for_30b` "
        "and `full_result_hint` are not primary top-level result fields."
    )
    operation.setdefault("responses", {})
    operation["responses"]["200"] = {
        "description": (
            "Terminal vulkan_helper response. Completed responses include payload_index_for_30b "
            "near the top so the model can locate concrete results without repeating the same call."
        ),
        "content": {
            "application/json": {
                "schema": vulkan_helper_completed_response_schema(),
            },
        },
    }


def build_native_helper_openapi(
    app: FastAPI,
    *,
    visible_tool_aliases: tuple[str, ...],
    registry_loader: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    registry_error = ""
    try:
        registry = registry_loader() if registry_loader else {}
    except Exception as exc:
        registry = {}
        registry_error = f"{type(exc).__name__}: {str(exc)[:500]}"
    allowed = {f"/{name}" for name in visible_tool_aliases}
    visible_routes = [
        route for route in app.routes
        if getattr(route, "path", None) in allowed
    ]
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=visible_routes,
    )
    schema["paths"] = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path in allowed
    }
    schema["x-aicarmine-tool-surface"] = "single_openwebui_vulkan_helper"
    schema["x-aicarmine-registry-hash"] = registry.get("registry_hash")
    if registry_error:
        schema["x-aicarmine-registry-load-error"] = registry_error
    schema["x-aicarmine-public-surface"] = list(visible_tool_aliases)
    schema["x-aicarmine-contract"] = (
        "OpenAPI exposes only vulkan_helper to OpenWebUI. Completed responses include "
        "payload_index_for_30b as an expected result field plus inline successful tool evidence."
    )
    schema["x-aicarmine-register_this_in_openwebui"] = "http://127.0.0.1:3571/openapi.json"
    annotate_vulkan_helper_openapi_response(schema)
    return schema
