"""HTML rendering for agent job dashboards."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .job_html_assets import BASE_CSS, BASE_JS, render_page_shell, render_json_page, render_json_section, render_status_badge, render_metric_grid, render_pre_block, render_section_link, render_toolbar, render_job_nav, render_active_job_panel
from .job_store import agent_job_root, compact_agent_status, list_agent_jobs, load_agent_job_state, read_agent_events, read_json


IA_VIEW_STEP_STRIP_LIMIT = 24
HTML_PRETTY_TEXT_LIMIT = 300_000


def _safe_text(value: Any,  limit: int = 500) -> str:
    try:
        text = str(value)
    except Exception as exc:
        return f"<unstringifiable:{type(exc).__name__}>"
    return text[:limit] + (f"... <truncated {len(text) - limit} chars>" if len(text) > limit else "")


def _clip_text(text: str,  limit: int = HTML_PRETTY_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... <truncated {len(text) - limit} chars>"


def _json_pretty(value: Any,  max_chars: int = HTML_PRETTY_TEXT_LIMIT) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        text = json.dumps(
            {
                "schema": "job_html_json_diagnostic.v1",
                "diagnostic_only": True,
                "reason": "json_serialization_failed",
                "error_type": type(exc).__name__,
                "error": _safe_text(exc, limit=1000),
                "value_type": type(value).__name__,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    return _clip_text(text, limit=max(0, int(max_chars or 0)))


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _planner_stream_frames(raw_ndjson: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for line in str(raw_ndjson or "").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            frame = json.loads(text)
        except Exception:
            continue
        if isinstance(frame, dict):
            frames.append(frame)
    return frames


def _planner_stream_native_summary(raw_ndjson: str) -> dict[str, Any]:
    frames = _planner_stream_frames(raw_ndjson)
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    native_tool_calls: list[Any] = []
    done_meta: dict[str, Any] = {}
    for frame in frames:
        message = frame.get("message") if isinstance(frame.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str) and content:
            content_parts.append(content)
        response_text = frame.get("response")
        if isinstance(response_text, str) and response_text:
            content_parts.append(response_text)
        for key in ("thinking", "reasoning"):
            value = frame.get(key)
            if isinstance(value, str) and value:
                reasoning_parts.append(value)
            message_value = message.get(key)
            if isinstance(message_value, str) and message_value:
                reasoning_parts.append(message_value)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            native_tool_calls.extend(tool_calls)
        if frame.get("done") is True:
            for key in (
                "model", "done", "done_reason", "total_duration", "load_duration",
                "prompt_eval_count", "prompt_eval_duration", "eval_count",
                "eval_duration",
            ):
                if frame.get(key) not in (None, "", [], {}):
                    done_meta[key] = frame.get(key)
    return {
        "available": bool(frames),
        "frame_count": len(frames),
        "assistant_content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts),
        "native_tool_calls": native_tool_calls,
        "native_tool_call_count": len(native_tool_calls),
        "done_meta": done_meta,
        "raw_ndjson": raw_ndjson,
    }


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


def _prompt_window_item_violations(item: dict[str, Any],  prefix: str) -> list[str]:
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
    raw_ndjson = _read_text_if_exists(stem.with_suffix(".raw.ndjson"))
    native_stream = _planner_stream_native_summary(raw_ndjson)
    native_tool_calls = native_stream.get("native_tool_calls")
    native_tool_call_stream = {}
    if isinstance(native_tool_calls, list) and native_tool_calls:
        native_tool_call_stream = {
            "source": "message.tool_calls",
            "native_tool_call_count": len(native_tool_calls),
            "native_tool_calls": native_tool_calls,
        }
    return {
        "content": _read_text_if_exists(stem.with_suffix(".content.txt")),
        "all": _read_text_if_exists(stem.with_suffix(".all.txt")),
        "raw_ndjson": raw_ndjson,
        "native_stream": native_stream,
        "native_tool_call_stream": native_tool_call_stream,
    }


def _latest_planner_step(root: Path) -> int:
    steps: list[int] = []
    for folder, pattern in (
        (root / "planner-prompts", "step-*-planner-payload.json"),
        (root / "planner-stream", "step-*.*"),
    ):
        for path in folder.glob(pattern):
            parts = path.name.split("-")
            if len(parts) < 2:
                continue
            try:
                steps.append(int(parts[1].split(".")[0]))
            except (TypeError, ValueError):
                continue
    return max(steps) if steps else 0


def _latest_planner_prompt_capture(root: Path, step: int = 0) -> dict[str, Any]:
    if step > 0:
        return _step_prompt_capture(root, step)
    latest = _latest_planner_step(root)
    return _step_prompt_capture(root, latest) if latest else {}


def _planner_stream_files_for_step(root: Path, step: int) -> list[Path]:
    stream_dir = root / "planner-stream"
    return sorted(stream_dir.glob(f"step-{int(step):03d}.*"))


def _planner_stream_combined_text(root: Path, step: int = 0) -> str:
    if step <= 0:
        step = _latest_planner_step(root)
    parts: list[str] = []
    for path in _planner_stream_files_for_step(root, step):
        parts.append(f"\n\n===== {path.name} =====\n")
        parts.append(_read_text_if_exists(path))
    return "".join(parts).strip()


def _planner_stream_display(root: Path, step: int = 0) -> dict[str, Any]:
    if step <= 0:
        step = _latest_planner_step(root)
    if step <= 0:
        return {
            "step": 0,
            "thinking": "",
            "content": "",
            "combined": "",
            "native_stream": {"available": False},
        }
    stream_dir = root / "planner-stream"
    stem = stream_dir / f"step-{int(step):03d}"
    raw_ndjson = _read_text_if_exists(stem.with_suffix(".raw.ndjson"))
    native_stream = _planner_stream_native_summary(raw_ndjson)
    thinking = _read_text_if_exists(stem.with_suffix(".thinking.txt"))
    content = _read_text_if_exists(stem.with_suffix(".content.txt"))
    combined = _read_text_if_exists(stem.with_suffix(".all.txt"))
    base = _read_text_if_exists(stem.with_suffix(".txt"))
    if not thinking:
        thinking = str(native_stream.get("reasoning") or "")
    if not content:
        native_content = str(native_stream.get("assistant_content") or "")
        native_tool_calls = native_stream.get("native_tool_calls")
        if native_content:
            content = native_content
        elif native_tool_calls:
            content = _json_pretty({
                "source": "message.tool_calls",
                "native_tool_calls": native_tool_calls,
            })
        elif native_stream.get("available"):
            content = _json_pretty({
                "source": "planner-stream raw_ndjson",
                "assistant_content": "",
                "native_tool_calls": [],
                "done_meta": native_stream.get("done_meta"),
            })
    combined = _planner_stream_combined_text(root, step) or combined or base
    return {
        "step": step,
        "thinking": thinking,
        "content": content,
        "combined": combined,
        "native_stream": native_stream,
    }


def agent_job_planner_stream_text(job_id: str) -> str:
    root = agent_job_root(job_id)
    stream_dir = root / "planner-stream"
    files = sorted(stream_dir.glob("step-*.*"))
    if not files:
        return ""
    steps: list[int] = []
    for path in files:
        try:
            steps.append(int(path.name.split("-")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    parts: list[str] = []
    for step in sorted(set(steps)):
        display = _planner_stream_display(root, step)
        native_summary = dict(display.get("native_stream") or {})
        native_summary.pop("raw_ndjson", None)
        parts.append(f"\n\n===== step-{step:03d} native stream summary =====\n")
        parts.append(_json_pretty(native_summary))
        combined = str(display.get("combined") or "")
        if combined:
            parts.append(f"\n\n===== step-{step:03d} raw files =====\n")
            parts.append(combined)
    return "".join(parts).strip()


def _html_pre(value: Any) -> str:
    """Render a pre-formatted code block with HTML escaping."""
    if isinstance(value, str):
        text = _clip_text(value)
    else:
        text = _json_pretty(value)
    return f"<pre>{html.escape(text)}</pre>"


def _html_page(title: str, body: str,  extra_css: str = "", extra_js: str = "") -> str:
    extra_css_attr = f'<style>{extra_css}</style>' if extra_css else ""
    extra_js_script = f'<script>{extra_js}</script>' if extra_js else ""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
{extra_css_attr}
</head>
<body>
{body}
{extra_js_script}
</body>
</html>"""


def _html_json_page(title: str, payload: Any,  section_url: str = "", max_chars: int = 300_000) -> str:
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<div class="card">
  <h2>{html.escape(title)}</h2>
  <pre>{json_text}</pre>
</div>
"""
    if section_url:
        body += f'<a href="{html.escape(section_url)}">← Back</a>'
    return _html_page(title, body)


def _html_json_section(title: str, payload: Any,  parent_url: str = "", max_chars: int = 300_000) -> str:
    json_text = _json_pretty(payload, max_chars=max_chars)
    body = f"""
<h3>{html.escape(title)}</h3>
<pre>{json_text}</pre>
"""
    if parent_url:
        body += f'<a href="{html.escape(parent_url)}">↑ Parent</a>'
    return body


def _html_status_badge(ok: bool) -> str:
    if ok:
        return '<span class="pill ok">✓ OK</span>'
    elif ok is False:
        return '<span class="pill bad">✗ Failed</span>'
    else:
        return '<span class="pill warn">⚠ Warning</span>'


def _html_metric_grid(metrics: dict[str, Any]) -> str:
    if not metrics:
        return ""
    rows = []
    for key, value in sorted(metrics.items()):
        rows.append(f'<div class="metric-row"><span>{html.escape(key)}</span><b>{html.escape(str(value))}</b></div>')
    return "\n".join(rows)


def _html_pre_block(value: Any, language: str = "json") -> str:
    text = _json_pretty(value) if isinstance(value, (dict, list)) else str(value)
    return f'<pre class="{html.escape(language)}">{text}</pre>'


def _html_section_link(label: str, href: str) -> str:
    return f'<a href="{html.escape(href)}">{html.escape(label)}</a>'


def _html_toolbar(actions: list[tuple[str, str]]) -> str:
    if not actions:
        return ""
    parts = []
    for label, href in actions:
        btn_class = ""
        if "secondary" in str(label).lower():
            btn_class = " secondary"
        parts.append(f'<button class="btn{btn_class}" onclick="location.href=\'{html.escape(href)}\'">{html.escape(label)}</button>')
    return " ".join(parts)


def _html_job_nav(job_id: str) -> str:
    actions = [
        ("job lab", f"{job_id}/planner-lab"),
        ("IA view", f"{job_id}/ia-view"),
        ("events", f"{job_id}/events"),
        ("planner stream", f"{job_id}/planner-stream"),
        ("final json", f"{job_id}/final.json"),
        ("status json", f"{job_id}/json"),
    ]
    return _html_toolbar([(label, href) for label, href in actions])


def _html_active_job_panel(job_id: str, status_text: str) -> str:
    return f"""
