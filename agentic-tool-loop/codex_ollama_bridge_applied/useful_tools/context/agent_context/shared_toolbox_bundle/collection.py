from __future__ import annotations

from .common import *  # noqa: F403
from ia_carmine._shared.provider_work_verification import provider_work_status


def _provider_lane(data: dict[str, Any]) -> str:
    lane = str(data.get("lane") or data.get("provider_id") or "").strip()
    if lane:
        return lane
    kind = str(data.get("kind") or "").strip()
    if kind == "gpu0_peer_response":
        return "gpu0_peer"
    if kind in {"npu_gpu_deep_review_audit", "npu_micro_task_auditor"}:
        return "npu_micro_task_auditor"
    if kind in {"local_provider_probe", "gpu1_primary_advisory"}:
        return "gpu1_planner"
    return ""


def _provider_execution_claim_seen(data: dict[str, Any]) -> bool:
    return bool(
        data.get("provider_execution_performed")
        or data.get("provider_execution_attempted")
        or data.get("provider_io_observed")
    )


def _provider_work_verified(data: dict[str, Any]) -> bool:
    if data.get("provider_work_verified") is True:
        return True
    lane = _provider_lane(data)
    if not lane:
        return False
    return bool(provider_work_status(lane=lane, report=data).get("provider_work_verified"))

def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON object while reusing shared evidence-bundle IO helpers."""
    data = read_json(path)
    if data is not None:
        return data, None
    if not path.exists():
        return None, "missing"
    text, read_error = read_text(path)
    if read_error:
        return None, read_error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    if not isinstance(parsed, dict):
        return None, f"expected JSON object, got {type(parsed).__name__}"
    return parsed, None

def existing_paths(
    repo_root: Path, raw_paths: list[str], *, label: str, include_missing_optional: bool
) -> tuple[list[str], list[dict[str, Any]]]:
    present: list[str] = []
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_paths:
        path = resolve_repo_path(repo_root, raw)
        rel = repo_relative(path, repo_root)
        if rel in seen:
            continue
        seen.add(rel)
        if path.exists():
            present.append(rel)
        else:
            missing.append({"path": rel, "reason": f"optional {label} missing"})
            if include_missing_optional:
                present.append(rel)
    return present, missing

def report_templates_for_stamp(stamp: str) -> list[str]:
    templates = list(DEFAULT_REPORT_TEMPLATES) + list(FULL_TOOLBOX_REPORT_TEMPLATES)
    return [item.format(stamp=stamp) for item in templates]

def artifact_templates_for_stamp(stamp: str) -> list[str]:
    templates = list(DEFAULT_ARTIFACT_TEMPLATES) + list(FULL_TOOLBOX_ARTIFACT_TEMPLATES)
    return [item.format(stamp=stamp) for item in templates]

def coalesce_list(*values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for items in values:
        for item in split_path_values(items):
            if item not in seen:
                result.append(item)
                seen.add(item)
    return result

def collect_report_facts(repo_root: Path, report_paths: list[str]) -> dict[str, Any]:
    reports_generated: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    provider_execution_performed = False
    provider_execution_claim_seen = False
    patch_application_performed = False
    source_writes_performed = False
    sqlite_write_performed = False
    persistent_memory_write_performed = False
    blender_runtime_execution_performed = False
    tool_requests: list[dict[str, Any]] = []

    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        entry: dict[str, Any] = {
            "path": repo_relative(path, repo_root),
            "exists": path.exists(),
            "json_ok": data is not None,
            "kind": data.get("kind") if data else None,
            "passed": data.get("passed") if data else None,
        }
        if parse_error and parse_error != "missing":
            entry["parse_error"] = parse_error
            warnings.append(f"{entry['path']}: {parse_error}")
        if data:
            provider_execution_performed = provider_execution_performed or _provider_work_verified(data)
            provider_execution_claim_seen = (
                provider_execution_claim_seen or _provider_execution_claim_seen(data)
            )
            patch_application_performed = (
                patch_application_performed or data.get("patch_application_performed") is True
            )
            source_writes_performed = (
                source_writes_performed or data.get("source_writes_performed") is True
            )
            sqlite_write_performed = (
                sqlite_write_performed or data.get("sqlite_write_performed") is True
            )
            persistent_memory_write_performed = (
                persistent_memory_write_performed
                or data.get("persistent_memory_write_performed") is True
            )
            blender_runtime_execution_performed = (
                blender_runtime_execution_performed
                or data.get("blender_runtime_execution_performed") is True
            )
            if isinstance(data.get("errors"), list):
                errors.extend(str(item) for item in data.get("errors", []) if item)
            if isinstance(data.get("warnings"), list):
                warnings.extend(str(item) for item in data.get("warnings", []) if item)
            for key in ("tool_requests", "runtime_tool_requests"):
                raw = data.get(key)
                if isinstance(raw, list):
                    for request in raw:
                        if isinstance(request, dict):
                            tool_requests.append(
                                {
                                    "source_report": repo_relative(path, repo_root),
                                    "id": request.get("id"),
                                    "tool": request.get("tool"),
                                    "reason": request.get("reason"),
                                    "args": (
                                        request.get("args")
                                        if isinstance(request.get("args"), dict)
                                        else {}
                                    ),
                                }
                            )
        reports_generated.append(entry)

    return {
        "reports_generated": reports_generated,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": provider_execution_performed,
        "provider_execution_claim_seen": provider_execution_claim_seen,
        "patch_application_performed": patch_application_performed,
        "source_writes_performed": source_writes_performed,
        "sqlite_write_performed": sqlite_write_performed,
        "persistent_memory_write_performed": persistent_memory_write_performed,
        "blender_runtime_execution_performed": blender_runtime_execution_performed,
        "tool_requests_executed_or_proposed": tool_requests,
    }

def artifact_hints_from_reports(repo_root: Path, report_paths: list[str]) -> list[str]:
    """Promote report-declared side artifacts, especially CSV evidence, into bundles."""
    artifacts: list[str] = []
    seen: set[str] = set()
    for rel in report_paths:
        path = resolve_repo_path(repo_root, rel)
        data, parse_error = read_json_object(path)
        if parse_error or not data:
            continue
        for key in ("csv_written", "csv_output", "markdown_output", "markdown_report"):
            value = data.get(key)
            if not isinstance(value, str) or not value:
                continue
            artifact_path = resolve_repo_path(repo_root, value)
            artifact_rel = repo_relative(artifact_path, repo_root)
            if artifact_rel in seen or not artifact_path.exists():
                continue
            seen.add(artifact_rel)
            artifacts.append(artifact_rel)
    return artifacts

def build_remaining_gaps(
    missing_reports: list[dict[str, Any]],
    missing_artifacts: list[dict[str, Any]],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    gaps.extend(missing_reports)
    gaps.extend(missing_artifacts)
    if not any(item.get("tool") for item in facts.get("tool_requests_executed_or_proposed", [])):
        gaps.append(
            {
                "gap": "runtime tool requests not proven in provider-backed run",
                "detail": "No concrete tool_requests were found in the included reports.",
            }
        )
    if facts.get("patch_application_performed"):
        gaps.append(
            {
                "gap": "patch application detected",
                "detail": "Expected report-only execution.",
            }
        )
    if facts.get("sqlite_write_performed") or facts.get("persistent_memory_write_performed"):
        gaps.append(
            {
                "gap": "SQLite or persistent memory write detected",
                "detail": "Expected read-only/report-only behavior.",
            }
        )
    return gaps
