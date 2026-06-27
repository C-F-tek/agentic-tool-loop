"""Offline loop replay diagnostics.

This module reads persisted job artifacts and produces a bounded diagnostic
report. It does not dispatch tools, call models, mutate job state, or change
planner/controller gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA = "loop_replay_report.v1"
MAX_PREVIEW_ITEMS = 20
FULL_LOOP_REQUIRED_EVENT_GROUPS = {
    "job_queued": {"job_queued"},
    "agentic_loop_started": {"agentic_loop_started"},
    "planner_request_started": {"planner_request_started"},
    "planner_decision": {"planner_decision", "planner_decision_rejected"},
}

EvidenceBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
Validator = Callable[[str, dict[str, Any], list[dict[str, Any]]], dict[str, Any]]


def _read_json(path: Path, default: Any) -> Any:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(raw)
    except FileNotFoundError:
        return default
    except PermissionError as exc:
        return {
            "_read_error": "permission_denied",
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    except json.JSONDecodeError as exc:
        return {
            "_read_error": "invalid_json",
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "payload_preview": raw[:500] if "raw" in locals() else "",
        }
    except OSError as exc:
        return {
            "_read_error": "read_failed",
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        # Missing events.ndjson must remain an empty list so SQLite fallback can recover.
        return rows
    except PermissionError as exc:
        return [{
            "_read_error": "permission_denied",
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }]
    except OSError as exc:
        return [{
            "_read_error": "os_error",
            "path": str(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }]
    for line_number, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            rows.append({
                "_read_error": "invalid_ndjson_line",
                "path": str(path),
                "line_number": line_number,
                "line_preview": text[:500],
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            rows.append({
                "_read_error": "non_object_ndjson_line",
                "path": str(path),
                "line_number": line_number,
                "decoded_type": type(row).__name__,
            })
    return rows


def _event_types(events: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("event_type") or "") for item in events if isinstance(item, dict)}


def _missing_full_loop_events(events: list[dict[str, Any]]) -> list[str]:
    event_types = _event_types(events)
    return [
        rule_name
        for rule_name, alternatives in FULL_LOOP_REQUIRED_EVENT_GROUPS.items()
        if not (event_types & alternatives)
    ]


def _read_sqlite_events(job_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not job_id:
        return [], {"available": False, "reason": "job_id_missing"}
    try:
        from ...config import AGENT_JOB_DB  # Late import keeps CLI import lightweight.
    except Exception as exc:
        return [], {
            "available": False,
            "reason": "config_import_failed",
            "error_stage": "config_import",
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    db_path = Path(AGENT_JOB_DB)
    if not db_path.exists() or not db_path.is_file():
        return [], {
            "available": False,
            "reason": "sqlite_db_missing",
            "db_path": str(db_path),
        }
    uri = "file:" + str(db_path).replace("\\", "/") + "?mode=ro"
    db: sqlite3.Connection | None = None
    try:
        db = sqlite3.connect(uri, uri=True)
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            SELECT id, job_id, ts, step, event_type, message, payload_json
            FROM events
            WHERE job_id = ?
            ORDER BY id
            """,
            (job_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        return [], {
            "available": False,
            "reason": "sqlite_operational_error",
            "db_path": str(db_path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    except sqlite3.DatabaseError as exc:
        return [], {
            "available": False,
            "reason": "sqlite_database_error",
            "db_path": str(db_path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    except OSError as exc:
        return [], {
            "available": False,
            "reason": "sqlite_os_error",
            "db_path": str(db_path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    except Exception as exc:
        return [], {
            "available": False,
            "reason": "sqlite_read_failed",
            "db_path": str(db_path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    finally:
        if db is not None:
            try:
                db.close()
            except sqlite3.Error:
                pass
    events: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        raw_payload = row["payload_json"]
        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                parsed = json.loads(raw_payload)
                payload = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError as exc:
                payload = {
                    "_read_error": "invalid_sqlite_event_payload_json",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "payload_preview": raw_payload[:500],
                }
            except Exception as exc:
                payload = {
                    "_read_error": "sqlite_event_payload_parse_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "payload_preview": raw_payload[:500],
                }
        events.append({
            "ts": row["ts"],
            "job_id": row["job_id"],
            "step": row["step"],
            "event_type": row["event_type"],
            "message": row["message"],
            "payload": payload,
            "event_storage": "sqlite_index",
            "sqlite_event_id": row["id"],
        })
    return events, {
        "available": True,
        "db_path": str(db_path),
        "count": len(events),
    }


def _select_replay_events(
    *,
    events_ndjson: list[dict[str, Any]],
    sqlite_events: list[dict[str, Any]],
    sqlite_diagnostic: dict[str, Any],
    require_full_loop: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ndjson_missing = _missing_full_loop_events(events_ndjson) if require_full_loop else []
    sqlite_missing = _missing_full_loop_events(sqlite_events) if require_full_loop and sqlite_events else []
    selected = "events_ndjson"
    events = events_ndjson
    notes: list[dict[str, Any]] = []
    if sqlite_events and not events_ndjson:
        selected = "sqlite_index"
        events = sqlite_events
        notes.append({
            "rule": "events_ndjson_empty_or_missing",
            "sqlite_index_used": True,
        })
    elif require_full_loop and sqlite_events and ndjson_missing and not sqlite_missing:
        selected = "sqlite_index_recovered_required_events"
        events = sqlite_events
        notes.append({
            "rule": "events_ndjson_missing_required_events_recovered_from_sqlite",
            "events_ndjson_missing_required_events": ndjson_missing,
            "sqlite_index_used": True,
        })
    elif sqlite_events and len(sqlite_events) != len(events_ndjson):
        notes.append({
            "rule": "event_source_count_mismatch",
            "events_ndjson_count": len(events_ndjson),
            "sqlite_index_count": len(sqlite_events),
            "selected_source": selected,
        })
    return events, {
        "selected": selected,
        "events_ndjson": {
            "count": len(events_ndjson),
            "missing_required_full_loop_events": ndjson_missing,
        },
        "sqlite_index": {
            **sqlite_diagnostic,
            "missing_required_full_loop_events": sqlite_missing,
        },
        "notes": notes,
    }


def _resolve_job_root(*, job_id: str | None, job_root: str | Path | None) -> Path:
    if job_root:
        return Path(job_root)
    if not job_id:
        raise ValueError("job_id_or_job_root_required")
    from ...job_store import agent_job_root  # Late import keeps module import lightweight.

    return agent_job_root(str(job_id))


def _default_evidence_builder(goal: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    from ... import planner  # Late import: CLI-only default path.

    return planner.planner_evidence_contract(goal, history)


def _default_validator(goal: str, decision: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    from ... import planner  # Late import: CLI-only default path.

    return planner.validate_planner_decision_against_evidence(goal, decision, history, None, None)


def _history_tool_result(row: dict[str, Any]) -> dict[str, Any]:
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    if result:
        return result
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    return result


def _stable_key(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def _rejection_signature(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("invalid_decision_signature"), dict) and result.get("invalid_decision_signature"):
        return result["invalid_decision_signature"]
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    violations = result.get("violations") if isinstance(result.get("violations"), list) else []
    return {
        "violations": [str(v) for v in violations],
        "rejected_decision": {
            key: rejected.get(key)
            for key in ("action", "tool", "arguments")
            if rejected.get(key) not in (None, "", [], {})
        },
    }


def _guard_result_rows_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        result = _history_tool_result(row)
        if result.get("tool") != "controller_guard":
            continue
        rows.append({"step": row.get("step"), "result": result, "source": "job_history"})
    return rows


def _guard_result_rows_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in events:
        if not isinstance(row, dict):
            continue
        event_type = str(row.get("event_type") or "")
        if event_type != "planner_decision_rejected":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if not payload:
            continue
        result = dict(payload)
        result.setdefault("tool", "controller_guard")
        rows.append({"step": row.get("step"), "result": result, "source": "events_ndjson"})
    return rows


def _detect_repeated_invalid_decisions(
    history: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for row in _guard_result_rows_from_history(history) + _guard_result_rows_from_events(events or []):
        result = row["result"]
        signature = _rejection_signature(result)
        key = _stable_key(signature)
        item = counts.setdefault(
            key,
            {
                "signature": signature,
                "count": 0,
                "first_step": row.get("step"),
                "last_step": row.get("step"),
                "sources": [],
            },
        )
        item["count"] += 1
        item["last_step"] = row.get("step")
        source = str(row.get("source") or "")
        if source and source not in item["sources"]:
            item["sources"].append(source)
    return [item for item in counts.values() if int(item.get("count") or 0) > 1]


def _candidate_paths(action: dict[str, Any]) -> list[str]:
    if action.get("tool") != "repo_read":
        return []
    args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    paths: list[str] = []
    if isinstance(args.get("path"), str):
        paths.append(args["path"])
    if isinstance(args.get("paths"), list):
        paths.extend(str(path) for path in args["paths"] if isinstance(path, str))
    return paths


def _candidate_validator_mismatches(contract: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    admissible = {
        str(path)
        for path in (
            contract.get("validator_admissible_repo_read_paths")
            if isinstance(contract.get("validator_admissible_repo_read_paths"), list)
            else []
        )
    }
    mismatches: list[dict[str, Any]] = []
    for action in candidates:
        if not isinstance(action, dict):
            continue
        for path in _candidate_paths(action):
            if path not in admissible:
                mismatches.append({
                    "tool": action.get("tool"),
                    "path": path,
                    "action_id": action.get("action_id"),
                    "reason": "candidate_path_not_validator_admissible",
                })
    return mismatches


def target_tool_coverage_from_history(history: list[dict[str, Any]], target_tool: str) -> dict[str, Any]:
    target = str(target_tool or "").strip()
    coverage = {
        "covered": False,
        "target_tool": target,
        "reason": "target_tool_not_attempted_after_planner",
        "matched_step": None,
        "matched_kind": "",
    }
    if not target:
        return coverage
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            step = int(row.get("step") or 0)
        except Exception:
            step = 0
        if step <= 0:
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        tool_result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
        decision_tool = str(decision.get("tool") or "").strip()
        result_tool = str(tool_result.get("tool") or "").strip()
        if str(decision.get("action") or "").strip() == "tool" and decision_tool == target:
            return {
                "covered": True,
                "target_tool": target,
                "reason": "planner_decision_tool_after_planner",
                "matched_step": step,
                "matched_kind": "decision",
            }
        if result_tool == target:
            return {
                "covered": True,
                "target_tool": target,
                "reason": "tool_result_after_planner",
                "matched_step": step,
                "matched_kind": "tool_result",
            }
        row_text = json.dumps(row, ensure_ascii=False, default=str).lower()
        if target.lower() in row_text and any(
            marker in row_text
            for marker in ("validator", "controller_guard", "blocked", "rejected", "unavailable", "missing", "requires")
        ):
            return {
                "covered": True,
                "target_tool": target,
                "reason": "typed_guard_mentions_target_after_planner",
                "matched_step": step,
                "matched_kind": "typed_guard",
            }
    return coverage


def target_tool_coverage_from_events(events: list[dict[str, Any]], target_tool: str) -> dict[str, Any]:
    target = str(target_tool or "").strip()
    coverage = {
        "covered": False,
        "target_tool": target,
        "reason": "target_tool_not_attempted_after_planner",
        "matched_step": None,
        "matched_kind": "",
        "matched_source": "events_ndjson",
        "matched_event_type": "",
    }
    if not target:
        return coverage
    for row in events if isinstance(events, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            step = int(row.get("step") or 0)
        except Exception:
            step = 0
        if step <= 0:
            continue
        event_type = str(row.get("event_type") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        event_tool = str(payload.get("tool") or "").strip()
        event_action = str(payload.get("action") or "").strip()
        row_text = json.dumps(row, ensure_ascii=False, default=str).lower()
        if target.lower() in row_text and any(
            marker in row_text
            for marker in ("validator", "controller_guard", "blocked", "rejected", "unavailable", "missing", "requires")
        ):
            return {
                **coverage,
                "covered": True,
                "reason": "typed_guard_event_mentions_target_after_planner",
                "matched_step": step,
                "matched_kind": "typed_guard_event",
                "matched_event_type": event_type,
            }
        if event_type == "planner_decision" and event_action == "tool" and event_tool == target:
            return {
                **coverage,
                "covered": True,
                "reason": "planner_decision_event_tool_after_planner",
                "matched_step": step,
                "matched_kind": "planner_decision_event",
                "matched_event_type": event_type,
            }
        if event_type in {"tool_start", "tool_result"} and event_tool == target:
            return {
                **coverage,
                "covered": True,
                "reason": f"{event_type}_event_after_planner",
                "matched_step": step,
                "matched_kind": event_type,
                "matched_event_type": event_type,
            }
    return coverage


def target_tool_coverage_from_runtime_artifacts(
    history: list[dict[str, Any]],
    events: list[dict[str, Any]],
    target_tool: str,
) -> dict[str, Any]:
    history_coverage = target_tool_coverage_from_history(history, target_tool)
    if history_coverage.get("covered") is True:
        history_coverage["matched_source"] = "job_history"
        return history_coverage
    event_coverage = target_tool_coverage_from_events(events, target_tool)
    if event_coverage.get("covered") is True:
        event_coverage["history_coverage"] = _bounded(history_coverage)
        return event_coverage
    history_coverage["matched_source"] = "job_history"
    history_coverage["event_coverage"] = _bounded(event_coverage)
    return history_coverage


def _validator_rejections_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _guard_result_rows_from_history(history):
        result = row["result"]
        rows.append({
            "step": row.get("step"),
            "source": row.get("source"),
            "guard_type": result.get("guard_type"),
            "summary": result.get("summary"),
            "violations": result.get("violations") if isinstance(result.get("violations"), list) else [],
        })
    return rows


def _validator_rejections_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _guard_result_rows_from_events(events):
        result = row["result"]
        rows.append({
            "step": row.get("step"),
            "source": row.get("source"),
            "guard_type": result.get("guard_type"),
            "summary": result.get("summary"),
            "violations": result.get("violations") if isinstance(result.get("violations"), list) else [],
        })
    return rows


def _recompute_validator_results(
    *,
    goal: str,
    history: list[dict[str, Any]],
    validator: Validator,
) -> list[dict[str, Any]]:
    recomputed: list[dict[str, Any]] = []
    prior: list[dict[str, Any]] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        action = str(decision.get("action") or "").strip().lower()
        if action in {"tool", "tool_batch", "final", "done", "complete", "completed", "block", "blocked"}:
            validation = validator(goal, decision, prior)
            recomputed.append({
                "step": row.get("step"),
                "ok": bool(validation.get("ok")) if isinstance(validation, dict) else False,
                "violations": (
                    validation.get("violations")
                    if isinstance(validation, dict) and isinstance(validation.get("violations"), list)
                    else []
                ),
                "decision_action": decision.get("action"),
                "decision_tool": decision.get("tool"),
            })
        prior.append(row)
    return recomputed


def _bounded(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _bounded(v) for k, v in list(value.items())[:MAX_PREVIEW_ITEMS]}
    if isinstance(value, list):
        out = [_bounded(item) for item in value[:MAX_PREVIEW_ITEMS]]
        if len(value) > MAX_PREVIEW_ITEMS:
            out.append({"_truncated_items": len(value) - MAX_PREVIEW_ITEMS})
        return out
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + f"...<truncated:{len(value) - 1000}>"
    return value


def _json_roundtrip(report: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))


def _first_prompt_payload(prompt_files: list[Path]) -> dict[str, Any]:
    if not prompt_files:
        return {}
    parsed = _read_json(prompt_files[0], {})
    return parsed if isinstance(parsed, dict) else {}


def _planner_prompt_audit(first_prompt: dict[str, Any], *, target_tool: str) -> dict[str, Any]:
    planner_payload = (
        first_prompt.get("planner_payload")
        if isinstance(first_prompt.get("planner_payload"), dict)
        else first_prompt
    )
    user_payload = first_prompt.get("user_payload") if isinstance(first_prompt.get("user_payload"), dict) else {}
    messages = planner_payload.get("messages") if isinstance(planner_payload, dict) else None
    native_tools = planner_payload.get("tools") if isinstance(planner_payload, dict) else None
    native_tool_names = [
        str((item.get("function") or {}).get("name") or "")
        for item in native_tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ] if isinstance(native_tools, list) else []
    explicit_request_context = (
        user_payload.get("explicit_request_context")
        if isinstance(user_payload.get("explicit_request_context"), dict)
        else {}
    )
    prompt_pack = user_payload.get("prompt_pack_contract") if isinstance(user_payload.get("prompt_pack_contract"), dict) else {}
    user_payload_text = json.dumps(user_payload, ensure_ascii=False, default=str)
    return {
        "schema": "planner_prompt_payload_audit.v1",
        "messages_present": isinstance(messages, list) and bool(messages),
        "native_tools_present": isinstance(native_tools, list) and bool(native_tools),
        "native_tool_names": native_tool_names,
        "target_tool_in_native_schema": bool(target_tool and target_tool in native_tool_names),
        "legacy_json_format": isinstance(planner_payload, dict) and planner_payload.get("format") == "json",
        "explicit_request_context": _bounded(explicit_request_context),
        "explicit_request_context_target_matches": (
            not target_tool
            or "target_internal_tool" not in explicit_request_context
            or explicit_request_context.get("target_internal_tool") == target_tool
        ),
        "prompt_pack_contract": _bounded(prompt_pack),
        "native_tools_schema_accounted_in_budget": prompt_pack.get("native_tools_schema_accounted_in_budget") is True,
        "native_tools_schema_chars": int(prompt_pack.get("native_tools_schema_chars") or 0),
        "normal_loop_context_sections": {
            key: key in user_payload_text
            for key in ("evidence_contract", "available_tools", "required_working_set")
        },
    }


def _runtime_loop_artifact_audit(
    *,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    prompt_files: list[Path],
    planner_stream_files: list[Path],
    tool_result_files: list[Path],
    target_tool: str,
    require_full_loop: bool,
) -> dict[str, Any]:
    event_types = _event_types(events)
    request_payload = state.get("request_payload") if isinstance(state.get("request_payload"), dict) else {}
    original_args = state.get("original_args") if isinstance(state.get("original_args"), dict) else {}
    prompt_audit = _planner_prompt_audit(_first_prompt_payload(prompt_files), target_tool=target_tool)
    target_coverage = target_tool_coverage_from_runtime_artifacts(
        state.get("history") if isinstance(state.get("history"), list) else [],
        events,
        target_tool,
    )
    failures: list[dict[str, Any]] = []

    def fail(rule: str, detail: Any = "") -> None:
        failures.append({"rule": rule, "detail": _bounded(detail)})

    if require_full_loop:
        if state.get("public_tool_name") != "vulkan_helper":
            fail("job_not_created_through_public_vulkan_helper", {"public_tool_name": state.get("public_tool_name")})
        if request_payload.get("tool_name") != "vulkan_helper":
            fail("request_payload_tool_name_not_vulkan_helper", {"tool_name": request_payload.get("tool_name")})
        if request_payload.get("bridge_public_tool_x") != "vulkan_helper":
            fail("request_payload_bridge_public_tool_x_not_vulkan_helper", {
                "bridge_public_tool_x": request_payload.get("bridge_public_tool_x")
            })
        for key in ("function", "tool_name", "requested_tool_name"):
            value = original_args.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "vulkan_helper":
                fail("original_args_internal_dispatch_key_leak", {key: value})
        if not prompt_files:
            fail("planner_prompt_payload_missing")
        if not planner_stream_files:
            fail("planner_stream_missing")
        if not tool_result_files and target_coverage.get("matched_kind") != "typed_guard_event":
            fail("tool_result_files_missing")
        for rule_name, alternatives in FULL_LOOP_REQUIRED_EVENT_GROUPS.items():
            if not (event_types & alternatives):
                fail("required_event_missing", rule_name)
        if target_tool == "repo_read" and "controller_preseed_file_surface" in event_types:
            fail("target_repo_read_covered_by_controller_preseed")
        if not prompt_audit["messages_present"]:
            fail("planner_payload_messages_missing")
        if not prompt_audit["native_tools_present"]:
            fail("planner_payload_native_tools_missing")
        if target_tool and not prompt_audit["target_tool_in_native_schema"]:
            fail("target_tool_missing_from_native_schema", {
                "target_tool": target_tool,
                "native_tool_names": prompt_audit["native_tool_names"],
            })
        if prompt_audit["legacy_json_format"]:
            fail("planner_payload_legacy_json_format")
        if not prompt_audit["explicit_request_context_target_matches"]:
            fail("explicit_request_context_target_mismatch", prompt_audit["explicit_request_context"])
        if not prompt_audit["native_tools_schema_accounted_in_budget"]:
            fail("native_tools_schema_not_accounted_in_budget")
        if int(prompt_audit["native_tools_schema_chars"] or 0) <= 0:
            fail("native_tools_schema_chars_missing")
        missing_sections = [
            key for key, present in prompt_audit["normal_loop_context_sections"].items() if not present
        ]
        if missing_sections:
            fail("normal_loop_context_sections_missing", missing_sections)
        if not any(
            "tool" in value
            or "controller" in value
            or "validator" in value
            or "rejected" in value
            or "job_completed" in value
            or "job_failed" in value
            for value in event_types
        ):
            fail("events_do_not_show_tool_controller_validator_or_terminal_activity", sorted(event_types))

    return {
        "schema": "runtime_loop_artifact_audit.v1",
        "diagnostic_only": True,
        "require_full_loop": bool(require_full_loop),
        "ok": not failures,
        "failures": failures,
        "public_tool_name": state.get("public_tool_name"),
        "request_payload_tool_name": request_payload.get("tool_name"),
        "request_payload_bridge_public_tool_x": request_payload.get("bridge_public_tool_x"),
        "event_types_preview": sorted(event_types)[:MAX_PREVIEW_ITEMS],
        "planner_prompt_count": len(prompt_files),
        "planner_stream_count": len(planner_stream_files),
        "tool_result_file_count": len(tool_result_files),
        "target_tool_coverage": _bounded(target_coverage),
        "planner_prompt": prompt_audit,
    }


def replay_loop_job(
    *,
    job_id: str | None = None,
    job_root: str | Path | None = None,
    target_tool: str | None = None,
    require_full_loop: bool = False,
    evidence_builder: EvidenceBuilder | None = None,
    validator: Validator | None = None,
) -> dict[str, Any]:
    root = _resolve_job_root(job_id=job_id, job_root=job_root)
    state = _read_json(root / "job.json", {})
    state = state if isinstance(state, dict) else {}
    resolved_job_id = str(job_id or state.get("job_id") or root.name)
    goal = str(state.get("goal") or state.get("user_goal") or "")
    history = state.get("history") if isinstance(state.get("history"), list) else []
    history = [row for row in history if isinstance(row, dict)]
    events_ndjson = _read_ndjson(root / "events.ndjson")
    sqlite_events, sqlite_event_diagnostic = _read_sqlite_events(resolved_job_id)
    events, event_sources = _select_replay_events(
        events_ndjson=events_ndjson,
        sqlite_events=sqlite_events,
        sqlite_diagnostic=sqlite_event_diagnostic,
        require_full_loop=require_full_loop,
    )
    tool_result_files = sorted((root / "tool-results").glob("*.json")) if (root / "tool-results").exists() else []
    prompt_files = sorted((root / "planner-prompts").glob("step-*-planner-payload.json")) if (root / "planner-prompts").exists() else []
    planner_stream_files = sorted((root / "planner-stream").glob("*.txt")) if (root / "planner-stream").exists() else []

    evidence_fn = evidence_builder or _default_evidence_builder
    validator_fn = validator or _default_validator
    evidence_contract = evidence_fn(goal, history)
    evidence_contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    repeated_invalid_decisions = _detect_repeated_invalid_decisions(history, events)
    validator_rejections = _validator_rejections_from_history(history) + _validator_rejections_from_events(events)
    candidate_mismatches = _candidate_validator_mismatches(evidence_contract)
    recomputed_validations = _recompute_validator_results(
        goal=goal,
        history=history,
        validator=validator_fn,
    )
    first_divergence = None
    if repeated_invalid_decisions:
        first_divergence = {
            "kind": "repeated_invalid_decision",
            "step": repeated_invalid_decisions[0].get("last_step"),
        }
    elif candidate_mismatches:
        first_divergence = {
            "kind": "candidate_validator_mismatch",
            "path": candidate_mismatches[0].get("path"),
        }

    report = {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "job_id": resolved_job_id,
        "replay_ok": True,
        "history_events": len(history),
        "event_count": len(events),
        "event_source": event_sources.get("selected"),
        "event_sources": event_sources,
        "tool_result_file_count": len(tool_result_files),
        "planner_stream_file_count": len(planner_stream_files),
        "validator_rejections": len(validator_rejections),
        "validator_rejections_preview": _bounded(validator_rejections),
        "validator_results_recomputed": _bounded(recomputed_validations),
        "candidate_actions_recomputed": _bounded(
            evidence_contract.get("candidate_next_actions")
            if isinstance(evidence_contract.get("candidate_next_actions"), list)
            else []
        ),
        "candidate_validator_mismatches": _bounded(candidate_mismatches),
        "first_divergence": first_divergence,
        "evidence_coverage": _bounded(
            evidence_contract.get("evidence_coverage")
            if isinstance(evidence_contract.get("evidence_coverage"), dict)
            else {}
        ),
        "runtime_loop_artifact_audit": _runtime_loop_artifact_audit(
            state=state,
            events=events,
            prompt_files=prompt_files,
            planner_stream_files=planner_stream_files,
            tool_result_files=tool_result_files,
            target_tool=str(target_tool or ""),
            require_full_loop=require_full_loop,
        ),
        "suspected_loop": bool(repeated_invalid_decisions),
        "repeated_invalid_decisions": _bounded(repeated_invalid_decisions),
    }
    if target_tool:
        report["target_tool_coverage"] = target_tool_coverage_from_runtime_artifacts(
            history,
            events,
            target_tool,
        )
    return _json_roundtrip(report)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay an agentic planner job offline.")
    parser.add_argument("--job-id", default="", help="Agent job id to resolve through configured job storage.")
    parser.add_argument("--job-root", default="", help="Absolute or relative path to a persisted job root.")
    parser.add_argument("--target-tool", default="", help="Optional planner-internal tool that must be covered after planner turn.")
    parser.add_argument("--require-full-loop", action="store_true", help="Require full 3571/3572 agentic loop artifacts.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = replay_loop_job(
        job_id=args.job_id or None,
        job_root=args.job_root or None,
        target_tool=args.target_tool or None,
        require_full_loop=args.require_full_loop,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