<div class="card active-job">
  <div class="shell-header">
    <div>
      <h2 class="shell-title">Active loop</h2>
      <div class="status-line"><span>job</span><b>{html.escape(job_id)}</b><span class="muted">{html.escape(status_text)}</span></div>
    </div>
    <div class="toolbar">
      <button onclick="loadJob(true)">Load</button>
      <button class="secondary" onclick="startPolling()">Poll</button>
      <button class="secondary" onclick="stopPolling()">Stop poll</button>
    </div>
  </div>
  <div class="job-actions">
    {_html_job_nav(job_id)}
  </div>
</div>
"""


def _html_recent_job_card(job_id: str, goal: str, actions: list[tuple[str, str]], status: str = "") -> str:
    status_badge = _html_status_badge(bool(status)) if status else ""
    actions_html = _html_toolbar(actions)
    return f"""
<div class="recent-job">
  <div class="recent-job-head">
    <div>
      <div class="recent-job-id">{html.escape(job_id)}</div>
      <div class="recent-job-goal">{html.escape(goal)}</div>
      {status_badge}
    </div>
    <div class="recent-job-actions">
      {actions_html}
    </div>
  </div>
</div>
"""


def _ia_debug_lanes(
    
    selected_step: dict[str, Any],
    prompt_available: bool,
    stream_available: bool,
    tool_feedback_available: bool,
    terminal_available: bool,
    terminal_included: bool,
    terminal_omitted: bool,
) -> dict[str, Any]:
    validator_guard = selected_step.get("validator_guard") if isinstance(selected_step.get("validator_guard"), dict) else {}
    payload_audit = selected_step.get("payload_audit") if isinstance(selected_step.get("payload_audit"), dict) else {}
    prompt_capture = selected_step.get("prompt_capture") if isinstance(selected_step.get("prompt_capture"), dict) else {}
    compacted = bool(
        prompt_capture.get("capture_compacted")
        or payload_audit.get("compact_payload_complete") is not True and payload_audit not in ({}, None)
    )
    raw_rehydrated = bool(
        selected_step.get("raw_tool_result_rehydrated") not in (None, "", [], {})
        or selected_step.get("raw_tool_results_rehydrated") not in (None, "", [], {})
    )
    return {
        "schema": "aicarmine_ia_view_debug_lanes.v1",
        "diagnostic_only": True,
        "what_planner_saw": {
            "available": bool(prompt_available),
            "source": "planner-prompts/step-XXX-planner-payload.json",
            "heavy_payload_lazy": True,
        },
        "what_validator_rejected": {
            "available": bool(validator_guard),
            "source": "events.ndjson planner_decision_rejected payload",
            "guard_type": validator_guard.get("guard_type") or validator_guard.get("reason"),
        },
        "what_tool_returned": {
            "available": bool(tool_feedback_available),
            "source": "events.ndjson tool_result payload",
            "compact_result_fed_back_to_planner": bool(tool_feedback_available),
        },
        "what_was_compacted": {
            "available": bool(compacted),
            "source": "planner prompt capture / payload audit",
        },
        "what_was_rehydrated": {
            "available": bool(raw_rehydrated or tool_feedback_available),
            "source": "same-job tool-results artifact",
            "raw_payload_loaded_in_heavy_view": bool(raw_rehydrated),
        },
        "what_openwebui_received": {
            "available": bool(terminal_available),
            "source": "final.json tool_context_for_30b",
            "included": bool(terminal_included),
            "omitted_from_light_view": bool(terminal_omitted),
        },
        "planner_stream": {
            "available": bool(stream_available),
            "source": "planner-stream/step-XXX.*",
        },
    }


def _safe_detail_key(value: Any) -> str:
    text = _safe_text(value, limit=200).strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return (cleaned.strip("-") or "detail")[:200]


def _html_detail_block(
    title: str,
    inner_html: str,
    
    open_by_default: bool = False,
    detail_key: str | None = None,
) -> str:
    opened = " open" if open_by_default else ""
    key = _safe_detail_key(detail_key or title)
    return (
        f"<details data-detail-key=\"{html.escape(key)}\"{opened}>"
        f"<summary>{html.escape(title)}</summary>"
        f"{inner_html}</details>"
    )


def _html_details(title: str, value: Any,  open_by_default: bool = False) -> str:
    if value in (None, "", [], {}):
        return ""
    return _html_detail_block(
        title,
        _html_pre(value),
        open_by_default=open_by_default,
        detail_key=title,
    )


def _json_payload_char_count(value: Any) -> int:
    try:
        return len(_json_pretty(value))
    except Exception:
        return len(_safe_text(value, limit=HTML_PRETTY_TEXT_LIMIT))


def _json_preview(value: Any,  max_chars: int = 220) -> str:
    if isinstance(value, dict):
        keys = [_safe_text(key, limit=80) for key in list(value.keys())[:8]]
        suffix = " ..." if len(value) > len(keys) else ""
        return "keys: " + ", ".join(keys) + suffix
    if isinstance(value, list):
        labels = [_json_value_label(item) for item in value[:5]]
        suffix = " ..." if len(value) > len(labels) else ""
        return "items: " + ", ".join(labels) + suffix
    if isinstance(value, str):
        text = value.replace("\r", "\\r").replace("\n", "\\n")
    else:
        text = _safe_text(value, limit=max(max_chars * 2, max_chars))
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _html_json_payload_index(payload: Any,  section_base_url: str, path: str) -> str:
    safe_base = section_base_url.rstrip("/")
    if isinstance(payload, dict):
        rows: list[str] = []
        for key, value in payload.items():
            key_text = str(key)
            key_url = f"{safe_base}/key?key={quote(key_text, safe='')}"
            rows.append(
                "<tr>"
                f"<td><code>{html.escape(key_text)}</code></td>"
                f"<td>{html.escape(_json_value_label(value))}</td>"
                f"<td>{html.escape(str(_json_payload_char_count(value)))}</td>"
                f"<td>{html.escape(_json_preview(value))}</td>"
                "<td>"
                f"{_html_lazy_details('Load structured value', key_url, detail_key=f'{path}.{key_text}')}"
                "</td>"
                "</tr>"
            )
        return (
            "<div class=\"json-index\" data-json-index=\"1\">"
            "<table><thead><tr>"
            "<th>Key</th><th>Type</th><th>Chars</th><th>Preview</th><th>Structured value</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    if isinstance(payload, list):
        preview_rows: list[str] = []
        for index, item in enumerate(payload[:50]):
            key_url = f"{safe_base}/index?index={index}"
            preview_rows.append(
                "<tr>"
                f"<td><code>[{index}]</code></td>"
                f"<td>{html.escape(_json_value_label(item))}</td>"
                f"<td>{html.escape(str(_json_payload_char_count(item)))}</td>"
                f"<td>{html.escape(_json_preview(item))}</td>"
                "<td>"
                f"{_html_lazy_details('Load structured item', key_url, detail_key=f'{path}.{index}')}"
                "</td>"
                "</tr>"
            )
        omitted = len(payload) - 50
        omitted_html = f"<p class=\"muted\">{omitted} additional items omitted from the initial map.</p>" if omitted > 0 else ""
        return (
            "<div class=\"json-index\" data-json-index=\"1\">"
            f"{omitted_html}"
            "<table><thead><tr>"
            "<th>Index</th><th>Type</th><th>Chars</th><th>Preview</th><th>Structured item</th>"
            "</tr></thead><tbody>"
            + "".join(preview_rows)
            + "</tbody></table></div>"
        )
    return _html_json_tree(payload, path=path)


def _html_lazy_details(
    title: str,
    url: str,
    
    open_by_default: bool = False,
    detail_key: str | None = None,
) -> str:
    opened = " open" if open_by_default else ""
    key = _safe_detail_key(detail_key or title)
    safe_url = html.escape(url, quote=True)
    safe_title = html.escape(title)
    return (
        f"<details data-detail-key=\"{html.escape(key)}\" data-lazy-url=\"{safe_url}\"{opened}>"
        f"<summary>{safe_title}</summary>"
        "<div class=\"lazy-content\" data-lazy-loaded=\"0\">"
        "<p class=\"muted\">Open this section to load the full payload.</p>"
        "</div></details>"
    )


def _json_value_label(value: Any) -> str:
    if isinstance(value, dict):
        return f"object, {len(value)} keys"
    if isinstance(value, list):
        return f"array, {len(value)} items"
    if isinstance(value, str):
        return f"string, {len(value)} chars"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return type(value).__name__
    return type(value).__name__


def _html_json_scalar(value: Any) -> str:
    if isinstance(value, bool):
        css = "json-bool-true" if value else "json-bool-false"
        text = "true" if value else "false"
        return f"<span class=\"json-scalar json-bool {css}\">{text}</span>"
    if value is None:
        return "<span class=\"json-scalar json-null\">null</span>"
    if isinstance(value, (int, float)):
        return f"<span class=\"json-scalar json-number\">{html.escape(str(value))}</span>"
    if isinstance(value, str):
        if "\n" not in value and len(value) <= 240:
            return f"<span class=\"json-scalar json-string\">{html.escape(json.dumps(value, ensure_ascii=False))}</span>"
        return _html_pre(value)
    return _html_pre(_json_pretty(value))


def _json_inline_container(value: Any) -> bool:
    if isinstance(value, dict):
        return 0 < len(value) <= 2 and all(not isinstance(item, (dict, list)) for item in value.values())
    if isinstance(value, list):
        return 0 < len(value) <= 2 and all(not isinstance(item, (dict, list)) for item in value)
    return False


def _html_json_inline_container(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(
                "<span class=\"json-inline-pair\">"
                f"<span class=\"json-key\">{html.escape(_safe_text(key, limit=120))}</span>: "
                f"{_html_json_scalar(item)}"
                "</span>"
            )
        return "<span class=\"json-inline-object\">{ " + ", ".join(parts) + " }</span>"
    if isinstance(value, list):
        parts = [_html_json_scalar(item) for item in value]
        return "<span class=\"json-inline-array\">[ " + ", ".join(parts) + " ]</span>"
    return _html_json_scalar(value)


def _decode_structured_json_text(value: str) -> Any:
    text = str(value or "").strip()
    if len(text) < 2 or text[0] not in "{[" or text[-1] not in "}]":
        return None
    try:
        decoded = json.loads(text)
    except Exception:
        return None
    return decoded if isinstance(decoded, (dict, list)) else None


def _html_json_tree(value: Any,  path: str = "root", depth: int = 0, _seen: set[int] | None = None) -> str:
    seen = _seen if _seen is not None else set()
    if isinstance(value, (dict, list)):
        marker = id(value)
        if marker in seen:
            return _html_pre(
                {
                    "schema": "job_html_json_diagnostic.v1",
                    "diagnostic_only": True,
                    "reason": "recursive_value_omitted",
                    "path": path,
                    "value_type": type(value).__name__,
                }
            )
        seen.add(marker)
    if isinstance(value, str):
        decoded = _decode_structured_json_text(value)
        if decoded is not None:
            return (
                "<div class=\"json-decoded\">"
                "<div class=\"json-decoded-label\">decoded JSON string</div>"
                f"{_html_json_tree(decoded, path=f'{path}.__decoded_json', depth=depth, _seen=seen)}"
                "</div>"
            )
    if _json_inline_container(value):
        result = _html_json_inline_container(value)
        if isinstance(value, (dict, list)):
            seen.discard(id(value))
        return result
    if isinstance(value, dict):
        if not value:
            seen.discard(id(value))
            return _html_pre("{}")
        parts: list[str] = ["<div class=\"json-tree json-object\">"]
        for key, item in value.items():
            key_text = _safe_text(key, limit=120)
            item_path = f"{path}.{key_text}"
            if not isinstance(item, (dict, list)) or _json_inline_container(item):
                parts.append(
                    "<div class=\"json-row\">"
                    f"<span class=\"json-key\">{html.escape(key_text)}</span>"
                    f"<span class=\"json-label\">{html.escape(_json_value_label(item))}</span>"
                    f"<span class=\"json-value\">{_html_json_tree(item, path=item_path, depth=depth + 1, _seen=seen)}</span>"
                    "</div>"
                )
                continue
            title = f"{key_text} ({_json_value_label(item)})"
            parts.append(
                _html_detail_block(
                    title,
                    _html_json_tree(item, path=item_path, depth=depth + 1, _seen=seen),
                    open_by_default=depth == 0 and not isinstance(item, (dict, list)),
                    detail_key=item_path,
                )
            )
        parts.append("</div>")
        seen.discard(id(value))
        return "".join(parts)
    if isinstance(value, list):
        if not value:
            seen.discard(id(value))
            return _html_pre("[]")
        parts = ["<div class=\"json-tree json-array\">"]
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, (dict, list)) or _json_inline_container(item):
                parts.append(
                    "<div class=\"json-row\">"
                    f"<span class=\"json-key\">[{index}]</span>"
                    f"<span class=\"json-label\">{html.escape(_json_value_label(item))}</span>"
                    f"<span class=\"json-value\">{_html_json_tree(item, path=item_path, depth=depth + 1, _seen=seen)}</span>"
                    "</div>"
                )
                continue
            title = f"[{index}] ({_json_value_label(item)})"
            parts.append(
                _html_detail_block(
                    title,
                    _html_json_tree(item, path=item_path, depth=depth + 1, _seen=seen),
                    open_by_default=False,
                    detail_key=item_path,
                )
            )
        parts.append("</div>")
        seen.discard(id(value))
        return "".join(parts)
    return _html_json_scalar(value)


def _json_tree_css() -> str:
    return """
