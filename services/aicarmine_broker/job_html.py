"""HTML rendering for agent job dashboards."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .job_store import agent_job_root, compact_agent_status, load_agent_job_state, read_agent_events, read_json


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _path_inside_root(root: Path, path_value: Any) -> Path | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        resolved = path.resolve()
        root_resolved = root.resolve()
    except Exception:
        return None
    if resolved == root_resolved or root_resolved in resolved.parents:
        return resolved
    return None


def _read_job_artifact_json(root: Path, path_value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _path_inside_root(root, path_value)
    if path is None:
        return {}, {"raw_payload_available": False, "error": "artifact_outside_job_root_or_missing"}
    data = read_json(path, {})
    if isinstance(data, dict):
        return data, {"raw_payload_available": True, "artifact": str(path)}
    return {}, {"raw_payload_available": False, "artifact": str(path), "error": "artifact_json_unavailable"}


def _contains_preview_only(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in {"content_preview", "text_preview", "unified_diff_preview", "structured_operations_preview", "preview_only"}:
                return True
            if _contains_preview_only(item):
                return True
    if isinstance(value, list):
        return any(_contains_preview_only(item) for item in value)
    return False


def _prompt_window_item_violations(item: dict[str, Any], *, prefix: str) -> list[str]:
    required = (
        "document_id", "section", "window_start", "window_end", "full_chars",
        "window_chars", "complete", "has_more_before", "has_more_after",
        "sha256", "window_sha256", "text",
    )
    return [
        f"{prefix}_missing_{key}"
        for key in required
        if key not in item or item.get(key) in (None, "")
    ]


def _tool_payload_audit(compact_payload: dict[str, Any], raw_payload: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    tool = str(compact_payload.get("tool") or raw_payload.get("tool") or "")
    raw_available = bool(raw_payload)
    if _contains_preview_only(compact_payload):
        violations.append("preview_only_violation")
    if compact_payload.get("artifact") and raw_available:
        useful_keys = [
            key for key in compact_payload
            if key not in {"tool", "ok", "summary", "artifact", "cache_key", "cache_hit"}
        ]
        if not useful_keys:
            violations.append("artifact_only_violation")
    if tool == "planner_scratchpad_read" and str(compact_payload.get("mode") or "") == "prompt_context_window":
        compact_items = compact_payload.get("items") if isinstance(compact_payload.get("items"), list) else []
        raw_items = raw_payload.get("items") if isinstance(raw_payload.get("items"), list) else []
        if not compact_items and raw_items:
            violations.append("metadata_only_violation")
        for index, item in enumerate(compact_items):
            if isinstance(item, dict):
                violations.extend(_prompt_window_item_violations(item, prefix=f"compact_item_{index}"))
        required_keys = {
            "document_id", "section", "window_start", "window_end", "full_chars",
            "window_chars", "complete", "has_more_before", "has_more_after",
            "sha256", "window_sha256", "text",
        }
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                continue
            compact_item = compact_items[index] if index < len(compact_items) and isinstance(compact_items[index], dict) else {}
            for key in required_keys:
                if key in raw_item and key not in compact_item:
                    violations.append(f"raw_field_missing_in_compact:{key}")
    if tool == "repo_propose_code_edit":
        edit_kind = str(compact_payload.get("edit_kind") or raw_payload.get("edit_kind") or "")
        if edit_kind == "unified_diff":
            raw_diff = raw_payload.get("unified_diff")
            if isinstance(raw_diff, str) and raw_diff and compact_payload.get("unified_diff") != raw_diff:
                violations.append("unified_diff_missing_or_changed_in_compact")
        if edit_kind == "structured_edit":
            raw_ops = raw_payload.get("structured_operations")
            if raw_ops not in (None, "", [], {}) and compact_payload.get("structured_operations") != raw_ops:
                violations.append("structured_operations_missing_or_changed_in_compact")
    violations = list(dict.fromkeys(violations))
    return {
        "raw_payload_available": raw_available,
        "compact_payload_complete": not violations,
        "metadata_only_violation": "metadata_only_violation" in violations,
        "preview_only_violation": "preview_only_violation" in violations,
        "artifact_only_violation": "artifact_only_violation" in violations,
        "violations": violations,
    }


def _step_prompt_capture(root: Path, step: int) -> dict[str, Any]:
    path = root / "planner-prompts" / f"step-{int(step):03d}-planner-payload.json"
    data = read_json(path, {})
    if not isinstance(data, dict) or not data:
        return {"available": False, "expected_path": str(path)}
    user_payload = data.get("user_payload") if isinstance(data.get("user_payload"), dict) else {}
    optional = user_payload.get("optional_context") if isinstance(user_payload.get("optional_context"), dict) else {}
    evidence = user_payload.get("evidence_contract") if isinstance(user_payload.get("evidence_contract"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "planner_url": data.get("planner_url"),
        "planner_model": data.get("planner_model"),
        "num_ctx_effective": data.get("num_ctx_effective"),
        "prompt_budget_report": data.get("prompt_budget_report"),
        "prompt_sent_to_11434": data.get("planner_payload"),
        "required_working_set": user_payload.get("required_working_set"),
        "intrinsic_context": optional.get("intrinsic_context"),
        "candidate_next_actions": evidence.get("candidate_next_actions"),
        "evidence_contract": evidence,
        "planner_user_payload": user_payload,
    }


def _step_stream_payload(root: Path, step: int) -> dict[str, Any]:
    stream_dir = root / "planner-stream"
    stem = stream_dir / f"step-{int(step):03d}"
    return {
        "content": _read_text_if_exists(stem.with_suffix(".content.txt")),
        "all": _read_text_if_exists(stem.with_suffix(".all.txt")),
        "raw_ndjson": _read_text_if_exists(stem.with_suffix(".raw.ndjson")),
    }


def agent_job_ia_view_payload(job_id: str) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "job_id": job_id, "error": "job_not_found"}
    root = agent_job_root(job_id)
    events = read_agent_events(job_id, 5000)
    event_count_before = len(events)
    steps: dict[int, dict[str, Any]] = {}
    for event in events:
        try:
            step = int(event.get("step") or 0)
        except (TypeError, ValueError):
            step = 0
        row = steps.setdefault(step, {"step": step, "events": []})
        row["events"].append({
            "time": event.get("time") or event.get("ts"),
            "event_type": event.get("event_type"),
            "message": event.get("message"),
        })
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        if event_type == "planner_request_started":
            row["planner_request_started"] = payload
            row["prompt_capture"] = _step_prompt_capture(root, step)
        elif event_type == "planner_decision":
            row["planner_decision"] = payload
            row["planner_stream"] = _step_stream_payload(root, step)
        elif event_type == "planner_decision_rejected":
            row["validator_guard"] = payload
        elif event_type == "tool_start":
            row["tool_start"] = payload
        elif event_type == "tool_result":
            raw_payload, raw_meta = _read_job_artifact_json(root, payload.get("artifact"))
            row["history_tool_result_fed_back_to_planner"] = payload
            row["raw_tool_result_rehydrated"] = raw_payload
            row["payload_audit"] = {**raw_meta, **_tool_payload_audit(payload, raw_payload)}
    final_json = read_json(root / "final.json", {})
    terminal_payload = {}
    if isinstance(final_json, dict) and isinstance(final_json.get("tool_context_for_30b"), dict):
        terminal_payload = final_json["tool_context_for_30b"]
    event_count_after = len(read_agent_events(job_id, 5000))
    return {
        "ok": True,
        "schema": "aicarmine_ia_live_control_view.v1",
        "read_only": True,
        "surface": "3572_operator_dashboard_only",
        "job": {
            "job_id": job_id,
            "status": state.get("status"),
            "goal": state.get("goal"),
            "current_step": state.get("current_step"),
            "workspace": state.get("workspace"),
        },
        "mutation_check": {
            "event_count_before": event_count_before,
            "event_count_after": event_count_after,
            "event_count_changed": event_count_before != event_count_after,
        },
        "steps": [steps[key] for key in sorted(steps)],
        "openwebui_30b_payload": terminal_payload,
    }


def agent_job_ia_view_html(job_id: str) -> str:
    payload = agent_job_ia_view_payload(job_id)
    if not payload.get("ok"):
        return f'<html><body><h1>Job not found</h1><pre>{html.escape(_json_pretty(payload))}</pre></body></html>'
    cards: list[str] = []
    all_steps = [step for step in (payload.get("steps") or []) if isinstance(step, dict)]
    current_step_number = (payload.get("job") or {}).get("current_step")
    current_step = None
    try:
        wanted_step = int(current_step_number or 0)
    except (TypeError, ValueError):
        wanted_step = 0
    if wanted_step:
        for step in all_steps:
            try:
                if int(step.get("step") or 0) == wanted_step:
                    current_step = step
                    break
            except (TypeError, ValueError):
                continue
    if current_step is None and all_steps:
        current_step = all_steps[-1]
    if isinstance(current_step, dict):
        sections = [
            ("Prompt Sent To 11434", current_step.get("prompt_capture")),
            ("History/Tool Result Fed Back To Planner", current_step.get("history_tool_result_fed_back_to_planner")),
            ("Raw Tool Result / Rehydrated", current_step.get("raw_tool_result_rehydrated")),
            ("Validator Guard / Rejection", current_step.get("validator_guard")),
            ("Planner Decision / Stream", {"planner_decision": current_step.get("planner_decision"), "planner_stream": current_step.get("planner_stream")}),
        ]
        body = "".join(
            f"<h3>{html.escape(title)}</h3><pre>{html.escape(_json_pretty(value))}</pre>"
            for title, value in sections
            if value not in (None, "", [], {})
        )
        audit = current_step.get("payload_audit")
        if isinstance(audit, dict):
            css = "audit-bad" if not audit.get("compact_payload_complete") else "audit-ok"
            body = f"<div class='{css}'><b>Payload audit</b><pre>{html.escape(_json_pretty(audit))}</pre></div>" + body
        cards.append(f"<div class='card'><h2>Current Step {html.escape(str(current_step.get('step')))}</h2>{body}</div>")
    else:
        cards.append("<div class='card'><h2>Current Step</h2><p>No planner step is available yet.</p></div>")
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AI-Carmine IA View {html.escape(job_id)}</title>
<meta http-equiv="refresh" content="2">
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
.audit-ok {{ border-left: 4px solid #45a75a; padding-left: 10px; }}
.audit-bad {{ border-left: 4px solid #d15b5b; padding-left: 10px; }}
</style>
</head>
<body>
<div class="card">
  <div class="status">IA Live Control View - {html.escape(job_id)}</div>
  <p><b>Status:</b> {html.escape(str((payload.get('job') or {}).get('status') or ''))}</p>
  <p><b>Goal:</b> {html.escape(str((payload.get('job') or {}).get('goal') or ''))}</p>
  <p><b>Current step:</b> {html.escape(str((payload.get('job') or {}).get('current_step') or ''))}</p>
  <p>Historical steps are kept in the complete JSON view only.</p>
  <p><a href="/jobs/{html.escape(job_id)}">dashboard</a> Â· <a href="/jobs/{html.escape(job_id)}/ia-view.json">ia-view.json</a></p>
  <pre>{html.escape(_json_pretty(payload.get('mutation_check') or {}))}</pre>
</div>
{''.join(cards)}
<div class="card">
  <h2>OpenWebUI 30B Payload</h2>
  <pre>{html.escape(_json_pretty(payload.get("openwebui_30b_payload") or {}))}</pre>
</div>
</body>
</html>"""


