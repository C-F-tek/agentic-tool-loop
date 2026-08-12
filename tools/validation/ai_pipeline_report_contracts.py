"""Reusable AI pipeline report contract validators.

The checks in this module validate report shape and field meanings only. They
do not execute pipeline steps, Blender, FFmpeg, NPU/GPU workloads or generated
artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PIPELINE_SCHEMA_VERSION = 6
KNOWN_LANES = {"CPU", "NPU", "GPU", "IO", "VALIDATION"}

BASE_PIPELINE_REPORT_FIELDS = {
    "schema_version",
    "generated_at",
    "repo_root",
    "output_dir",
    "dry_run",
    "passed",
    "preflight",
    "step_count",
    "summary",
    "schedule",
    "steps",
}

EXTENDED_PIPELINE_REPORT_FIELDS = {
    "lanes",
    "wave_entrypoint_review",
    "smart_context",
    "agent_state_packet",
    "guardrail_remediation_loop",
    "post_run_expected_outputs",
}


def is_non_empty_string(value: Any) -> bool:
    """Return True when value is a non-empty string after trimming whitespace."""
    return isinstance(value, str) and bool(value.strip())


def is_int(value: Any) -> bool:
    """Return True for integers while excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_non_negative_int(value: Any) -> bool:
    """Return True for non-negative integers while excluding booleans."""
    return is_int(value) and value >= 0