.json-tree details { margin-left: 12px; }
.json-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  border-top: 1px solid #2b2b2b;
  padding: 6px 0;
  flex-wrap: wrap;
}
.json-key {
  font-family: Consolas, monospace;
  font-weight: 700;
  color: #9ed0ff;
}
.json-label {
  color: #888;
  font-size: 11px;
}
.json-value {
  min-width: 0;
  overflow-wrap: anywhere;
}
.json-scalar,
.json-inline-object,
.json-inline-array {
  font-family: Consolas, monospace;
  overflow-wrap: anywhere;
}
.json-bool {
  border-radius: 4px;
  padding: 1px 5px;
}
.json-bool-true {
  color: #d7ffde;
  background: #234d2b;
}
.json-bool-false {
  color: #ffdede;
  background: #5a2424;
}
.json-null {
  color: #aaa;
}
.json-number {
  color: #f2d28b;
}
.json-string {
  color: #e4e4e4;
}
.json-decoded {
  border-left: 3px solid #4b7fa8;
  padding-left: 10px;
}
.json-decoded-label {
  color: #9bb8cc;
  font-size: 11px;
  margin: 0 0 6px 0;
  text-transform: uppercase;
}
"""


def _adaptive_dashboard_css() -> str:
    return """
* { box-sizing: border-box; }
html { min-width: 0; }
body { overflow-x: hidden; }
a { overflow-wrap: anywhere; }
.card,
details,
.metric,
.control-panel,
.step-card,
.json-tree,
.json-index {
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.card {
  overflow: hidden;
}
details {
  max-width: 100%;
}
summary {
  overflow-wrap: anywhere;
}
pre {
  max-width: 100%;
  overflow-x: auto;
  overflow-wrap: anywhere;
}
table {
  table-layout: fixed;
}
td,
th {
  overflow-wrap: anywhere;
  word-break: break-word;
}
.adaptive-grid,
.metrics,
.control-grid {
  min-width: 0;
}
.adaptive-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 12px;
  align-items: start;
}
@media (max-width: 760px) {
  body { margin: 10px; }
  td, th { padding: 6px; }
}
"""


def _compact_runtime_debug_for_view(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict) or not packet:
        return {}
    validator = packet.get("validator_result") if isinstance(packet.get("validator_result"), dict) else {}
    evidence = packet.get("evidence_coverage") if isinstance(packet.get("evidence_coverage"), dict) else {}
    required = (
        packet.get("required_next_progress_model")
        if isinstance(packet.get("required_next_progress_model"), dict)
        else {}
    )
    return {
        "phase": packet.get("phase"),
        "step": packet.get("step"),
        "validator_ok": validator.get("ok"),
        "validator_violations": validator.get("violations") or validator.get("violation_codes"),
        "coverage_score": evidence.get("coverage_score"),
        "coverage_score_ready": evidence.get("coverage_score_ready"),
        "final_ready": evidence.get("final_ready"),
        "required_progress_kind": required.get("kind"),
        "candidate_next_actions_count": packet.get("candidate_next_actions_count"),
        "rejected_candidate_actions_count": packet.get("rejected_candidate_actions_count"),
    }


def _compact_validator_guard_for_view(guard: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(guard, dict) or not guard:
        return {}
    keys = (
        "ok", "tool", "guard_type", "reason", "summary", "error", "error_type",
        "rejected_tool", "rejected_action", "blocked_tool", "blocked_by",
        "validation_result", "violations", "violation_codes", "candidate_next_action",
        "required_next_progress_model",
    )
    out = {key: guard.get(key) for key in keys if guard.get(key) not in (None, "", [], {})}
    if "runtime_debug_packet" in guard:
        out["runtime_debug_available"] = True
    return out


def _compact_planner_decision_for_view(decision: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(decision, dict) or not decision:
        return {}
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    return {
        "action": decision.get("action"),
        "tool": decision.get("tool"),
        "reason": decision.get("reason"),
        "native_tool_call": decision.get("native_tool_call"),
        "arguments_keys": sorted(str(key) for key in args.keys())[:20],
    }


def _compact_command_policy_for_view(policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict) or not policy:
        return {}
    return {
        "allowed": policy.get("allowed"),
        "command_class": policy.get("command_class"),
        "reason": policy.get("reason"),
        "cwd_under_repo": policy.get("cwd_under_repo"),
        "side_effect_scope": policy.get("side_effect_scope"),
        "consent_required": policy.get("consent_required"),
        "diagnostic_only": policy.get("diagnostic_only"),
    }


def _compact_search_quality_for_view(quality: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(quality, dict) or not quality:
        return {}
    return {
        "quality": quality.get("quality"),
        "must_retry": quality.get("must_retry"),
        "reason": quality.get("reason"),
        "count": quality.get("count"),
        "truncated": quality.get("truncated"),
        "search_complete": quality.get("search_complete"),
        "unreadable_files": quality.get("unreadable_files"),
        "diagnostic_only": quality.get("diagnostic_only"),
    }


def _step_diagnostics_summary_for_view(step: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(step, dict) or not step:
        return {}
    guard = step.get("validator_guard") if isinstance(step.get("validator_guard"), dict) else {}
    tool_result = (
        step.get("history_tool_result_fed_back_to_planner")
        if isinstance(step.get("history_tool_result_fed_back_to_planner"), dict)
        else {}
    )
    audit = step.get("payload_audit") if isinstance(step.get("payload_audit"), dict) else {}
    runtime_packet = (
        guard.get("runtime_debug_packet")
        if isinstance(guard.get("runtime_debug_packet"), dict)
        else {}
    )
    diagnostics = {
        "runtime_debug": _compact_runtime_debug_for_view(runtime_packet),
        "command_policy": _compact_command_policy_for_view(tool_result.get("command_execution_policy")),
        "search_quality": _compact_search_quality_for_view(tool_result.get("search_quality")),
        "payload_audit": {
            "raw_payload_available": audit.get("raw_payload_available"),
            "compact_payload_complete": audit.get("compact_payload_complete"),
            "violations": audit.get("violations"),
        } if audit else {},
    }
    return {
        key: value
        for key, value in diagnostics.items()
        if value not in ({}, [], "", None)
    }


def _event_step_number(event: dict[str, Any]) -> int:
    try:
        return int(event.get("step") or 0)
    except (TypeError, ValueError):
        return 0


def _latest_event_step(events: list[dict[str, Any]]) -> int:
    steps = [_event_step_number(event) for event in events]
    return max(steps) if steps else 0


def _select_step_events(root: Path, events: list[dict[str, Any]], requested_step: int = 0) -> tuple[int, list[dict[str, Any]]]:
    step = int(requested_step or 0)
    if step <= 0:
        step = _latest_planner_step(root) or _latest_event_step(events)
    return step, [event for event in events if _event_step_number(event) == step]


def _last_payload_for_event(step_events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    for event in reversed(step_events):
        if str(event.get("event_type") or "") != event_type:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            return payload
    return {}


def _payloads_for_event(step_events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for event in step_events:
        if str(event.get("event_type") or "") != event_type:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _step_payload_audit(root: Path, compact_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(compact_payload, dict) or not compact_payload:
        return {
            "raw_payload_available": False,
            "compact_payload_complete": False,
            "violations": ["compact_payload_missing"],
        }
    raw_payload, raw_meta = _read_job_artifact_json(root, compact_payload.get("artifact"))
    return {**raw_meta, **_tool_payload_audit(compact_payload, raw_payload)}


def _status_tone(value: bool | None) -> str:
    if value is True:
        return "ok"
    if value is False:
        return "bad"
    return "warn"


def _html_status_pill(label: str, value: bool | None) -> str:
    return (
        f"<span class=\"status-pill status-pill-{_status_tone(value)}\">"
        f"{html.escape(label)}: {html.escape(str(value))}</span>"
    )


def _step_strip_html(job_id: str, steps: list[dict[str, Any]], current_step: int) -> str:
    if not steps:
        return "<p class=\"muted\">No step index yet.</p>"
    def step_number_for(row: dict[str, Any]) -> int:
        try:
            return int(row.get("step") or 0)
        except (TypeError, ValueError):
            return 0

    visible_steps = list(steps[-IA_VIEW_STEP_STRIP_LIMIT:])
    if current_step and not any(step_number_for(step) == current_step for step in visible_steps if isinstance(step, dict)):
        for step in steps:
            if isinstance(step, dict) and step_number_for(step) == current_step:
                visible_steps = [step] + visible_steps[-max(0, IA_VIEW_STEP_STRIP_LIMIT - 1):]
                break
    parts: list[str] = []
    for step in visible_steps:
        step_number = step_number_for(step)
        events_count = len(step.get("events") or []) if isinstance(step.get("events"), list) else 0
        css = "step-chip active" if step_number == current_step else "step-chip"
        safe_job = html.escape(job_id, quote=True)
        parts.append(
            f"<a class=\"{css}\" href=\"/jobs/{safe_job}/ia-view/section/prompt?step={step_number}\" "
            f"data-step=\"{step_number}\">"
            f"<span>step {html.escape(str(step_number))}</span>"
            f"<b>{html.escape(str(events_count))} events</b>"
            "</a>"
        )
    return "<div class=\"step-strip\">" + "".join(parts) + "</div>"


def _html_control_panel(
    
    title: str,
    role: str,
    available: bool | None,
    priority: int,
    summary: dict[str, Any],
    body_html: str = "",
    lazy_title: str = "",
    lazy_url: str = "",
    detail_key: str = "",
) -> str:
    available_value = "true" if available is True else "false" if available is False else "unknown"
    lazy = (
        _html_lazy_details(lazy_title, lazy_url, detail_key=detail_key or title)
        if lazy_title and lazy_url
        else ""
    )
    return (
        "<section class=\"control-panel\" "
        f"data-control-panel=\"1\" data-role=\"{html.escape(role)}\" "
        f"data-available=\"{available_value}\" data-priority=\"{int(priority)}\">"
        "<div class=\"control-panel-head\">"
        f"<h3>{html.escape(title)}</h3>"
        f"{_html_status_pill('available', available)}"
        "</div>"
        f"{_html_json_tree(summary, path=f'ia.panel.{_safe_detail_key(title)}')}"
        f"{body_html}"
        f"{lazy}"
        "</section>"
    )


def _ia_control_css() -> str:
    return """