def agent_job_html(job_id: str) -> str:
    status = compact_agent_status(job_id, include_events=True)
    if not status.get('ok'):
        return f'<html><body><h1>Job not found</h1><pre>{html.escape(json.dumps(status, ensure_ascii=False, indent=2))}</pre></body></html>'
    events = read_agent_events(job_id, 500)
    rows = []
    for ev in events:
        rows.append(f"<tr><td>{html.escape(str(ev.get('time') or ev.get('ts') or ''))}</td><td>{html.escape(str(ev.get('step') or ''))}</td><td>{html.escape(str(ev.get('event_type') or ''))}</td><td><pre>{html.escape(str(ev.get('message') or ''))}</pre></td></tr>")
    final_summary = html.escape(str(status.get('final_summary') or ''))
    planner_thinking_text = ''
    planner_content_text = ''
    planner_all_text = ''
    planner_stream_dir = agent_job_root(job_id) / "planner-stream"
    thinking_files = sorted(planner_stream_dir.glob('step-*.thinking.txt'))
    content_files = sorted(planner_stream_dir.glob('step-*.content.txt'))
    all_files = sorted(planner_stream_dir.glob('step-*.all.txt'))
    if thinking_files:
        planner_thinking_text = thinking_files[-1].read_text(encoding='utf-8', errors='replace')[-20000:]
    if content_files:
        planner_content_text = content_files[-1].read_text(encoding='utf-8', errors='replace')[-12000:]
    if all_files:
        planner_all_text = all_files[-1].read_text(encoding='utf-8', errors='replace')[-20000:]
    planner_thinking_html = html.escape(planner_thinking_text)
    planner_content_html = html.escape(planner_content_text)
    planner_all_html = html.escape(planner_all_text)
    return f"""<!doctype html>\n<html>\n<head>\n<meta charset="utf-8">\n<title>AI-Carmine Agent Job {html.escape(job_id)}</title>\n<meta http-equiv="refresh" content="2">\n<style>\nbody {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}\na {{ color: #8fd3ff; }}\n.card {{ border: 1px solid #444; border-radius: 10px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}\ntable {{ border-collapse: collapse; width: 100%; }}\ntd, th {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}\npre {{ white-space: pre-wrap; margin: 0; }}\n.status {{ font-size: 20px; font-weight: 700; }}\n</style>\n</head>\n<body>\n<div class="card">\n  <div class="status">Job {html.escape(job_id)} â€” {html.escape(str(status.get('status')))}</div>\n  <p><b>Goal:</b> {html.escape(str(status.get('goal') or ''))}</p>\n  <p><b>Workspace:</b> {html.escape(str(status.get('workspace') or ''))}</p>\n  <p><a href="/jobs/{html.escape(job_id)}/json">JSON compatto</a> Â· <a href="/jobs/{html.escape(job_id)}/final.json">final.json completo</a> Â· <a href="/jobs/{html.escape(job_id)}/final.md">final.md completo</a> Â· <a href="/jobs/{html.escape(job_id)}/events">events.ndjson</a> Â· <a href="/jobs/{html.escape(job_id)}/ia-view">IA live control view</a> Â· <a href="/jobs/{html.escape(job_id)}/ia-view.json">ia-view.json</a></p>\n</div>\n<div class="card">\n  <h2>Final summary</h2>\n  <pre>{final_summary}</pre>\n</div>\n<div class="card">\n  <h2>Planner thinking / reasoning raw</h2>\n  <p>Mostra solo ciÃ² che 11434 emette nello stream: thinking, reasoning o blocchi &lt;think&gt;...&lt;/think&gt;.</p>\n  <pre>{planner_thinking_html}</pre>\n</div>\n\n<div class="card">\n  <h2>Planner emitted content</h2>\n  <pre>{planner_content_html}</pre>\n</div>\n\n<div class="card">\n  <h2>Planner full raw combined</h2>\n  <p><a href="/jobs/{html.escape(job_id)}/planner-stream">full planner stream</a></p>\n  <pre>{planner_all_html}</pre>\n</div>\n<div class="card">\n  <h2>Events</h2>\n  <table>\n    <thead><tr><th>Time</th><th>Step</th><th>Type</th><th>Message</th></tr></thead>\n    <tbody>{''.join(rows)}</tbody>\n  </table>\n</div>\n</body>\n</html>"""

