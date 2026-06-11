from __future__ import annotations

import json
from typing import Any

from vulkan_bridge.application.public_payload_linter import lint_public_payload


def _decode_tool_context(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AssertionError("tool_context is not JSON parseable") from exc
        if not isinstance(parsed, dict):
            raise AssertionError("tool_context parsed to non-object JSON")
        return parsed
    raise AssertionError("tool_context must be a JSON string or object")


def _walk(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    rows = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_walk(child, path + (str(key),)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk(child, path + (str(index),)))
    return rows


def assert_public_payload_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AssertionError("public payload must be a dict")
    legacy_keys = [
        ".".join(path)
        for path, _ in _walk(payload)
        if path and ("for_30b" in path[-1] or path[-1] == "called_by_30b")
    ]
    if legacy_keys:
        raise AssertionError(f"public payload contains legacy 30B field names: {legacy_keys[:20]}")
    lint = lint_public_payload(payload, mode="block")
    if lint.get("ok") is not True:
        raise AssertionError(
            "runtime public_payload_linter rejected payload: "
            + json.dumps(lint.get("violations") or lint, ensure_ascii=False, default=str)
        )

    guide = payload.get("evidence_guide")
    if not isinstance(guide, str) or not guide.strip():
        raise AssertionError("missing non-empty evidence_guide")

    index = payload.get("payload_index")
    if not isinstance(index, dict):
        raise AssertionError("missing payload_index object")
    if not (index.get("concrete_results") or index.get("partial_results")):
        raise AssertionError("payload_index lacks concrete_results/partial_results")

    priority = payload.get("priority_evidence")
    if not isinstance(priority, dict):
        raise AssertionError("missing priority_evidence object")
    items = priority.get("items")
    if not isinstance(items, list):
        raise AssertionError("priority_evidence.items must be a list")
    if items:
        first_content = items[0].get("content") if isinstance(items[0], dict) else None
        if first_content is not None and not isinstance(first_content, str):
            raise AssertionError("priority_evidence.items[0].content must be text when present")

    materialization = payload.get("materialization_report")
    if not isinstance(materialization, dict):
        raise AssertionError("missing materialization_report object")
    if materialization.get("schema") != "public_evidence_materialization.v1":
        raise AssertionError("materialization_report schema mismatch")
    if materialization.get("ok") is not True:
        raise AssertionError(f"materialization_report is not ok: {materialization}")
    if materialization.get("owner") != "3572_broker":
        raise AssertionError(f"materialization_report owner is not 3572_broker: {materialization.get('owner')}")

    tool_context = _decode_tool_context(payload.get("tool_context"))
    artifacts = tool_context.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            raise AssertionError("tool_context.artifacts must be a list when present")
        for artifact_row in artifacts:
            if not isinstance(artifact_row, dict):
                raise AssertionError("tool_context.artifacts rows must be objects")
            if "artifact" not in artifact_row:
                raise AssertionError("tool_context artifact row lacks artifact")
            artifact = artifact_row.get("artifact")
            if not isinstance(artifact, (dict, list)) or artifact in ({}, []):
                raise AssertionError("tool_context artifact must be a non-empty inline serialized payload")

    return {
        "payload_ok": True,
        "runtime_public_payload_lint": lint,
        "priority_items": len(items),
        "tool_context_artifacts": len(artifacts or []),
        "materialization_owner": materialization.get("owner"),
    }


def assert_same_openwebui_payload(
    public_3571_payload: dict[str, Any],
    serializer_3572_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(public_3571_payload, dict) or not isinstance(serializer_3572_payload, dict):
        raise AssertionError("OpenWebUI payload equality requires two JSON objects")
    if public_3571_payload == serializer_3572_payload:
        return {
            "same_openwebui_payload": True,
            "top_level_keys": sorted(public_3571_payload),
        }

    public_keys = set(public_3571_payload)
    serializer_keys = set(serializer_3572_payload)
    public_only_keys = public_keys - serializer_keys
    bridge_wrapper_keys = {"called_by", "job_url", "tool_name", "tool_result_for"}
    shared_changed = sorted(
        key
        for key in public_keys & serializer_keys
        if public_3571_payload.get(key) != serializer_3572_payload.get(key)
    )
    if not shared_changed and not (serializer_keys - public_keys) and public_only_keys <= bridge_wrapper_keys:
        return {
            "same_openwebui_payload": True,
            "top_level_keys": sorted(public_3571_payload),
            "bridge_wrapper_3571_only_keys": sorted(public_only_keys),
        }
    raise AssertionError(
        "3571 public payload differs from 3572 openwebui serializer payload: "
        + json.dumps(
            {
                "3571_only_keys": sorted(public_only_keys),
                "3572_only_keys": sorted(serializer_keys - public_keys),
                "changed_shared_keys": shared_changed,
            },
            ensure_ascii=False,
            default=str,
        )
    )


def extract_job_id(payload: dict[str, Any]) -> str:
    for key in ("job_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("job-"):
            return value
    started = payload.get("started_job")
    if isinstance(started, dict):
        value = started.get("job_id")
        if isinstance(value, str) and value.startswith("job-"):
            return value
    for _, value in _walk(payload):
        if isinstance(value, str) and value.startswith("job-"):
            return value
        if isinstance(value, str) and "job-" in value and value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                nested = extract_job_id(parsed)
                if nested:
                    return nested
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        nested = extract_job_id(item)
                        if nested:
                            return nested
    return ""


def extract_tools_observed(payload: dict[str, Any]) -> set[str]:
    observed: set[str] = set()
    for path, value in _walk(payload):
        if not isinstance(value, str):
            continue
        key = path[-1] if path else ""
        if key in {"tool", "tool_name", "requested_tool_name", "tool_result_for", "function", "name"}:
            observed.add(value)
    return observed