.control-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}
.control-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
  gap: 12px;
  align-items: start;
}
.control-panel {
  border: 1px solid #34404a;
  border-radius: 8px;
  padding: 12px;
  background: #171b1f;
  min-width: 0;
}
.control-panel[data-available="false"] {
  opacity: .72;
}
.control-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.control-panel h3 {
  font-size: 15px;
  margin: 0;
}
.status-pill {
  border: 1px solid #46515d;
  border-radius: 999px;
  padding: 2px 7px;
  font-size: 11px;
  white-space: nowrap;
}
.status-pill-ok {
  color: #d8f7dd;
  background: #1d3a24;
}
.status-pill-warn {
  color: #fff0bf;
  background: #463813;
}
.status-pill-bad {
  color: #ffd9d9;
  background: #4b1f1f;
}
.step-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 0 0;
}
.step-chip {
  border: 1px solid #3b4f5c;
  border-radius: 8px;
  padding: 6px 8px;
  background: #14191d;
  color: #d9ecf5;
  text-decoration: none;
}
.step-chip span,
.step-chip b {
  display: block;
}
.step-chip b {
  color: #9ca8af;
  font-size: 11px;
  margin-top: 2px;
}
.step-chip.active {
  border-color: #6fb3e8;
  background: #132535;
}
@media (min-width: 1180px) {
  .control-layout {
    grid-template-columns: minmax(0, 1.25fr) minmax(340px, .75fr);
  }
}
"""


def _dashboard_links(job_id: str) -> str:
    safe_job = html.escape(job_id)
    return (
        "<a href=\"/jobs\">jobs home</a> &middot; "
        f"<a href=\"/jobs/{safe_job}\">dashboard</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/json\">status json</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/final.json\">final json</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/final.md\">final md</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/events\">events</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/planner-stream\">planner stream</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/ia-view\">IA live control view</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/ia-view.json\">IA view json</a> &middot; "
        f"<a href=\"/jobs/{safe_job}/planner-lab\">planner payload lab</a>"
    )


def _html_page(title: str, body_html: str,  refresh_seconds: int = 0, job_id: str | None = None) -> str:
    gpu0_panel = _gpu0_panel_html(job_id) if job_id else ""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
details {{ border-top: 1px solid #333; padding-top: 10px; margin-top: 10px; }}
summary {{ cursor: pointer; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
.muted {{ color: #aaa; }}
  .event-type {{ font-family: Consolas, monospace; }}
  .audit-ok {{ border-left: 4px solid #45a75a; padding-left: 10px; }}
  .audit-bad {{ border-left: 4px solid #d15b5b; padding-left: 10px; }}
  {_adaptive_dashboard_css()}
  {_json_tree_css()}
  {_gpu0_panel_css()}
</style>
{_stateful_refresh_script(refresh_seconds)}
</head>
<body>
{gpu0_panel}
{body_html}
</body>
</html>"""


def _structured_json_page(
    job_id: str,
    title: str,
    payload: Any,
    
    summary: dict[str, Any] | None = None,
    section_base_url: str,
) -> str:
    payload_summary = {
        "payload_type": type(payload).__name__,
        "payload_chars": _json_payload_char_count(payload),
        "top_level": _json_value_label(payload),
    }
    if isinstance(payload, dict):
        payload_summary["top_level_keys"] = list(payload.keys())
    elif isinstance(payload, list):
        payload_summary["items"] = len(payload)
    merged_summary = {**payload_summary, **(summary or {})}
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">{html.escape(title)} - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        "</div>"
    )
    body += (
        "<div class=\"card\"><h2>Summary</h2>"
        f"{_html_json_tree(merged_summary, path='summary')}"
        "</div>"
        "<div class=\"card\"><h2>Structured JSON</h2>"
        "<p class=\"muted\">Top-level map is loaded inline. Full branches are fetched only when opened.</p>"
        f"{_html_json_payload_index(payload, section_base_url=section_base_url, path=title)}"
        f"{_html_lazy_details('Complete structured JSON', f'{section_base_url}/root', detail_key=f'{title}.root')}"
        "</div>"
        "<div class=\"card\"><h2>Raw JSON</h2>"
        "<p class=\"muted\">Raw JSON is an audit fallback and is loaded on demand.</p>"
        f"{_html_lazy_details('Complete raw JSON', f'{section_base_url}/raw', detail_key=f'{title}.raw')}"
        "</div>"
    )
    return _html_page(title, body, job_id=job_id)


def _structured_json_section_html(
    title: str,
    payload: Any,
    section: str,
    
    key: str = "",
    index: int = 0,
) -> str:
    section = str(section or "").strip()
    if section == "raw":
        return _html_pre(payload)
    if section == "root":
        return _html_json_tree(payload, path=f"{title}.root")
    if section == "key":
        if not isinstance(payload, dict):
            return _html_json_tree(
                {"ok": False, "error": "payload_is_not_object", "payload_type": type(payload).__name__},
                path=f"{title}.error",
            )
        if key not in payload:
            return _html_json_tree({"ok": False, "error": "key_not_found", "key": key}, path=f"{title}.error")
        return (
            f"<h3><code>{html.escape(key)}</code></h3>"
            f"{_html_json_tree(payload[key], path=f'{title}.{_safe_detail_key(key)}')}"
        )
    if section == "index":
        if not isinstance(payload, list):
            return _html_json_tree(
                {"ok": False, "error": "payload_is_not_array", "payload_type": type(payload).__name__},
                path=f"{title}.error",
            )
        if index < 0 or index >= len(payload):
            return _html_json_tree({"ok": False, "error": "index_not_found", "index": index}, path=f"{title}.error")
        return (
            f"<h3><code>[{index}]</code></h3>"
            f"{_html_json_tree(payload[index], path=f'{title}.{index}')}"
        )
    return _html_json_tree({"ok": False, "error": "unknown_json_section", "section": section}, path=f"{title}.error")


def agent_job_status_json_view_html(job_id: str) -> str:
    payload = compact_agent_status(job_id, include_events=True)
    return _structured_json_page(
        job_id,
        "Compact Status JSON View",
        payload,
        section_base_url=f"/jobs/{job_id}/json/section",
        summary={
            "ok": payload.get("ok"),
            "status": payload.get("status"),
            "goal": payload.get("goal"),
            "events_tail_count": len(payload.get("events_tail") or []),
        } if isinstance(payload, dict) else None,
    )


def agent_job_status_json_section_html(job_id: str, section: str,  key: str = "", index: int = 0) -> str:
    payload = compact_agent_status(job_id, include_events=True)
    return _structured_json_section_html("Compact Status JSON View", payload, section, key=key, index=index)


def agent_job_final_json_view_html(job_id: str) -> str:
    root = agent_job_root(job_id)
    path = root / "final.json"
    if not path.exists():
        payload: Any = {"ok": False, "job_id": job_id, "error": "final_not_found"}
    else:
        data = read_json(path, {})
        payload = data if isinstance(data, dict) else {"ok": True, "job_id": job_id, "data": data}
    summary = {
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "ok": payload.get("ok") if isinstance(payload, dict) else None,
        "tool_context_for_30b_keys": (
            list(payload.get("tool_context_for_30b", {}).keys())
            if isinstance(payload, dict) and isinstance(payload.get("tool_context_for_30b"), dict)
            else []
        ),
    }
    return _structured_json_page(
        job_id,
        "Final JSON View",
        payload,
        summary=summary,
        section_base_url=f"/jobs/{job_id}/final.json/section",
    )


def agent_job_final_json_section_html(job_id: str, section: str,  key: str = "", index: int = 0) -> str:
    root = agent_job_root(job_id)
    path = root / "final.json"
    if not path.exists():
        payload: Any = {"ok": False, "job_id": job_id, "error": "final_not_found"}
    else:
        data = read_json(path, {})
        payload = data if isinstance(data, dict) else {"ok": True, "job_id": job_id, "data": data}
    return _structured_json_section_html("Final JSON View", payload, section, key=key, index=index)


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Preamble"
    current_lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines or current_title != "Preamble":
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = stripped.lstrip("#").strip() or stripped
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or not sections:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def agent_job_final_markdown_view_html(job_id: str) -> str:
    root = agent_job_root(job_id)
    path = root / "final.md"
    text = _read_text_if_exists(path)
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">Final Markdown View - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        f"<p class=\"muted\">Path: {html.escape(str(path))}</p>"
        "</div>"
    )
    if not text:
        body += "<div class=\"card\"><p>final.md not found or empty.</p></div>"
    else:
        section_html = "".join(
            _html_detail_block(
                title,
                _html_pre(section_text),
                open_by_default=index == 0,
                detail_key=f"final-md.{index}.{title}",
            )
            for index, (title, section_text) in enumerate(_markdown_sections(text))
        )
        body += (
            "<div class=\"card\"><h2>Markdown Sections</h2>"
            f"{section_html}</div>"
            "<div class=\"card\"><h2>Raw Markdown</h2>"
            f"{_html_details('Complete final.md', text)}</div>"
        )
    return _html_page("Final Markdown View", body, job_id=job_id)


