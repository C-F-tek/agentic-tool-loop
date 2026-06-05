"""Offline loop replay diagnostics.

This module reads persisted job artifacts and produces a bounded diagnostic
report. It does not dispatch tools, call models, mutate job state, or change
planner/controller gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA = "loop_replay_report.v1"
MAX_PREVIEW_ITEMS = 20

EvidenceBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
Validator = Callable[[str, dict[str, Any], list[dict[str, Any]]], dict[str, Any]]


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        return {"_read_error": "invalid_json", "path": str(path), "error": str(exc)}
    except OSError as exc:
        return {"_read_error": "read_failed", "path": str(path), "error": str(exc)}


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return rows
    except OSError as exc:
        return [{"_read_error": "read_failed", "path": str(path), "error": str(exc)}]
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            rows.append({"_read_error": "invalid_ndjson_line", "line_preview": text[:500]})
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


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

    return planner.validate_planner_decision_against_evidence(goal, decision, history)


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


def replay_loop_job(
    *,
    job_id: str | None = None,
    job_root: str | Path | None = None,
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
    events = _read_ndjson(root / "events.ndjson")
    tool_result_files = sorted((root / "tool-results").glob("*.json")) if (root / "tool-results").exists() else []
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
        "suspected_loop": bool(repeated_invalid_decisions),
        "repeated_invalid_decisions": _bounded(repeated_invalid_decisions),
    }
    return _json_roundtrip(report)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay an agentic planner job offline.")
    parser.add_argument("--job-id", default="", help="Agent job id to resolve through configured job storage.")
    parser.add_argument("--job-root", default="", help="Absolute or relative path to a persisted job root.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = replay_loop_job(
        job_id=args.job_id or None,
        job_root=args.job_root or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
