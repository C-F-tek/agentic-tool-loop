#!/usr/bin/env python3
"""Read-only MCP server for persisted agent job artifacts."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-job-artifact-mcp"
SERVER_VERSION = "0.1.0"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SUPPORT_SUBTURN_TOOLS = frozenset(
    {
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
    }
)


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def _dedupe(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _job_roots(root: Path) -> list[Path]:
    codex_agentic_loop_roots: list[Path] = []
    codex_agentic_loop_root = root / "state" / "codex_bridge" / "agentic_loop_client"
    if codex_agentic_loop_root.is_dir():
        codex_agentic_loop_roots = [
            path / "workspace" / "agent-jobs"
            for path in sorted(codex_agentic_loop_root.glob("port-*"))
            if path.is_dir()
        ]
    candidates = [
        _env_path("AICARMINE_AGENT_JOB_ROOT"),
        root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs",
        *codex_agentic_loop_roots,
        root / "output" / "agent-jobs",
        root / "output" / "agent_jobs",
        root / "agent-jobs",
        root / "agent_jobs",
    ]
    return _dedupe([path for path in candidates if path is not None])


def _safe_job_id(value: Any) -> str:
    job_id = str(value or "").strip()
    if not job_id:
        raise ValueError("missing job_id")
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"invalid job_id: {job_id}")
    return job_id


def _find_job_dir(root: Path, job_id: str) -> Path | None:
    for jobs_root in _job_roots(root):
        candidate = jobs_root / job_id
        try:
            resolved = candidate.resolve()
            resolved.relative_to(jobs_root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_dir():
            return resolved
    return None


def _read_text(path: Path, *, max_chars: int) -> tuple[str, bool]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(max_chars + 1)
    truncated = len(text) > max_chars
    return text[:max_chars], truncated


def _read_json(path: Path, *, max_chars: int = 2_000_000) -> Any:
    try:
        text, truncated = _read_text(path, max_chars=max_chars)
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed["_artifact_path"] = str(path)
            parsed["_truncated_before_parse"] = truncated
        return parsed
    except Exception as exc:
        return {"_read_error": str(exc), "_artifact_path": str(path)}


def _read_events(path: Path, *, max_lines: int = 5000) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.is_file():
        return events
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            if index >= max_lines:
                break
            raw = line.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"event_type": "raw", "message": raw}
            if isinstance(parsed, dict):
                events.append(parsed)
    return events


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or event.get("event_type") or event.get("name") or "").strip()


def _event_step(event: dict[str, Any]) -> int | None:
    for key in ("step", "step_index", "current_step"):
        try:
            value = event.get(key)
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return dict(value) if isinstance(value, dict) else {}


def _event_tool(event: dict[str, Any]) -> str:
    payload = _event_payload(event)
    return str(payload.get("tool") or "").strip()


def _support_subturn_event(event: dict[str, Any]) -> bool:
    payload = _event_payload(event)
    return bool(payload.get("support_subturn")) or _event_tool(event) in SUPPORT_SUBTURN_TOOLS


def _tool_result_step_from_name(name: str) -> int | None:
    match = re.search(r"step-(\d+)", str(name or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _payload_preview(value: Any, *, max_chars: int) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return {
        "text": text[:max_chars],
        "chars": len(text),
        "truncated": len(text) > max_chars,
    }


def _compact_subturn_event(event: dict[str, Any], *, include_payload: bool, max_chars: int) -> dict[str, Any]:
    payload = _event_payload(event)
    args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    written = payload.get("written") if isinstance(payload.get("written"), dict) else {}
    row: dict[str, Any] = {
        "step": _event_step(event),
        "type": _event_type(event),
        "message": event.get("message"),
        "tool": _event_tool(event),
        "support_subturn": _support_subturn_event(event),
        "semantic_step": payload.get("semantic_step"),
        "support_subturn_index": payload.get("support_subturn_index"),
        "ok": payload.get("ok"),
        "kind": args.get("kind") or payload.get("kind") or payload.get("mode") or written.get("kind"),
        "tag": args.get("tag") or written.get("tag"),
        "document_id": args.get("document_id") or payload.get("document_id"),
        "offset": args.get("offset"),
        "max_chars": args.get("max_chars"),
        "artifact": payload.get("artifact"),
        "guard_type": payload.get("guard_type"),
        "violations": payload.get("violations"),
    }
    if include_payload:
        row["payload_preview"] = _payload_preview(payload, max_chars=max_chars)
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _tool_from_result_payload_or_name(payload: Any, name: str) -> str:
    if isinstance(payload, dict) and payload.get("tool"):
        return str(payload.get("tool") or "").strip()
    lowered = name.lower()
    for tool in SUPPORT_SUBTURN_TOOLS:
        if tool in lowered:
            return tool
    return ""


def _compact_subturn_tool_result(path: Path, payload: Any, *, include_payload: bool, max_chars: int) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    written = data.get("written") if isinstance(data.get("written"), dict) else {}
    row: dict[str, Any] = {
        "name": path.name,
        "path": str(path),
        "step": _tool_result_step_from_name(path.name),
        "tool": _tool_from_result_payload_or_name(payload, path.name),
        "support_subturn": bool(data.get("support_subturn")) or _tool_from_result_payload_or_name(payload, path.name) in SUPPORT_SUBTURN_TOOLS,
        "semantic_step": data.get("semantic_step"),
        "support_subturn_index": data.get("support_subturn_index"),
        "ok": data.get("ok"),
        "mode": data.get("mode"),
        "kind": data.get("kind") or written.get("kind"),
        "tag": written.get("tag"),
        "document_id": data.get("document_id"),
        "artifact": data.get("artifact"),
    }
    if include_payload:
        row["payload_preview"] = _payload_preview(payload, max_chars=max_chars)
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _job_file_overview(job_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(job_dir.iterdir(), key=lambda item: item.name.lower()):
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append(
            {
                "name": path.name,
                "kind": "directory" if path.is_dir() else "file",
                "size_bytes": stat.st_size if path.is_file() else None,
                "modified_unix": stat.st_mtime,
            }
        )
    return rows


def _list_jobs(args: dict[str, Any], root: Path) -> dict[str, Any]:
    limit = _safe_int(args.get("limit") or args.get("max_results"), 50, 1, 500)
    rows: list[dict[str, Any]] = []
    roots = _job_roots(root)
    for jobs_root in roots:
        if not jobs_root.is_dir():
            continue
        for item in jobs_root.iterdir():
            if not item.is_dir():
                continue
            marker_files = [
                item / "job.json",
                item / "state.json",
                item / "final.json",
                item / "events.ndjson",
                item / "planner_composer.sqlite",
            ]
            existing = [path for path in marker_files if path.exists()]
            if not existing:
                continue
            newest = max(path.stat().st_mtime for path in existing)
            job_json = _read_json(item / "job.json") if (item / "job.json").is_file() else {}
            rows.append(
                {
                    "job_id": item.name,
                    "root": str(item.resolve()),
                    "status": job_json.get("status") if isinstance(job_json, dict) else "",
                    "goal": job_json.get("goal") if isinstance(job_json, dict) else "",
                    "current_step": job_json.get("current_step") if isinstance(job_json, dict) else None,
                    "modified_unix": newest,
                    "files": [path.name for path in existing],
                }
            )
    rows.sort(key=lambda item: float(item.get("modified_unix") or 0), reverse=True)
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_list_jobs",
        "mode": "local_filesystem_no_http",
        "roots": [str(path) for path in roots],
        "jobs": rows[:limit],
        "count": min(len(rows), limit),
        "truncated": len(rows) > limit,
    }


def _summary(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id, "roots": [str(path) for path in _job_roots(root)]}

    job_json = _read_json(job_dir / "job.json") if (job_dir / "job.json").is_file() else {}
    final_json = _read_json(job_dir / "final.json") if (job_dir / "final.json").is_file() else {}
    events = _read_events(job_dir / "events.ndjson")
    event_types = Counter(_event_type(event) or "<missing>" for event in events)
    rejections = _select_rejection_events(events)
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_summary",
        "job_id": job_id,
        "root": str(job_dir),
        "status": job_json.get("status") if isinstance(job_json, dict) else "",
        "goal": job_json.get("goal") if isinstance(job_json, dict) else "",
        "current_step": job_json.get("current_step") if isinstance(job_json, dict) else None,
        "max_steps": job_json.get("max_steps") if isinstance(job_json, dict) else None,
        "final_status": final_json.get("status") if isinstance(final_json, dict) else "",
        "blocked_by": final_json.get("blocked_by") if isinstance(final_json, dict) else "",
        "event_count": len(events),
        "event_types": dict(event_types.most_common(40)),
        "rejection_count": len(rejections),
        "latest_events": events[-10:],
        "files": _job_file_overview(job_dir),
        "mode": "local_filesystem_no_http",
    }


def _events(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    tail = _safe_int(args.get("tail") or args.get("limit"), 100, 1, 2000)
    max_lines = _safe_int(args.get("max_lines"), 10000, 1, 100000)
    raw_types = args.get("types")
    types = {str(item) for item in raw_types} if isinstance(raw_types, list) else set()
    step = args.get("step")
    step_number = None
    if step is not None:
        try:
            step_number = int(step)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_step", "step": step}

    events = _read_events(job_dir / "events.ndjson", max_lines=max_lines)
    filtered = [
        event
        for event in events
        if (not types or _event_type(event) in types)
        and (step_number is None or _event_step(event) == step_number)
    ]
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_events",
        "job_id": job_id,
        "events": filtered[-tail:],
        "event_count_total": len(events),
        "event_count_filtered": len(filtered),
        "tail": tail,
    }


def _final(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    max_chars = _safe_int(args.get("max_chars"), 2_000_000, 1000, 5_000_000)
    final_json = _read_json(job_dir / "final.json", max_chars=max_chars) if (job_dir / "final.json").is_file() else {}
    final_md = ""
    final_md_truncated = False
    if (job_dir / "final.md").is_file():
        final_md, final_md_truncated = _read_text(job_dir / "final.md", max_chars=max_chars)
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_final",
        "job_id": job_id,
        "final_json": final_json,
        "final_md": final_md,
        "final_md_truncated": final_md_truncated,
    }


def _tool_results(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    tool_dir = job_dir / "tool-results"
    if not tool_dir.is_dir():
        return {"ok": True, "tool": "aicarmine_job_artifact_tool_results", "job_id": job_id, "results": [], "count": 0}
    include_payload = bool(args.get("include_payload", False))
    max_results = _safe_int(args.get("max_results") or args.get("limit"), 50, 1, 500)
    max_chars = _safe_int(args.get("max_chars"), 40000, 1000, 500000)
    tool_filter = str(args.get("tool_filter") or args.get("tool") or "").strip().lower()

    rows: list[dict[str, Any]] = []
    for path in sorted(tool_dir.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if not path.is_file():
            continue
        if tool_filter and tool_filter not in path.name.lower():
            continue
        stat = path.stat()
        row: dict[str, Any] = {
            "name": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_unix": stat.st_mtime,
        }
        if include_payload:
            if path.suffix.lower() == ".json":
                row["payload"] = _read_json(path, max_chars=max_chars)
            else:
                text, truncated = _read_text(path, max_chars=max_chars)
                row["text"] = text
                row["truncated"] = truncated
        rows.append(row)
        if len(rows) >= max_results:
            break
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_tool_results",
        "job_id": job_id,
        "results": rows,
        "count": len(rows),
        "include_payload": include_payload,
    }


def _subturns(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    tail = _safe_int(args.get("tail") or args.get("limit"), 200, 1, 5000)
    max_lines = _safe_int(args.get("max_lines"), 300000, 1, 500000)
    include_payload = bool(args.get("include_payload", False))
    max_chars = _safe_int(args.get("max_chars"), 8000, 500, 100000)
    events = _read_events(job_dir / "events.ndjson", max_lines=max_lines)
    support_events = [_compact_subturn_event(event, include_payload=include_payload, max_chars=max_chars) for event in events if _support_subturn_event(event)]

    tool_result_rows: list[dict[str, Any]] = []
    tool_dir = job_dir / "tool-results"
    if tool_dir.is_dir():
        for path in sorted(tool_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            payload = _read_json(path, max_chars=max_chars) if path.suffix.lower() == ".json" else {}
            tool = _tool_from_result_payload_or_name(payload, path.name)
            if tool not in SUPPORT_SUBTURN_TOOLS and not (isinstance(payload, dict) and payload.get("support_subturn")):
                continue
            tool_result_rows.append(_compact_subturn_tool_result(path, payload, include_payload=include_payload, max_chars=max_chars))

    by_tool = Counter(str(row.get("tool") or "<missing>") for row in support_events if row.get("tool"))
    by_kind = Counter(str(row.get("kind") or "<missing>") for row in support_events if row.get("kind"))
    repeated_answer_chunk_tags = [
        tag
        for tag, count in Counter(
            str(row.get("tag") or "")
            for row in support_events
            if row.get("kind") in {"answer_chunk", "final_answer_chunk"} and row.get("tag")
        ).items()
        if count > 1
    ]
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_subturns",
        "job_id": job_id,
        "mode": "local_filesystem_no_http",
        "support_subturn_tools": sorted(SUPPORT_SUBTURN_TOOLS),
        "events": support_events[-tail:],
        "tool_results": tool_result_rows[-tail:],
        "subturn_event_count": len(support_events),
        "tool_result_count": len(tool_result_rows),
        "counts": {
            "by_tool": dict(by_tool.most_common()),
            "by_kind": dict(by_kind.most_common()),
            "repeated_answer_chunk_tags": repeated_answer_chunk_tags,
        },
        "tail": tail,
        "include_payload": include_payload,
    }


def _planner_payload(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    prompt_dir = job_dir / "planner-prompts"
    if not prompt_dir.is_dir():
        return {"ok": False, "error": "planner_prompts_dir_missing", "job_id": job_id}
    raw_step = args.get("step")
    if raw_step is None:
        candidates = sorted(prompt_dir.glob("step-*-planner-payload.json"))
        path = candidates[-1] if candidates else None
    else:
        try:
            step = int(raw_step)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_step", "step": raw_step}
        path = prompt_dir / f"step-{step:03d}-planner-payload.json"
    if path is None or not path.is_file():
        return {"ok": False, "error": "planner_payload_not_found", "job_id": job_id, "step": raw_step}

    include_payload = bool(args.get("include_payload", True))
    max_chars = _safe_int(args.get("max_chars"), 500000, 1000, 2_000_000)
    payload = _read_json(path, max_chars=max_chars)
    summary: dict[str, Any] = {}
    if isinstance(payload, dict):
        raw_planner_payload = payload.get("planner_payload")
        planner_payload = raw_planner_payload if isinstance(raw_planner_payload, dict) else payload
        messages = planner_payload.get("messages")
        tools = planner_payload.get("tools")
        summary = {
            "top_level_keys": sorted(str(key) for key in payload.keys()),
            "planner_payload_keys": sorted(str(key) for key in planner_payload.keys()) if planner_payload is not payload else [],
            "messages_count": len(messages) if isinstance(messages, list) else None,
            "tools_count": len(tools) if isinstance(tools, list) else None,
            "model": planner_payload.get("model") or payload.get("planner_model"),
            "stream": planner_payload.get("stream"),
            "user_payload_keys": sorted(str(key) for key in (payload.get("user_payload") or {}).keys())
            if isinstance(payload.get("user_payload"), dict)
            else [],
        }
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_planner_payload",
        "job_id": job_id,
        "path": str(path),
        "summary": summary,
        "payload": payload if include_payload else None,
        "include_payload": include_payload,
    }


def _select_rejection_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    markers = ("rejected", "validation_failed", "native_tool_call_required", "tool_not_in_turn_surface")
    for event in events:
        text = json.dumps(event, ensure_ascii=False, default=str).lower()
        if any(marker in text for marker in markers):
            selected.append(event)
    return selected


def _rejections(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        job_id = _safe_job_id(args.get("job_id"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    job_dir = _find_job_dir(root, job_id)
    if job_dir is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}

    tail = _safe_int(args.get("tail") or args.get("limit"), 100, 1, 1000)
    events = _read_events(job_dir / "events.ndjson", max_lines=_safe_int(args.get("max_lines"), 100000, 1, 300000))
    selected = _select_rejection_events(events)
    compacted: list[dict[str, Any]] = []
    for event in selected[-tail:]:
        compacted.append(
            {
                "step": _event_step(event),
                "type": _event_type(event),
                "message": event.get("message"),
                "reason": event.get("reason") or event.get("blocked_by"),
                "event": event,
            }
        )
    return {
        "ok": True,
        "tool": "aicarmine_job_artifact_rejections",
        "job_id": job_id,
        "rejections": compacted,
        "count": len(compacted),
        "total_rejections": len(selected),
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "read_only": True,
            "mode": "local_filesystem_no_http",
            "job_roots": [str(path) for path in _job_roots(root)],
            "no_broker_http": True,
            "no_agentic_loop": True,
        }
    )
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_job_artifact_health"] = ToolSpec(
        name="aicarmine_job_artifact_health",
        description="Report job artifact MCP health and read-only filesystem roots.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_job_artifact_list_jobs"] = ToolSpec(
        name="aicarmine_job_artifact_list_jobs",
        description="List persisted agent jobs from allowlisted local artifact roots.",
        input_schema=object_schema({"limit": integer_prop(50, 1, 500), "max_results": integer_prop(50, 1, 500)}),
        handler=_list_jobs,
    )
    tools["aicarmine_job_artifact_summary"] = ToolSpec(
        name="aicarmine_job_artifact_summary",
        description="Summarize one persisted agent job without calling broker HTTP.",
        input_schema=object_schema({"job_id": string_prop()}, required=["job_id"]),
        handler=_summary,
    )
    tools["aicarmine_job_artifact_events"] = ToolSpec(
        name="aicarmine_job_artifact_events",
        description="Read filtered/tail events from a job events.ndjson file.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "tail": integer_prop(100, 1, 2000),
                "limit": integer_prop(100, 1, 2000),
                "max_lines": integer_prop(10000, 1, 100000),
                "types": string_array_prop(),
                "step": integer_prop(0, 0, 100000),
            },
            required=["job_id"],
        ),
        handler=_events,
    )
    tools["aicarmine_job_artifact_final"] = ToolSpec(
        name="aicarmine_job_artifact_final",
        description="Read final.json and final.md for a persisted agent job.",
        input_schema=object_schema({"job_id": string_prop(), "max_chars": integer_prop(2000000, 1000, 5000000)}, required=["job_id"]),
        handler=_final,
    )
    tools["aicarmine_job_artifact_tool_results"] = ToolSpec(
        name="aicarmine_job_artifact_tool_results",
        description="List or read job tool-result artifacts from tool-results/.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "tool_filter": string_prop(),
                "tool": string_prop(),
                "include_payload": boolean_prop(False),
                "max_results": integer_prop(50, 1, 500),
                "limit": integer_prop(50, 1, 500),
                "max_chars": integer_prop(40000, 1000, 500000),
            },
            required=["job_id"],
        ),
        handler=_tool_results,
    )
    tools["aicarmine_job_artifact_subturns"] = ToolSpec(
        name="aicarmine_job_artifact_subturns",
        description="Read support-subturn events and tool-result artifacts from a persisted job without broker HTTP.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "tail": integer_prop(200, 1, 5000),
                "limit": integer_prop(200, 1, 5000),
                "max_lines": integer_prop(300000, 1, 500000),
                "include_payload": boolean_prop(False),
                "max_chars": integer_prop(8000, 500, 100000),
            },
            required=["job_id"],
        ),
        handler=_subturns,
    )
    tools["aicarmine_job_artifact_planner_payload"] = ToolSpec(
        name="aicarmine_job_artifact_planner_payload",
        description="Read a planner-prompts step payload for a persisted agent job.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "step": integer_prop(0, 0, 100000),
                "include_payload": boolean_prop(True),
                "max_chars": integer_prop(500000, 1000, 2000000),
            },
            required=["job_id"],
        ),
        handler=_planner_payload,
    )
    tools["aicarmine_job_artifact_rejections"] = ToolSpec(
        name="aicarmine_job_artifact_rejections",
        description="Extract planner/controller rejection events from a job event log.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "tail": integer_prop(100, 1, 1000),
                "limit": integer_prop(100, 1, 1000),
                "max_lines": integer_prop(100000, 1, 300000),
            },
            required=["job_id"],
        ),
        handler=_rejections,
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_job_artifact_health",
            real_tool="aicarmine_job_artifact_list_jobs",
            real_args={"limit": 5},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