def is_number(value: Any) -> bool:
    """Return True for numeric values while excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_non_negative_number(value: Any) -> bool:
    """Return True for non-negative numeric values while excluding booleans."""
    return is_number(value) and value >= 0


def add_error(errors: list[str], path: str, message: str) -> None:
    """Append a path-qualified validation error."""
    errors.append(f"{path}: {message}")


def add_warning(warnings: list[str], path: str, message: str) -> None:
    """Append a path-qualified validation warning."""
    warnings.append(f"{path}: {message}")


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load a JSON object with tolerant UTF-8 BOM handling."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, f"not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, f"read error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def validate_agent_state_packet(packet: Any, path: str, errors: list[str], warnings: list[str]) -> None:
    """Validate the optional agent_state_packet metadata sub-contract."""
    if not isinstance(packet, dict):
        add_error(errors, path, "must be an object when present")
        return

    enabled = packet.get("enabled")
    packet_path = packet.get("path")
    exists = packet.get("exists")
    source = packet.get("source")

    if not isinstance(enabled, bool):
        add_error(errors, f"{path}.enabled", "must be bool")
    if "exists" not in packet or not isinstance(exists, bool):
        add_error(errors, f"{path}.exists", "must be bool")
    if source not in {"disabled", "cli"}:
        add_error(errors, f"{path}.source", 'must be "disabled" or "cli"')

    if enabled is True:
        if source != "cli":
            add_error(errors, f"{path}.source", 'must be "cli" when enabled=true')
        if not is_non_empty_string(packet_path):
            add_error(errors, f"{path}.path", "must be a non-empty string when enabled=true")
        if "repo_relative_path" in packet and not is_non_empty_string(packet.get("repo_relative_path")):
            add_error(errors, f"{path}.repo_relative_path", "must be a non-empty string when present")
    elif enabled is False:
        if exists is not False:
            add_error(errors, f"{path}.exists", "must be false when enabled=false")
        if source != "disabled":
            add_error(errors, f"{path}.source", 'must be "disabled" when enabled=false')
        if packet_path is not None and not is_non_empty_string(packet_path):
            add_error(errors, f"{path}.path", "must be null/absent or a non-empty string")

    allowed_fields = {"enabled", "path", "exists", "source", "repo_relative_path", "size_bytes", "modified_time"}
    extra_fields = sorted(set(packet) - allowed_fields)
    if extra_fields:
        add_warning(warnings, path, f"accepted extra fields: {', '.join(extra_fields)}")


def validate_preflight(preflight: Any, path: str, errors: list[str]) -> bool | None:
    """Validate preflight report metadata and return its pass state when known."""
    if not isinstance(preflight, dict):
        add_error(errors, path, "must be an object")
        return None

    passed = preflight.get("passed")
    if not isinstance(passed, bool):
        add_error(errors, f"{path}.passed", "must be bool")
        passed = None
    for list_field in ("errors", "warnings"):
        value = preflight.get(list_field)
        if value is not None and not isinstance(value, list):
            add_error(errors, f"{path}.{list_field}", "must be list when present")
    return passed


def validate_summary(summary: Any, path: str, errors: list[str], step_count: int | None) -> None:
    """Validate schema-v6 summary semantics."""
    if not isinstance(summary, dict):
        add_error(errors, path, "must be an object")
        return

    for field in ("ok_count", "failed_count", "planned_only_count"):
        if not is_non_negative_int(summary.get(field)):
            add_error(errors, f"{path}.{field}", "must be int >= 0")
    if not is_non_negative_number(summary.get("total_duration_sec")):
        add_error(errors, f"{path}.total_duration_sec", "must be int or float >= 0")
    if not isinstance(summary.get("failed_steps"), list):
        add_error(errors, f"{path}.failed_steps", "must be a list")

    lane_counts = summary.get("lane_counts")
    if not isinstance(lane_counts, dict):
        add_error(errors, f"{path}.lane_counts", "must be an object")
    else:
        for lane, count in lane_counts.items():
            if not is_non_empty_string(lane):
                add_error(errors, f"{path}.lane_counts", "lane key must be a non-empty string")
            if not is_non_negative_int(count):
                add_error(errors, f"{path}.lane_counts.{lane}", "must be int >= 0")
        if step_count is not None and sum(lane_counts.values()) != step_count:
            add_error(errors, f"{path}.lane_counts", f"must sum to step_count {step_count}")

    ok_count = summary.get("ok_count")
    failed_count = summary.get("failed_count")
    planned_only_count = summary.get("planned_only_count")
    if step_count is not None and is_non_negative_int(ok_count) and is_non_negative_int(failed_count):
        if ok_count + failed_count != step_count:
            add_error(errors, path, f"ok_count + failed_count must equal step_count {step_count}")
    if step_count is not None and is_non_negative_int(planned_only_count) and planned_only_count > step_count:
        add_error(errors, f"{path}.planned_only_count", "must be <= step_count")


def validate_schedule(schedule: Any, path: str, errors: list[str], step_names: list[str]) -> None:
    """Validate schema-v6 schedule semantics."""
    if not isinstance(schedule, dict):
        add_error(errors, path, "must be an object")
        return

    for field in ("serial_count", "parallel_count", "total_count"):
        if not is_non_negative_int(schedule.get(field)):
            add_error(errors, f"{path}.{field}", "must be int >= 0")
    for field in ("serial", "parallel"):
        value = schedule.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            add_error(errors, f"{path}.{field}", "must be a list of strings")
    if "parallel_lanes" in schedule and not (
        isinstance(schedule.get("parallel_lanes"), list) and all(isinstance(item, str) for item in schedule["parallel_lanes"])
    ):
        add_error(errors, f"{path}.parallel_lanes", "must be a list of strings when present")

    serial = schedule.get("serial") if isinstance(schedule.get("serial"), list) else []
    parallel = schedule.get("parallel") if isinstance(schedule.get("parallel"), list) else []
    serial_count = schedule.get("serial_count")
    parallel_count = schedule.get("parallel_count")
    total_count = schedule.get("total_count")
    if is_non_negative_int(serial_count) and len(serial) != serial_count:
        add_error(errors, f"{path}.serial_count", "must equal len(serial)")
    if is_non_negative_int(parallel_count) and len(parallel) != parallel_count:
        add_error(errors, f"{path}.parallel_count", "must equal len(parallel)")
    if is_non_negative_int(total_count):
        if is_non_negative_int(serial_count) and is_non_negative_int(parallel_count) and total_count != serial_count + parallel_count:
            add_error(errors, f"{path}.total_count", "must equal serial_count + parallel_count")
        if total_count != len(step_names):
            add_error(errors, f"{path}.total_count", "must equal step_count")
    scheduled_names = [*serial, *parallel]
    if sorted(scheduled_names) != sorted(step_names):
        add_error(errors, path, "serial + parallel step names must match report steps")


def validate_lanes(lanes: Any, path: str, errors: list[str], warnings: list[str], step_names: list[str]) -> None:
    """Validate lane grouping semantics."""
    if not isinstance(lanes, dict):
        add_error(errors, path, "must be an object")
        return

    for required_lane in ("CPU", "NPU", "GPU"):
        if required_lane not in lanes:
            add_error(errors, path, f"missing required lane key: {required_lane}")
    grouped_names: list[str] = []
    for lane, names in lanes.items():
        if not is_non_empty_string(lane):
            add_error(errors, path, "lane key must be a non-empty string")
        elif lane not in KNOWN_LANES:
            add_warning(warnings, f"{path}.{lane}", "accepted unknown lane")
        if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
            add_error(errors, f"{path}.{lane}", "must be a list of strings")
            continue
        grouped_names.extend(names)
    if sorted(grouped_names) != sorted(step_names):
        add_error(errors, path, "lane step names must match report steps")


def validate_step(step: Any, index: int, errors: list[str], warnings: list[str], require_dry_run: bool) -> str | None:
    """Validate one schema-v6 step payload."""
    path = f"steps[{index}]"
    if not isinstance(step, dict):
        add_error(errors, path, "must be an object")
        return None

    name = step.get("name")
    if not is_non_empty_string(name):
        add_error(errors, f"{path}.name", "must be a non-empty string")

    lane = step.get("lane")
    if not is_non_empty_string(lane):
        add_error(errors, f"{path}.lane", "must be a non-empty string")
    elif lane not in KNOWN_LANES:
        add_warning(warnings, f"{path}.lane", f"accepted unknown lane {lane!r}")

    if "purpose" in step and not isinstance(step.get("purpose"), str):
        add_error(errors, f"{path}.purpose", "must be string when present")
    command = step.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        add_error(errors, f"{path}.command", "must be a non-empty list of strings")

    expected_outputs = step.get("expected_outputs")
    if expected_outputs is not None and not (
        isinstance(expected_outputs, list) and all(isinstance(item, str) for item in expected_outputs)
    ):
        add_error(errors, f"{path}.expected_outputs", "must be a list of strings when present")

    if not isinstance(step.get("dry_run"), bool):
        add_error(errors, f"{path}.dry_run", "must be bool")
    elif require_dry_run and step.get("dry_run") is not True:
        add_error(errors, f"{path}.dry_run", "must be true for dry-run report validation")

    if not isinstance(step.get("planned_only"), bool):
        add_error(errors, f"{path}.planned_only", "must be bool")
    elif require_dry_run and step.get("planned_only") is not True:
        add_error(errors, f"{path}.planned_only", "must be true for dry-run report validation")

    if not is_int(step.get("returncode")):
        add_error(errors, f"{path}.returncode", "must be int")
    if not is_non_negative_number(step.get("duration_sec")):
        add_error(errors, f"{path}.duration_sec", "must be int or float >= 0")
    if "pass_index" in step and not is_non_negative_int(step.get("pass_index")):
        add_error(errors, f"{path}.pass_index", "must be int >= 0")
    if "allow_failure" in step and not isinstance(step.get("allow_failure"), bool):
        add_error(errors, f"{path}.allow_failure", "must be bool when present")
    if "metadata" in step and not isinstance(step.get("metadata"), dict):
        add_error(errors, f"{path}.metadata", "must be object when present")
    if "ok" in step and not isinstance(step.get("ok"), bool):
        add_error(errors, f"{path}.ok", "must be bool when present")
    if "error" in step and step.get("error") is not None and not isinstance(step.get("error"), str):
        add_error(errors, f"{path}.error", "must be string or null when present")

    for stream_field in ("stdout", "stderr"):
        if stream_field in step and not isinstance(step.get(stream_field), str):
            add_error(errors, f"{path}.{stream_field}", "must be string")

    return str(name) if is_non_empty_string(name) else None


def validate_enabled_path_ref(value: Any, path: str, errors: list[str], field_name: str) -> None:
    """Validate a small enabled/path-like subreport."""
    if not isinstance(value, dict):
        add_error(errors, path, "must be an object")
        return
    enabled = value.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, f"{path}.enabled", "must be bool")
    target = value.get(field_name)
    if enabled is True and not is_non_empty_string(target):
        add_error(errors, f"{path}.{field_name}", "must be a non-empty string when enabled=true")
    if enabled is False and target is not None and not isinstance(target, str):
        add_error(errors, f"{path}.{field_name}", "must be string or null when enabled=false")


def validate_guardrail_loop(value: Any, path: str, errors: list[str]) -> None:
    """Validate guardrail remediation loop metadata."""
    if not isinstance(value, dict):
        add_error(errors, path, "must be an object")
        return
    if not isinstance(value.get("enabled"), bool):
        add_error(errors, f"{path}.enabled", "must be bool")
    if "max_passes" in value and not is_non_negative_int(value.get("max_passes")):
        add_error(errors, f"{path}.max_passes", "must be int >= 0 when present")
    passes = value.get("passes")
    if not isinstance(passes, list):
        add_error(errors, f"{path}.passes", "must be a list")
        return
    for index, item in enumerate(passes):
        item_path = f"{path}.passes[{index}]"
        if not isinstance(item, dict):
            add_error(errors, item_path, "must be an object")
            continue
        if "pass_index" in item and not is_non_negative_int(item.get("pass_index")):
            add_error(errors, f"{item_path}.pass_index", "must be int >= 0")
        if "status" in item and not is_non_empty_string(item.get("status")):
            add_error(errors, f"{item_path}.status", "must be a non-empty string when present")
        if "plan" in item and not isinstance(item.get("plan"), dict):
            add_error(errors, f"{item_path}.plan", "must be an object when present")
        if "steps" in item and not isinstance(item.get("steps"), list):
            add_error(errors, f"{item_path}.steps", "must be a list when present")


def validate_expected_outputs(value: Any, path: str, errors: list[str]) -> None:
    """Validate post-run expected output metadata."""
    if not isinstance(value, list):
        add_error(errors, path, "must be a list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            add_error(errors, item_path, "must be an object")
            continue
        if not is_non_empty_string(item.get("path")):
            add_error(errors, f"{item_path}.path", "must be a non-empty string")
        if not isinstance(item.get("exists"), bool):
            add_error(errors, f"{item_path}.exists", "must be bool")
        if "size_bytes" in item and not is_non_negative_int(item.get("size_bytes")):
            add_error(errors, f"{item_path}.size_bytes", "must be int >= 0 when present")
        if "modified_time" in item and not is_non_empty_string(item.get("modified_time")):
            add_error(errors, f"{item_path}.modified_time", "must be a non-empty string when present")


def validate_ai_pipeline_report_payload(
    payload: dict[str, Any],
    *,
    require_dry_run: bool = False,
    path: str = "report",
) -> dict[str, Any]:
    """Validate one AI pipeline schema-v6 report payload."""
    errors: list[str] = []
    warnings: list[str] = []

    missing_base = sorted(BASE_PIPELINE_REPORT_FIELDS - set(payload))
    for field in missing_base:
        add_error(errors, f"{path}.{field}", "is missing")

    schema_version = payload.get("schema_version")
    if schema_version != PIPELINE_SCHEMA_VERSION:
        add_error(errors, f"{path}.schema_version", f"must be {PIPELINE_SCHEMA_VERSION}")
    if not is_non_empty_string(payload.get("generated_at")):
        add_error(errors, f"{path}.generated_at", "must be a non-empty string")
    if not is_non_empty_string(payload.get("repo_root")):
        add_error(errors, f"{path}.repo_root", "must be a non-empty string")
    if not is_non_empty_string(payload.get("output_dir")):
        add_error(errors, f"{path}.output_dir", "must be a non-empty string")
    if not isinstance(payload.get("dry_run"), bool):
        add_error(errors, f"{path}.dry_run", "must be bool")
    elif require_dry_run and payload.get("dry_run") is not True:
        add_error(errors, f"{path}.dry_run", "must be true")
    if not isinstance(payload.get("passed"), bool):
        add_error(errors, f"{path}.passed", "must be bool")

    preflight_passed = validate_preflight(payload.get("preflight"), f"{path}.preflight", errors) if "preflight" in payload else None
    is_preflight_failed_report = preflight_passed is False and payload.get("passed") is False and payload.get("step_count") == 0
    missing_extended = sorted(EXTENDED_PIPELINE_REPORT_FIELDS - set(payload))
    for field in missing_extended:
        if is_preflight_failed_report:
            add_warning(warnings, f"{path}.{field}", "missing in preflight-failed report")
        else:
            add_error(errors, f"{path}.{field}", "is missing")

    step_count = payload.get("step_count")
    if not is_non_negative_int(step_count):
        add_error(errors, f"{path}.step_count", "must be int >= 0")
        step_count_int: int | None = None
    else:
        step_count_int = step_count

    steps = payload.get("steps")
    step_names: list[str] = []
    if not isinstance(steps, list):
        add_error(errors, f"{path}.steps", "must be a list")
    else:
        if step_count_int is not None and len(steps) != step_count_int:
            add_error(errors, f"{path}.step_count", "must equal len(steps)")
        for index, step in enumerate(steps):
            name = validate_step(step, index, errors, warnings, require_dry_run)
            if name is not None:
                step_names.append(name)
        duplicates = sorted({name for name in step_names if step_names.count(name) > 1})
        if duplicates:
            add_error(errors, f"{path}.steps", f"duplicate step names: {', '.join(duplicates)}")

    if "summary" in payload:
        validate_summary(payload.get("summary"), f"{path}.summary", errors, step_count_int)
    if "schedule" in payload:
        if not (is_preflight_failed_report and payload.get("schedule") == {}):
            validate_schedule(payload.get("schedule"), f"{path}.schedule", errors, step_names)
    if "lanes" in payload:
        validate_lanes(payload.get("lanes"), f"{path}.lanes", errors, warnings, step_names)
    if "wave_entrypoint_review" in payload:
        validate_enabled_path_ref(payload.get("wave_entrypoint_review"), f"{path}.wave_entrypoint_review", errors, "report")
    if "smart_context" in payload:
        smart_context = payload.get("smart_context")
        validate_enabled_path_ref(smart_context, f"{path}.smart_context", errors, "packet")
        smart_task = smart_context.get("task") if isinstance(smart_context, dict) else None
        smart_enabled = smart_context.get("enabled") if isinstance(smart_context, dict) else None
        if smart_enabled is True and not is_non_empty_string(smart_task):
            add_error(errors, f"{path}.smart_context.task", "must be a non-empty string when enabled=true")
    if "agent_state_packet" in payload:
        validate_agent_state_packet(payload.get("agent_state_packet"), f"{path}.agent_state_packet", errors, warnings)
    if "guardrail_remediation_loop" in payload:
        validate_guardrail_loop(payload.get("guardrail_remediation_loop"), f"{path}.guardrail_remediation_loop", errors)
    if "post_run_expected_outputs" in payload:
        validate_expected_outputs(payload.get("post_run_expected_outputs"), f"{path}.post_run_expected_outputs", errors)

    if payload.get("passed") is True and isinstance(steps, list):
        failed_steps = [
            item.get("name") or f"steps[{index}]"
            for index, item in enumerate(steps)
            if isinstance(item, dict) and item.get("returncode") != 0 and item.get("allow_failure") is not True
        ]
        if failed_steps:
            add_error(errors, f"{path}.passed", f"true but failed steps exist: {', '.join(str(item) for item in failed_steps)}")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "schema_version": schema_version,
            "dry_run": payload.get("dry_run"),
            "report_passed": payload.get("passed"),
            "step_count": step_count if is_non_negative_int(step_count) else None,
            "validated_step_count": len(step_names),
            "preflight_passed": preflight_passed,
            "missing_base_fields": missing_base,
            "missing_extended_fields": missing_extended,
        },
    }


def validate_ai_pipeline_report_file(path: Path, *, require_dry_run: bool = False) -> dict[str, Any]:
    """Load and validate one AI pipeline schema-v6 report file."""
    payload, load_error = load_json_object(path)
    if load_error:
        return {
            "passed": False,
            "errors": [load_error],
            "warnings": [],
            "checks": {
                "schema_version": None,
                "dry_run": None,
                "report_passed": None,
                "step_count": None,
                "validated_step_count": 0,
                "preflight_passed": None,
                "missing_base_fields": [],
                "missing_extended_fields": [],
            },
        }
    assert payload is not None
    return validate_ai_pipeline_report_payload(payload, require_dry_run=require_dry_run)