def _read_events_ndjson(root: Path) -> tuple[str, list[dict[str, Any]]]:
    raw = _read_text_if_exists(root / "events.ndjson")
    events: list[dict[str, Any]] = []
    for raw_line in raw.splitlines():
        try:
            decoded = json.loads(raw_line)
        except Exception:
            decoded = {"event_type": "raw", "message": raw_line}
        if isinstance(decoded, dict):
            events.append(decoded)
    return raw, events


def agent_job_events_view_html(job_id: str) -> str:
    root = agent_job_root(job_id)
    raw, events = _read_events_ndjson(root)
    by_step: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        step = str(event.get("step") or "job")
        by_step.setdefault(step, []).append(event)
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">Events View - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        f"<p class=\"muted\">events={len(events)}</p>"
        "</div>"
    )
    step_parts: list[str] = []
    for step, step_events in by_step.items():
        rows = []
        for event_index, event in enumerate(step_events):
            payload_html = ""
            if event.get("payload") not in (None, "", [], {}):
                payload_html = _html_lazy_details(
                    "payload",
                    (
                        f"/jobs/{job_id}/events/section/payload"
                        f"?step={quote(str(step), safe='')}&index={event_index}"
                    ),
                    detail_key=f"events.{step}.{event_index}.payload",
                )
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(event.get('time') or event.get('ts') or ''))}</td>"
                f"<td class=\"event-type\">{html.escape(str(event.get('event_type') or ''))}</td>"
                f"<td><pre>{html.escape(str(event.get('message') or ''))}</pre></td>"
                f"<td>{payload_html}</td>"
                "</tr>"
            )
        table = (
            "<table><thead><tr><th>Time</th><th>Type</th><th>Message</th><th>Payload</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        step_parts.append(
            _html_detail_block(
                f"Step {step} ({len(step_events)} events)",
                table,
                open_by_default=False,
                detail_key=f"events.step.{step}",
            )
        )
    body += (
        "<div class=\"card\" data-live-region=\"events-by-step\"><h2>Events By Step</h2>"
        f"{''.join(step_parts) if step_parts else '<p>No events.</p>'}"
        "</div>"
        "<div class=\"card\"><h2>Raw NDJSON</h2>"
        f"{_html_lazy_details('Complete events.ndjson', f'/jobs/{job_id}/events/section/raw', detail_key='events.raw_ndjson')}"
        "</div>"
    )
    return _html_page("Events View", body, refresh_seconds=2, job_id=job_id)


def agent_job_events_section_html(job_id: str, section: str,  step: str = "", index: int = 0) -> str:
    root = agent_job_root(job_id)
    raw, events = _read_events_ndjson(root)
    section = str(section or "").strip()
    if section == "raw":
        return _html_pre(raw)
    if section != "payload":
        return _html_json_tree({"ok": False, "error": "unknown_events_section", "section": section}, path="events.error")
    by_step: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        step_key = str(event.get("step") or "job")
        by_step.setdefault(step_key, []).append(event)
    step_events = by_step.get(str(step or "job")) or []
    if index < 0 or index >= len(step_events):
        return _html_json_tree(
            {"ok": False, "error": "event_payload_not_found", "step": step, "index": index},
            path="events.error",
        )
    payload = step_events[index].get("payload")
    if payload in (None, "", [], {}):
        return _html_json_tree({"ok": False, "error": "event_payload_empty", "step": step, "index": index}, path="events.error")
    return _html_json_tree(payload, path=f"events.{_safe_detail_key(step)}.{index}.payload")


def agent_job_ia_view_json_view_html(job_id: str) -> str:
    payload = agent_job_ia_view_payload(job_id)
    if not isinstance(payload, dict) or not payload.get("ok"):
        return _structured_json_page(job_id, "IA View JSON View", payload)
    steps = [step for step in (payload.get("steps") or []) if isinstance(step, dict)]
    summary_payload = {
        "ok": payload.get("ok"),
        "job": payload.get("job"),
        "steps_count": len(steps),
        "mutation_check": payload.get("mutation_check"),
    }
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">IA View JSON View - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        "</div>"
        "<div class=\"card\"><h2>Summary</h2>"
        f"{_html_json_tree(summary_payload, path='ia_view_summary')}"
        "</div>"
    )
    for step in steps:
        step_id = html.escape(str(step.get("step") or "job"))
        body += (
            f"<div class=\"card step-card\" data-step=\"{step_id}\">"
            f"<h2>Step {step_id}</h2>"
            f"{_html_json_tree(step, path=f'ia_view.steps.{step_id}')}"
            "</div>"
        )
    body += (
        "<div class=\"card\"><h2>OpenWebUI 30B Payload</h2>"
        f"{_html_json_tree(payload.get('openwebui_30b_payload') or {}, path='ia_view.openwebui_30b_payload')}"
        "</div>"
    )
    return _html_page("IA View JSON View", body, job_id=job_id)


