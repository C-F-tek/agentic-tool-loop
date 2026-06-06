from __future__ import annotations

import json
import re
from typing import Any


LOCAL_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)
SUMMARY_DUPLICATE_KEYS = {
    "answer_for_30b",
    "message_for_30b",
    "summary_for_30b",
}
OMISSION_MARKERS = {
    "local_path_omitted",
    "local_url_omitted",
    "job_workspace_path_omitted",
    "job_path_omitted",
    "tool_result_path_omitted",
    "sqlite_path_omitted",
}


def _decode_tool_context(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AssertionError("tool_context_for_30b is not JSON parseable") from exc
        if not isinstance(parsed, dict):
            raise AssertionError("tool_context_for_30b parsed to non-object JSON")
        return parsed
    raise AssertionError("tool_context_for_30b must be a JSON string or object")


def _walk(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    rows = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_walk(child, path + (str(key),)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk(child, path + (str(index),)))
    return rows


def _under_operator_diagnostics(path: tuple[str, ...]) -> bool:
    return "operator_diagnostics" in path


def assert_public_payload_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AssertionError("public payload must be a dict")

    guide = payload.get("evidence_guide_for_30b")
    if not isinstance(guide, str) or not guide.strip():
        raise AssertionError("missing non-empty evidence_guide_for_30b")

    index = payload.get("payload_index_for_30b")
    if not isinstance(index, dict):
        raise AssertionError("missing payload_index_for_30b object")
    if not (index.get("concrete_results") or index.get("partial_results")):
        raise AssertionError("payload_index_for_30b lacks concrete_results/partial_results")

    priority = payload.get("priority_evidence_for_30b")
    if not isinstance(priority, dict):
        raise AssertionError("missing priority_evidence_for_30b object")
    items = priority.get("items")
    if not isinstance(items, list):
        raise AssertionError("priority_evidence_for_30b.items must be a list")
    if items:
        first_content = items[0].get("content") if isinstance(items[0], dict) else None
        if first_content is not None and not isinstance(first_content, str):
            raise AssertionError("priority_evidence_for_30b.items[0].content must be text when present")

    materialization = payload.get("materialization_report")
    if not isinstance(materialization, dict):
        raise AssertionError("missing materialization_report object")
    if materialization.get("schema") != "public_evidence_materialization.v1":
        raise AssertionError("materialization_report schema mismatch")

    tool_context = _decode_tool_context(payload.get("tool_context_for_30b"))
    if any(key in tool_context for key in SUMMARY_DUPLICATE_KEYS | {"evidence_guide_for_30b", "content"}):
        raise AssertionError("tool_context_for_30b contains redundant summary/answer/content keys")
    artifacts = tool_context.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            raise AssertionError("tool_context_for_30b.artifacts must be a list when present")
        for artifact_row in artifacts:
            if not isinstance(artifact_row, dict):
                raise AssertionError("tool_context_for_30b.artifacts rows must be objects")
            if "artifact" not in artifact_row:
                raise AssertionError("tool_context_for_30b artifact row lacks artifact")
            artifact = artifact_row.get("artifact")
            if not isinstance(artifact, (dict, list)) or artifact in ({}, []):
                raise AssertionError("tool_context_for_30b artifact must be a non-empty inline serialized payload")

    duplicate_top_level = [key for key in SUMMARY_DUPLICATE_KEYS if key in payload]
    if duplicate_top_level:
        raise AssertionError(f"redundant top-level 30B summary fields present: {duplicate_top_level}")
    if isinstance(payload.get("content"), str) and payload["content"].strip() == guide.strip():
        raise AssertionError("top-level content duplicates evidence_guide_for_30b")

    for path, value in _walk(payload):
        if isinstance(value, str) and LOCAL_PATH_RE.search(value) and not _under_operator_diagnostics(path):
            dotted = ".".join(path)
            raise AssertionError(f"local Windows path leaked outside operator_diagnostics at {dotted}")
        if isinstance(value, str) and any(marker in value for marker in OMISSION_MARKERS) and not _under_operator_diagnostics(path):
            dotted = ".".join(path)
            raise AssertionError(f"local path omission marker leaked into public payload at {dotted}")
        if path and path[-1] in {"final_path", "artifact_path", "workspace"} and not _under_operator_diagnostics(path):
            dotted = ".".join(path)
            raise AssertionError(f"local path field leaked outside operator_diagnostics at {dotted}")

    return {
        "payload_ok": True,
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
    shared_changed = sorted(
        key
        for key in public_keys & serializer_keys
        if public_3571_payload.get(key) != serializer_3572_payload.get(key)
    )
    raise AssertionError(
        "3571 public payload differs from 3572 openwebui serializer payload: "
        + json.dumps(
            {
                "3571_only_keys": sorted(public_keys - serializer_keys),
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