def agent_job_planner_stream_view_html(job_id: str) -> str:
    root = agent_job_root(job_id)
    latest_step = _latest_planner_step(root)
    steps: list[int] = []
    for path in sorted((root / "planner-stream").glob("step-*.*")):
        try:
            steps.append(int(path.name.split("-")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">Planner Stream View - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        f"<p class=\"muted\">latest_step={html.escape(str(latest_step))}</p>"
        "</div>"
    )
    step_sections: list[str] = []
    for step in sorted(set(steps)):
        display = _planner_stream_display(root, step)
        native_summary = dict(display.get("native_stream") or {})
        native_summary.pop("raw_ndjson", None)
        inner = (
            _html_details("Native stream summary", native_summary, open_by_default=True)
            + _html_details("Planner emitted content or native tool calls", display.get("content"))
            + _html_details("Planner thinking / reasoning raw", display.get("thinking"))
            + _html_lazy_details(
                "Planner full raw combined",
                f"/jobs/{job_id}/ia-view/section/planner_stream_raw?step={step}",
                detail_key=f"planner-stream.step.{step}.raw",
            )
        )
        step_sections.append(
            _html_detail_block(
                f"Step {step}",
                inner,
                open_by_default=step == latest_step,
                detail_key=f"planner-stream.step.{step}",
            )
        )
    body += (
        "<div class=\"card\" data-live-region=\"planner-stream-steps\"><h2>Planner Stream Steps</h2>"
        f"{''.join(step_sections) if step_sections else '<p>No planner stream files.</p>'}"
        "</div>"
    )
    return _html_page("Planner Stream View", body, refresh_seconds=2, job_id=job_id)



def _stateful_refresh_script(refresh_seconds: int = 0) -> str:
    interval_ms = max(0, int(float(refresh_seconds or 0) * 1000))
    live_script = ""
    if interval_ms > 0:
        live_script = f"""
  var liveTimer = null;
  function findLiveRegion(key) {{
    var found = null;
    document.querySelectorAll("[data-live-region]").forEach(function(el) {{
      if (!found && el.getAttribute("data-live-region") === key) {{
        found = el;
      }}
    }});
    return found;
  }}
  function loadedLazyContent(container) {{
    var loaded = {{}};
    container.querySelectorAll("details[data-lazy-url][data-lazy-loaded='1']").forEach(function(el) {{
      var key = detailKey(el, 0);
      var target = el.querySelector(".lazy-content");
      if (target) {{
        loaded[key] = target.innerHTML;
      }}
    }});
    return loaded;
  }}
  function restoreLoadedLazyContent(container, loaded) {{
    container.querySelectorAll("details[data-lazy-url]").forEach(function(el) {{
      var key = detailKey(el, 0);
      if (!Object.prototype.hasOwnProperty.call(loaded, key)) {{
        return;
      }}
      var target = el.querySelector(".lazy-content");
      if (target) {{
        target.innerHTML = loaded[key];
        el.setAttribute("data-lazy-loaded", "1");
      }}
    }});
  }}
  function replaceLiveRegionsFrom(doc) {{
    var changed = false;
    doc.querySelectorAll("[data-live-region]").forEach(function(fresh) {{
      var key = fresh.getAttribute("data-live-region");
      var current = findLiveRegion(key);
      if (!current) {{
        return;
      }}
      if (current.innerHTML !== fresh.innerHTML) {{
        var loaded = loadedLazyContent(current);
        current.innerHTML = fresh.innerHTML;
        restoreLoadedLazyContent(current, loaded);
        changed = true;
      }}
    }});
    if (changed) {{
      restoreState(false);
    }}
  }}
  function pollLiveRegions() {{
    writeState();
    var url = window.location.pathname + "?_live=" + Date.now();
    fetch(url, {{ cache: "no-store" }})
      .then(function(response) {{ return response.text(); }})
      .then(function(text) {{
        var doc = new DOMParser().parseFromString(text, "text/html");
        replaceLiveRegionsFrom(doc);
      }})
      .catch(function() {{}});
  }}
  document.addEventListener("DOMContentLoaded", function() {{
    if (document.querySelector("[data-live-region]")) {{
      liveTimer = window.setInterval(pollLiveRegions, {interval_ms});
    }}
  }});
"""
    return f"""<script>
(function() {{
  var key = "aicarmine-dashboard-state:" + window.location.pathname;
  function detailKey(el, index) {{
    return el.getAttribute("data-detail-key") || String(index);
  }}
  function readState() {{
    try {{ return JSON.parse(sessionStorage.getItem(key) || "{{}}"); }}
    catch (err) {{ return {{}}; }}
  }}
  function writeState() {{
    var state = readState();
    state.details = {{}};
    document.querySelectorAll("details").forEach(function(el, index) {{
      state.details[detailKey(el, index)] = !!el.open;
    }});
    state.scrollY = window.scrollY || 0;
    sessionStorage.setItem(key, JSON.stringify(state));
  }}
  function bindLazyDetails() {{
    document.querySelectorAll("details[data-lazy-url]").forEach(function(el) {{
      if (el.getAttribute("data-lazy-bound")) {{
        return;
      }}
      el.setAttribute("data-lazy-bound", "1");
      el.addEventListener("toggle", function() {{
        if (!el.open || el.getAttribute("data-lazy-loaded") === "1") {{
          return;
        }}
        var target = el.querySelector(".lazy-content");
        if (!target) {{
          return;
        }}
        target.innerHTML = "<p class=\\"muted\\">Loading...</p>";
        fetch(el.getAttribute("data-lazy-url"), {{ cache: "no-store" }})
          .then(function(response) {{ return response.text(); }})
          .then(function(text) {{
            target.innerHTML = text;
            el.setAttribute("data-lazy-loaded", "1");
            restoreState(false);
          }})
          .catch(function(err) {{
            target.innerHTML = "<pre>lazy load failed: " + String(err) + "</pre>";
          }});
      }});
      if (el.open) {{
        el.dispatchEvent(new Event("toggle"));
      }}
    }});
  }}
  function orderDynamicPanels() {{
    document.querySelectorAll("[data-dynamic-panel-grid]").forEach(function(grid) {{
      Array.prototype.slice.call(grid.children).sort(function(a, b) {{
        var aAvailable = a.getAttribute("data-available") === "true" ? 0 : 1;
        var bAvailable = b.getAttribute("data-available") === "true" ? 0 : 1;
        if (aAvailable !== bAvailable) {{
          return aAvailable - bAvailable;
        }}
        var aPriority = Number(a.getAttribute("data-priority") || "999");
        var bPriority = Number(b.getAttribute("data-priority") || "999");
        return aPriority - bPriority;
      }}).forEach(function(el) {{
        grid.appendChild(el);
      }});
    }});
  }}
  function restoreState(restoreScroll) {{
    var state = readState();
    var details = state.details || {{}};
    document.querySelectorAll("details").forEach(function(el, index) {{
      var k = detailKey(el, index);
      if (Object.prototype.hasOwnProperty.call(details, k)) {{
        el.open = !!details[k];
      }}
      if (!el.getAttribute("data-stateful-bound")) {{
        el.setAttribute("data-stateful-bound", "1");
        el.addEventListener("toggle", writeState);
      }}
    }});
    bindLazyDetails();
    orderDynamicPanels();
    if (restoreScroll !== false && typeof state.scrollY === "number") {{
      window.scrollTo(0, state.scrollY);
    }}
  }}
  window.addEventListener("beforeunload", writeState);
  document.addEventListener("DOMContentLoaded", function() {{
    restoreState(true);
  }});
{live_script}
}})();
</script>"""


def _gpu0_panel_css() -> str:
    return """
.gpu0-corrections-window {
  position: fixed;
  top: 12px;
  right: 12px;
  width: 30vw;
  height: 20vh;
  overflow: auto;
  z-index: 1000;
  border: 1px solid #5d6b7b;
  border-radius: 8px;
  background: #151a20;
  color: #e5edf5;
  box-shadow: 0 8px 24px rgba(0,0,0,.45);
  padding: 10px;
}
.gpu0-corrections-window h2 {
  font-size: 13px;
  margin: 0 0 8px 0;
}
.gpu0-corrections-window pre {
  font-size: 11px;
  line-height: 1.25;
  overflow-wrap: anywhere;
  word-break: break-word;
}
@media (max-width: 900px) {
  .gpu0-corrections-window {
    position: static;
    width: auto;
    height: 220px;
    margin-bottom: 14px;
  }
}
"""


def _contains_gpu0_repair_text(value: Any) -> bool:
    text = str(value or "").lower()
    if not any(marker in text for marker in ("gpu0", "vulkan_gpu0", "vulkan/gpu0")):
        return False
    return any(marker in text for marker in ("repair", "repaired", "correz", "correction"))


def _collect_gpu0_repair_nodes(value: Any,  path: str = "root") -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            item_path = f"{path}.{key_text}"
            key_lower = key_text.lower()
            if (
                ("gpu0" in key_lower or "vulkan_repair" in key_lower or "vulkan_gpu0" in key_lower)
                and item not in (None, "", [], {}, False)
            ):
                nodes.append({"path": item_path, "value": item})
            if _contains_gpu0_repair_text(key_text) and item not in (None, "", [], {}, False):
                nodes.append({"path": item_path, "value": item})
            if not isinstance(item, (dict, list)) and _contains_gpu0_repair_text(item):
                nodes.append({"path": item_path, "value": item})
            nodes.extend(_collect_gpu0_repair_nodes(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, (dict, list)) and _contains_gpu0_repair_text(item):
                nodes.append({"path": item_path, "value": item})
            nodes.extend(_collect_gpu0_repair_nodes(item, path=item_path))
    elif _contains_gpu0_repair_text(value):
        nodes.append({"path": path, "value": value})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes:
        key = _json_pretty(node)
        if key not in seen:
            seen.add(key)
            deduped.append(node)
    return deduped


def _gpu0_corrections_payload(job_id: str) -> dict[str, Any]:
    root = agent_job_root(job_id)
    _, events = _read_events_ndjson(root)
    repair_events: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type") or "")
        message = str(event.get("message") or "")
        payload = event.get("payload")
        payload_signals = _collect_gpu0_repair_nodes(payload, path="payload")
        if (
            _contains_gpu0_repair_text(event_type)
            or _contains_gpu0_repair_text(message)
            or bool(payload_signals)
        ):
            repair_events.append({
                "step": event.get("step"),
                "time": event.get("time") or event.get("ts"),
                "event_type": event_type,
                "message": message,
                "payload": payload,
                "payload_gpu0_repair_signals": payload_signals,
            })
    final_json = read_json(root / "final.json", {})
    final_repair_signals = _collect_gpu0_repair_nodes(final_json)
    return {
        "schema": "aicarmine_gpu0_corrections_overlay.v1",
        "job_id": job_id,
        "source": "events.ndjson + final.json",
        "has_gpu0_corrections": bool(repair_events or final_repair_signals),
        "repair_event_count": len(repair_events),
        "final_repair_signal_count": len(final_repair_signals),
        "repair_events": repair_events,
        "final_repair_signals": final_repair_signals,
    }


def _gpu0_panel_html(job_id: str) -> str:
    payload = _gpu0_corrections_payload(job_id)
    return (
        "<aside class=\"gpu0-corrections-window\" data-live-region=\"gpu0-corrections\">"
        "<h2>GPU0 corrections JSON</h2>"
        f"{_html_pre(payload)}"
        "</aside>"
    )


def agent_jobs_index_html( limit: int, title: str, refresh_seconds: int) -> str:
    safe_limit = max(1, min(int(limit or 50), 200))
    jobs = list_agent_jobs(limit=safe_limit)
    rows: list[str] = []
    for job in jobs:
        job_id = html.escape(str(job.get("job_id") or ""))
        status = html.escape(str(job.get("status") or ""))
        goal = html.escape(str(job.get("goal") or ""))
        updated = html.escape(str(job.get("updated_at") or ""))
        workspace = html.escape(str(job.get("workspace") or ""))
        rows.append(
            "<tr>"
            f"<td><a href=\"/jobs/{job_id}\">{job_id}</a></td>"
            f"<td>{status}</td>"
            f"<td><pre>{goal}</pre></td>"
            f"<td>{updated}</td>"
            f"<td><pre>{workspace}</pre></td>"
            f"<td><a href=\"/jobs/{job_id}/events\">events</a> &middot; "
            f"<a href=\"/jobs/{job_id}/ia-view\">IA view</a> &middot; "
            f"<a href=\"/jobs/{job_id}/planner-stream\">planner stream</a> &middot; "
            f"<a href=\"/jobs/{job_id}/planner-lab\">planner lab</a></td>"
            "</tr>"
        )
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">{html.escape(title)} Agent Jobs</div>"
        "<p class=\"muted\">Live update aggiorna solo la tabella job, senza ricaricare la pagina intera.</p>"
        "</div>"
        "<div class=\"card\" data-live-region=\"jobs-index-table\">"
        "<table><thead><tr><th>Job</th><th>Status</th><th>Goal</th>"
        "<th>Updated</th><th>Workspace</th><th>Views</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)} Agent Jobs</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
details {{ border-top: 1px solid #333; padding-top: 10px; margin-top: 10px; }}
summary {{ cursor: pointer; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
.muted {{ color: #aaa; }}
{_adaptive_dashboard_css()}
{_json_tree_css()}
</style>
{_stateful_refresh_script(max(2, int(refresh_seconds or 5)))}
</head>
<body>
{body}
</body>
</html>"""


def agent_job_ia_view_payload(job_id: str,  include_heavy: bool = True) -> dict[str, Any]:
    state = load_agent_job_state(job_id)
    if not state:
        return {"ok": False, "job_id": job_id, "error": "job_not_found"}
    root = agent_job_root(job_id)
    events = read_agent_events(job_id, 5000)
    event_count_before = len(events)
    steps: dict[int, dict[str, Any]] = {}
    try:
        current_step_number = int(state.get("current_step") or 0)
    except (TypeError, ValueError):
        current_step_number = 0
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
            if include_heavy or step == current_step_number:
                prompt_capture = _step_prompt_capture(root, step)
                if include_heavy:
                    row["prompt_capture"] = prompt_capture
                else:
                    row["prompt_capture"] = {
                        "available": prompt_capture.get("available"),
                        "planner_url": prompt_capture.get("planner_url"),
                        "planner_model": prompt_capture.get("planner_model"),
                        "num_ctx_effective": prompt_capture.get("num_ctx_effective"),
                        "prompt_budget_report": prompt_capture.get("prompt_budget_report"),
                    }
        elif event_type == "planner_decision":
            row["planner_decision"] = payload
            if include_heavy or step == current_step_number:
                stream_payload = _step_stream_payload(root, step)
                if include_heavy:
                    row["planner_stream"] = stream_payload
                else:
                    native_stream = dict(stream_payload.get("native_stream") or {})
                    native_stream.pop("raw_ndjson", None)
                    row["planner_stream"] = {
                        "native_stream": native_stream,
                        "native_tool_call_stream": stream_payload.get("native_tool_call_stream"),
                    }
        elif event_type == "planner_decision_rejected":
            row["validator_guard"] = payload
        elif event_type == "tool_start":
            row["tool_start"] = payload
        elif event_type == "tool_result":
            tool_feedback = payload if include_heavy else {
                key: value
                for key, value in payload.items()
                if key in {
                    "tool", "ok", "substep", "mode", "kind", "target_file", "edit_kind",
                    "window_start", "window_end", "document_id", "command_class",
                    "policy", "command_execution_policy", "search_quality",
                    "public_payload_lint",
                }
            }
            row.setdefault("history_tool_results_fed_back_to_planner", []).append(tool_feedback)
            row["history_tool_result_fed_back_to_planner"] = tool_feedback
            if include_heavy:
                raw_payload, raw_meta = _read_job_artifact_json(root, payload.get("artifact"))
                payload_audit = {**raw_meta, **_tool_payload_audit(payload, raw_payload)}
                row.setdefault("raw_tool_results_rehydrated", []).append(raw_payload)
                row.setdefault("payload_audits", []).append(payload_audit)
                row["raw_tool_result_rehydrated"] = raw_payload
                row["payload_audit"] = payload_audit
    final_json = read_json(root / "final.json", {})
    terminal_payload = {}
    terminal_context = final_json.get("tool_context_for_30b") if isinstance(final_json, dict) else None
    terminal_available = terminal_context not in (None, "", [], {})
    if include_heavy and terminal_available:
        terminal_payload = terminal_context
    selected_step_number = current_step_number or (max(steps.keys()) if steps else 0)
    selected_row = steps.get(selected_step_number, {})
    prompt_available = bool(
        isinstance(selected_row, dict)
        and isinstance(selected_row.get("prompt_capture"), dict)
        and selected_row["prompt_capture"].get("available")
    )
    stream_available = bool(
        isinstance(selected_row, dict)
        and isinstance(selected_row.get("planner_stream"), dict)
        and (selected_row["planner_stream"].get("native_stream") or selected_row["planner_stream"].get("content"))
    )
    tool_feedback_available = bool(
        isinstance(selected_row, dict)
        and selected_row.get("history_tool_result_fed_back_to_planner") not in (None, "", [], {})
    )
    diagnostics_available = bool(
        isinstance(selected_row, dict)
        and (
            selected_row.get("validator_guard") not in (None, "", [], {})
            or selected_row.get("payload_audit") not in (None, "", [], {})
        )
    )
    terminal_included = bool(include_heavy and terminal_payload)
    terminal_omitted = bool(terminal_available and not include_heavy)
    debug_lanes = _ia_debug_lanes(
        selected_step=selected_row if isinstance(selected_row, dict) else {},
        prompt_available=prompt_available,
        stream_available=stream_available,
        tool_feedback_available=tool_feedback_available,
        terminal_available=terminal_available,
        terminal_included=terminal_included,
        terminal_omitted=terminal_omitted,
    )
    event_count_after = len(read_agent_events(job_id, 5000))
    return {
        "ok": True,
        "schema": "aicarmine_ia_live_control_view.v1",
        "read_only": True,
        "surface": "3572_operator_dashboard_only",
        "selected_step": selected_step_number,
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
        "view_contract": {
            "schema": "aicarmine_ia_view_source_contract.v1",
            "selected_step": selected_step_number,
            "read_only": True,
            "sources": {
                "state": {"source": "job.json", "available": bool(state)},
                "events": {"source": "events.ndjson", "available": True, "count": len(events)},
                "prompt": {"source": "planner-prompts/step-XXX-planner-payload.json", "available": prompt_available},
                "planner_stream": {"source": "planner-stream/step-XXX.*", "available": stream_available},
                "tool_feedback": {"source": "events.ndjson tool_result payload", "available": tool_feedback_available},
                "raw_tool_result": {"source": "same-job tool-results artifact", "available": tool_feedback_available},
                "diagnostics": {"source": "validator guard / payload audit", "available": diagnostics_available},
                "terminal_payload": {"source": "final.json tool_context_for_30b", "available": terminal_available},
            },
        },
        "debug_lanes": debug_lanes,
        "openwebui_30b_payload": terminal_payload,
        "openwebui_30b_payload_available": terminal_available,
        "openwebui_30b_payload_included": terminal_included,
        "openwebui_30b_payload_omitted": terminal_omitted,
    }


def _ia_view_payload_step(payload: dict[str, Any], requested_step: int = 0) -> dict[str, Any]:
    steps = [step for step in (payload.get("steps") or []) if isinstance(step, dict)]
    if requested_step > 0:
        for step in steps:
            try:
                if int(step.get("step") or 0) == requested_step:
                    return step
            except (TypeError, ValueError):
                continue
    if steps:
        return steps[-1]
    return {}


def agent_job_ia_view_section_html(job_id: str, section: str,  step: int = 0) -> str:
    root = agent_job_root(job_id)
    section_name = str(section or "").strip()
    try:
        requested_step = int(step or 0)
    except (TypeError, ValueError):
        requested_step = 0
    if section_name == "prompt":
        payload = _step_prompt_capture(root, requested_step or _latest_planner_step(root))
        return _html_json_tree(payload, path="ia.lazy.prompt")
    if section_name == "planner_stream_raw":
        payload = _step_stream_payload(root, requested_step or _latest_planner_step(root))
        return _html_json_tree(payload, path="ia.lazy.planner_stream_raw")
    if section_name == "events_raw":
        raw, _events = _read_events_ndjson(root)
        return _html_pre(raw)
    events = read_agent_events(job_id, 5000)
    selected_step, step_events = _select_step_events(root, events, requested_step)
    compact_tool_results = _payloads_for_event(step_events, "tool_result")
    compact_tool_result = _last_payload_for_event(step_events, "tool_result")
    validator_guard = _last_payload_for_event(step_events, "planner_decision_rejected")
    if section_name == "compact_tool_result":
        return _html_json_tree(
            {
                "selected_step": selected_step,
                "source": "events.ndjson tool_result payload",
                "payload_count": len(compact_tool_results),
                "payloads": compact_tool_results,
                "payload": compact_tool_result,
            },
            path="ia.lazy.compact_tool_result",
        )
    if section_name == "raw_tool_result":
        raw_results = []
        for compact in compact_tool_results:
            raw_payload_i, raw_meta_i = _read_job_artifact_json(root, compact.get("artifact"))
            raw_results.append({
                "compact": compact,
                "artifact": raw_meta_i,
                "payload": raw_payload_i,
            })
        raw_payload, raw_meta = _read_job_artifact_json(root, compact_tool_result.get("artifact"))
        return _html_json_tree(
            {
                "selected_step": selected_step,
                "source": "same-job tool-results artifact",
                "payload_count": len(raw_results),
                "payloads": raw_results,
                "artifact": raw_meta,
                "payload": raw_payload,
            },
            path="ia.lazy.raw_tool_result",
        )
    if section_name == "payload_audit":
        audits = [
            {
                "compact": compact,
                "audit": _step_payload_audit(root, compact),
            }
            for compact in compact_tool_results
        ]
        return _html_json_tree(
            {
                "selected_step": selected_step,
                "source": "compact event payload + same-job artifact",
                "payload_count": len(audits),
                "audits": audits,
                "audit": _step_payload_audit(root, compact_tool_result),
            },
            path="ia.lazy.payload_audit",
        )
    if section_name == "runtime_debug":
        return _html_json_tree(
            {
                "selected_step": selected_step,
                "source": "planner_decision_rejected event payload",
                "runtime_debug_packet": validator_guard.get("runtime_debug_packet") or {},
            },
            path="ia.lazy.runtime_debug",
        )
    if section_name == "openwebui_payload":
        final_json = read_json(root / "final.json", {})
        terminal_payload = (
            final_json.get("tool_context_for_30b")
            if isinstance(final_json, dict)
            else {}
        )
        return _html_json_tree(
            {
                "source": "final.json tool_context_for_30b",
                "available": terminal_payload not in (None, "", [], {}),
                "payload": terminal_payload or {},
            },
            path="ia.lazy.openwebui_30b_payload",
        )
    return _html_pre({"ok": False, "error": "unknown_ia_view_section", "section": section_name})


def agent_job_ia_view_html(job_id: str) -> str:
    payload = agent_job_ia_view_payload(job_id, include_heavy=False)
    if not payload.get("ok"):
        return f'<html><body><h1>Job not found</h1><pre>{html.escape(_json_pretty(payload))}</pre></body></html>'
    cards: list[str] = []
    all_steps = [step for step in (payload.get("steps") or []) if isinstance(step, dict)]
    steps_omitted_count = max(0, len(all_steps) - min(len(all_steps), IA_VIEW_STEP_STRIP_LIMIT))
    view_truncated_for_operator_page = steps_omitted_count > 0
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
    job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    mutation_check = payload.get("mutation_check") if isinstance(payload.get("mutation_check"), dict) else {}
    debug_lanes = payload.get("debug_lanes") if isinstance(payload.get("debug_lanes"), dict) else {}
    prompt_capture = current_step.get("prompt_capture") if isinstance(current_step, dict) and isinstance(current_step.get("prompt_capture"), dict) else {}
    planner_decision = current_step.get("planner_decision") if isinstance(current_step, dict) and isinstance(current_step.get("planner_decision"), dict) else {}
    planner_stream = current_step.get("planner_stream") if isinstance(current_step, dict) and isinstance(current_step.get("planner_stream"), dict) else {}
    native_stream = planner_stream.get("native_stream") if isinstance(planner_stream.get("native_stream"), dict) else {}
    native_tool_call_stream = (
        planner_stream.get("native_tool_call_stream")
        if isinstance(planner_stream.get("native_tool_call_stream"), dict)
        else {}
    )
    validator_guard = current_step.get("validator_guard") if isinstance(current_step, dict) and isinstance(current_step.get("validator_guard"), dict) else {}
    audit = current_step.get("payload_audit") if isinstance(current_step, dict) and isinstance(current_step.get("payload_audit"), dict) else {}
    tool_result = (
        current_step.get("history_tool_result_fed_back_to_planner")
        if isinstance(current_step, dict) and isinstance(current_step.get("history_tool_result_fed_back_to_planner"), dict)
        else {}
    )
    diagnostics_summary = _step_diagnostics_summary_for_view(current_step or {})
    runtime_debug_packet = (
        validator_guard.get("runtime_debug_packet")
        if isinstance(validator_guard.get("runtime_debug_packet"), dict)
        else {}
    )
    command_policy = (
        tool_result.get("command_execution_policy")
        if isinstance(tool_result.get("command_execution_policy"), dict)
        else {}
    )
    search_quality = (
        tool_result.get("search_quality")
        if isinstance(tool_result.get("search_quality"), dict)
        else {}
    )
    metrics = {
        "step": current_step.get("step") if isinstance(current_step, dict) else None,
        "status": job.get("status"),
        "planner_model": prompt_capture.get("planner_model"),
        "planner_url": prompt_capture.get("planner_url"),
        "num_ctx_effective": prompt_capture.get("num_ctx_effective"),
        "prompt_chars": (prompt_capture.get("prompt_budget_report") or {}).get("total_prompt_chars")
        if isinstance(prompt_capture.get("prompt_budget_report"), dict)
        else None,
        "decision": planner_decision.get("action") or planner_decision.get("tool"),
        "tool": planner_decision.get("tool"),
        "native_tool_calls": native_stream.get("native_tool_call_count"),
        "validator_guard": validator_guard.get("guard_type") or validator_guard.get("reason"),
        "diagnostics": ", ".join(diagnostics_summary.keys()) if diagnostics_summary else None,
        "search_quality": search_quality.get("quality"),
        "command_policy": command_policy.get("command_class"),
        "payload_complete": audit.get("compact_payload_complete"),
        "steps_omitted_count": steps_omitted_count if view_truncated_for_operator_page else None,
        "view_truncated_for_operator_page": view_truncated_for_operator_page if view_truncated_for_operator_page else None,
    }
    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{html.escape(str(key))}</span>"
        f"<b>{html.escape(str(value))}</b>"
        "</div>"
        for key, value in metrics.items()
        if value not in (None, "", [], {})
    )
    if isinstance(current_step, dict):
        current_step_id = current_step.get("step") or 0
        planner_summary = {
            "planner_decision": _compact_planner_decision_for_view(planner_decision),
            "native_stream_summary": {
                key: value
                for key, value in native_stream.items()
                if key != "raw_ndjson"
            },
        }
        planner_output_body = _html_detail_block(
            "Planner Decision / Stream Summary",
            _html_json_tree(planner_summary, path="ia.current.planner_summary"),
            open_by_default=True,
            detail_key="ia.current.planner_summary",
        )
        if native_tool_call_stream:
            planner_output_body += _html_detail_block(
                "Native Tool Calls",
                _html_json_tree(native_tool_call_stream, path="ia.current.native_tool_calls"),
                open_by_default=True,
                detail_key="ia.current.native_tool_calls",
            )
        diagnostics_body = ""
        if diagnostics_summary:
            diagnostics_body += _html_detail_block(
                "Diagnostics Summary",
                _html_json_tree(diagnostics_summary, path="ia.current.diagnostics"),
                open_by_default=True,
                detail_key="ia.current.diagnostics",
            )
        if validator_guard:
            diagnostics_body += _html_detail_block(
                "Validator Guard / Rejection (compact)",
                _html_json_tree(_compact_validator_guard_for_view(validator_guard), path="ia.current.validator_guard"),
                open_by_default=True,
                detail_key="ia.current.validator_guard",
            )
        if runtime_debug_packet:
            diagnostics_body += _html_lazy_details(
                "Runtime Debug Packet",
                f"/jobs/{job_id}/ia-view/section/runtime_debug?step={current_step_id}",
                detail_key="ia.current.runtime_debug",
            )
        diagnostics_body += _html_lazy_details(
            "Payload Audit",
            f"/jobs/{job_id}/ia-view/section/payload_audit?step={current_step_id}",
            detail_key="ia.current.payload_audit",
        )
        panels = [
            _html_control_panel(
                title="Planner Input",
                role="working",
                available=bool(prompt_capture.get("available")),
                priority=10,
                summary={
                    "source": "planner-prompts/step-XXX-planner-payload.json",
                    "step": current_step_id,
                    "planner_model": prompt_capture.get("planner_model"),
                    "planner_url": prompt_capture.get("planner_url"),
                    "num_ctx_effective": prompt_capture.get("num_ctx_effective"),
                    "prompt_chars": (prompt_capture.get("prompt_budget_report") or {}).get("total_prompt_chars")
                    if isinstance(prompt_capture.get("prompt_budget_report"), dict)
                    else None,
                },
                lazy_title="Prompt Sent To 11434",
                lazy_url=f"/jobs/{job_id}/ia-view/section/prompt?step={current_step_id}",
                detail_key="ia.current.prompt_summary",
            ),
            _html_control_panel(
                title="Planner Output",
                role="working",
                available=bool(planner_decision or native_stream),
                priority=20,
                summary={
                    "source": "events.ndjson planner_decision + planner-stream/step-XXX.*",
                    "decision": planner_decision.get("action") or planner_decision.get("tool"),
                    "native_tool_call_count": native_stream.get("native_tool_call_count"),
                    "done_reason": (native_stream.get("done_meta") or {}).get("done_reason")
                    if isinstance(native_stream.get("done_meta"), dict)
                    else None,
                },
                body_html=planner_output_body,
                lazy_title="Planner full raw combined",
                lazy_url=f"/jobs/{job_id}/ia-view/section/planner_stream_raw?step={current_step_id}",
                detail_key="ia.current.planner_stream_raw",
            ),
            _html_control_panel(
                title="Tool Feedback",
                role="working",
                available=bool(tool_result),
                priority=30,
                summary={
                    "source": "events.ndjson tool_result payload",
                    "compact_payload_available": bool(tool_result),
                    "raw_result_available_on_demand": bool(tool_result),
                    "same_step": current_step_id,
                },
                body_html=(
                    _html_lazy_details(
                        "History/Tool Result Fed Back To Planner",
                        f"/jobs/{job_id}/ia-view/section/compact_tool_result?step={current_step_id}",
                        detail_key="ia.current.compact_tool_result",
                    )
                    + _html_lazy_details(
                        "Raw Tool Result / Rehydrated",
                        f"/jobs/{job_id}/ia-view/section/raw_tool_result?step={current_step_id}",
                        detail_key="ia.current.raw_tool_result",
                    )
                    if tool_result else ""
                ),
            ),
            _html_control_panel(
                title="Diagnostics",
                role="diagnostic",
                available=bool(validator_guard or diagnostics_summary or tool_result),
                priority=40,
                summary={
                    "source": "validator guard / runtime debug / payload audit",
                    "validator_guard_available": bool(validator_guard),
                    "runtime_debug_packet_available": bool(runtime_debug_packet),
                    "command_policy_available": bool(command_policy),
                    "search_quality_available": bool(search_quality),
                    "payload_audit_available_on_demand": bool(tool_result),
                },
                body_html=diagnostics_body,
            ),
            _html_control_panel(
                title="Terminal 30B Payload",
                role="terminal",
                available=bool(payload.get("openwebui_30b_payload_available")),
                priority=50,
                summary={
                    "source": "final.json tool_context_for_30b",
                    "available": bool(payload.get("openwebui_30b_payload_available")),
                    "loaded": "on demand",
                },
                lazy_title="Complete terminal payload",
                lazy_url=f"/jobs/{job_id}/ia-view/section/openwebui_payload",
                detail_key="ia.openwebui_30b_payload",
            ),
            _html_control_panel(
                title="Source Contract",
                role="diagnostic",
                available=True,
                priority=60,
                summary=payload.get("view_contract") if isinstance(payload.get("view_contract"), dict) else {},
            ),
            _html_control_panel(
                title="Debug Lanes",
                role="diagnostic",
                available=bool(debug_lanes),
                priority=70,
                summary=debug_lanes,
            ),
        ]
        cards.append(
            "<div class='card' data-live-region='ia-current-step'>"
            f"<h2>Current Step {html.escape(str(current_step_id))}</h2>"
            f"<div class=\"metrics\">{metric_html}</div>"
            "<div class=\"control-layout\">"
            "<div class=\"control-grid\" data-dynamic-panel-grid=\"1\">"
            f"{''.join(panels)}"
            "</div>"
            "</div>"
            "</div>"
        )
    else:
        cards.append("<div class='card' data-live-region='ia-current-step'><h2>Current Step</h2><p>No planner step is available yet.</p></div>")
    step_window_html = ""
    if view_truncated_for_operator_page:
        step_window_html = _html_detail_block(
            "Operator Step Window",
            _html_json_tree(
                {
                    "view_truncated_for_operator_page": True,
                    "total_steps": len(all_steps),
                    "visible_step_chip_limit": IA_VIEW_STEP_STRIP_LIMIT,
                    "steps_omitted_count": steps_omitted_count,
                    "current_step_preserved": bool(current_step),
                    "heavy_payloads_remain_lazy": True,
                },
                path="ia.operator_step_window",
            ),
            detail_key="ia.operator_step_window",
        )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AI-Carmine IA View {html.escape(job_id)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
details {{ border-top: 1px solid #333; padding-top: 10px; margin-top: 10px; }}
summary {{ cursor: pointer; font-weight: 700; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin: 12px 0; }}
.metric {{ border: 1px solid #333; border-radius: 6px; padding: 8px; background: #151515; }}
.metric span {{ display: block; color: #aaa; font-size: 11px; }}
.metric b {{ display: block; margin-top: 4px; overflow-wrap: anywhere; }}
.audit-ok {{ border-left: 4px solid #45a75a; padding-left: 10px; }}
.audit-bad {{ border-left: 4px solid #d15b5b; padding-left: 10px; }}
{_adaptive_dashboard_css()}
{_json_tree_css()}
{_ia_control_css()}
{_gpu0_panel_css()}
</style>
{_stateful_refresh_script(2)}
</head>
<body>
{_gpu0_panel_html(job_id)}
<div class="card" data-live-region="ia-status">
  <div class="status">IA Live Control View - {html.escape(job_id)}</div>
  <div class="metrics">
    <div class="metric"><span>Status</span><b>{html.escape(str(job.get('status') or ''))}</b></div>
    <div class="metric"><span>Current step</span><b>{html.escape(str(job.get('current_step') or ''))}</b></div>
    <div class="metric"><span>Historical steps</span><b>{html.escape(str(len(all_steps)))}</b></div>
    <div class="metric"><span>Read-only check</span><b>{html.escape(str(not mutation_check.get('event_count_changed')))}</b></div>
  </div>
  <p><b>Goal:</b> {html.escape(str(job.get('goal') or ''))}</p>
  {_step_strip_html(job_id, all_steps, int((current_step or {}).get('step') or 0) if isinstance(current_step, dict) else 0)}
  {step_window_html}
  <p>{_dashboard_links(job_id)}</p>
  {_html_detail_block("Mutation Check", _html_json_tree(mutation_check, path="ia.mutation_check"), detail_key="ia.mutation_check")}
</div>
{''.join(cards)}
</body>
</html>"""


def agent_job_html(job_id: str) -> str:
    status = compact_agent_status(job_id, include_events=True)
    if not status.get("ok"):
        return f"<html><body><h1>Job not found</h1>{_html_pre(status)}</body></html>"
    events = read_agent_events(job_id, 500)
    rows = []
    for ev in events:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(ev.get('time') or ev.get('ts') or ''))}</td>"
            f"<td>{html.escape(str(ev.get('step') or ''))}</td>"
            f"<td>{html.escape(str(ev.get('event_type') or ''))}</td>"
            f"<td><pre>{html.escape(str(ev.get('message') or ''))}</pre></td>"
            "</tr>"
        )
    final_summary = html.escape(str(status.get("final_summary") or ""))
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AI-Carmine Agent Job {html.escape(job_id)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
details {{ border-top: 1px solid #333; padding-top: 10px; margin-top: 10px; }}
summary {{ cursor: pointer; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border-bottom: 1px solid #333; padding: 8px; vertical-align: top; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
{_adaptive_dashboard_css()}
{_gpu0_panel_css()}
</style>
{_stateful_refresh_script(2)}
</head>
<body>
{_gpu0_panel_html(job_id)}
<div class="card" data-live-region="job-summary">
  <div class="status">Job {html.escape(job_id)} - {html.escape(str(status.get('status')))}</div>
  <p><b>Goal:</b> {html.escape(str(status.get('goal') or ''))}</p>
  <p><b>Workspace:</b> {html.escape(str(status.get('workspace') or ''))}</p>
  <p>{_dashboard_links(job_id)}</p>
</div>
<div class="card" data-live-region="job-final-summary">
  <h2>Final summary</h2>
  <pre>{final_summary}</pre>
</div>
<div class="card">
  <h2>Control views</h2>
  <p>The dashboard is an index/status page. Planner prompt, stream, raw tool payloads and validator details are shown in the IA live control view.</p>
  <p><a href="/jobs/{html.escape(job_id)}/ia-view">Open IA live control view</a></p>
</div>
<div class="card" data-live-region="job-events">
  <h2>Events</h2>
  <table>
    <thead><tr><th>Time</th><th>Step</th><th>Type</th><th>Message</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
</body>
</html>"""

