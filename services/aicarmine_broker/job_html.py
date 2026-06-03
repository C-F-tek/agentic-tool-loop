"""HTML rendering for agent job dashboards."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .job_store import agent_job_root, compact_agent_status, list_agent_jobs, load_agent_job_state, read_agent_events, read_json


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


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
    raw_ndjson = _read_text_if_exists(stem.with_suffix(".raw.ndjson"))
    return {
        "content": _read_text_if_exists(stem.with_suffix(".content.txt")),
        "all": _read_text_if_exists(stem.with_suffix(".all.txt")),
        "raw_ndjson": raw_ndjson,
        "native_stream": _planner_stream_native_summary(raw_ndjson),
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
    if isinstance(value, str):
        text = value
    else:
        text = _json_pretty(value)
    return f"<pre>{html.escape(text)}</pre>"


def _safe_detail_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return (cleaned.strip("-") or "detail")[:200]


def _html_detail_block(
    title: str,
    inner_html: str,
    *,
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


def _html_details(title: str, value: Any, *, open_by_default: bool = False) -> str:
    if value in (None, "", [], {}):
        return ""
    return _html_detail_block(
        title,
        _html_pre(value),
        open_by_default=open_by_default,
        detail_key=title,
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
                f"<span class=\"json-key\">{html.escape(str(key))}</span>: "
                f"{_html_json_scalar(item)}"
                "</span>"
            )
        return "<span class=\"json-inline-object\">{ " + ", ".join(parts) + " }</span>"
    if isinstance(value, list):
        parts = [_html_json_scalar(item) for item in value]
        return "<span class=\"json-inline-array\">[ " + ", ".join(parts) + " ]</span>"
    return _html_json_scalar(value)


def _html_json_tree(value: Any, *, path: str = "root", depth: int = 0) -> str:
    if _json_inline_container(value):
        return _html_json_inline_container(value)
    if isinstance(value, dict):
        if not value:
            return _html_pre("{}")
        parts: list[str] = ["<div class=\"json-tree json-object\">"]
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if not isinstance(item, (dict, list)) or _json_inline_container(item):
                parts.append(
                    "<div class=\"json-row\">"
                    f"<span class=\"json-key\">{html.escape(str(key))}</span>"
                    f"<span class=\"json-label\">{html.escape(_json_value_label(item))}</span>"
                    f"<span class=\"json-value\">{_html_json_tree(item, path=item_path, depth=depth + 1)}</span>"
                    "</div>"
                )
                continue
            title = f"{key} ({_json_value_label(item)})"
            parts.append(
                _html_detail_block(
                    title,
                    _html_json_tree(item, path=item_path, depth=depth + 1),
                    open_by_default=depth == 0 and not isinstance(item, (dict, list)),
                    detail_key=item_path,
                )
            )
        parts.append("</div>")
        return "".join(parts)
    if isinstance(value, list):
        if not value:
            return _html_pre("[]")
        parts = ["<div class=\"json-tree json-array\">"]
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, (dict, list)) or _json_inline_container(item):
                parts.append(
                    "<div class=\"json-row\">"
                    f"<span class=\"json-key\">[{index}]</span>"
                    f"<span class=\"json-label\">{html.escape(_json_value_label(item))}</span>"
                    f"<span class=\"json-value\">{_html_json_tree(item, path=item_path, depth=depth + 1)}</span>"
                    "</div>"
                )
                continue
            title = f"[{index}] ({_json_value_label(item)})"
            parts.append(
                _html_detail_block(
                    title,
                    _html_json_tree(item, path=item_path, depth=depth + 1),
                    open_by_default=False,
                    detail_key=item_path,
                )
            )
        parts.append("</div>")
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
        f"<a href=\"/jobs/{safe_job}/ia-view.json\">IA view json</a>"
    )


def _html_page(title: str, body_html: str, *, refresh_seconds: int = 0, job_id: str | None = None) -> str:
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
    *,
    summary: dict[str, Any] | None = None,
) -> str:
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">{html.escape(title)} - {html.escape(job_id)}</div>"
        f"<p>{_dashboard_links(job_id)}</p>"
        "</div>"
    )
    if summary:
        body += (
            "<div class=\"card\"><h2>Summary</h2>"
            f"{_html_json_tree(summary, path='summary')}"
            "</div>"
        )
    body += (
        "<div class=\"card\"><h2>Structured JSON</h2>"
        f"{_html_json_tree(payload, path=title)}"
        "</div>"
        "<div class=\"card\"><h2>Raw JSON</h2>"
        f"{_html_details('Complete raw JSON', payload)}"
        "</div>"
    )
    return _html_page(title, body, job_id=job_id)


def agent_job_status_json_view_html(job_id: str) -> str:
    payload = compact_agent_status(job_id, include_events=True)
    return _structured_json_page(
        job_id,
        "Compact Status JSON View",
        payload,
        summary={
            "ok": payload.get("ok"),
            "status": payload.get("status"),
            "goal": payload.get("goal"),
            "events_tail_count": len(payload.get("events_tail") or []),
        } if isinstance(payload, dict) else None,
    )


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
    return _structured_json_page(job_id, "Final JSON View", payload, summary=summary)


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
                payload_html = _html_detail_block(
                    "payload",
                    _html_json_tree(event.get("payload"), path=f"events.{step}.{event_index}.payload"),
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
        "<div class=\"card\"><h2>Events By Step</h2>"
        f"{''.join(step_parts) if step_parts else '<p>No events.</p>'}"
        "</div>"
        "<div class=\"card\"><h2>Raw NDJSON</h2>"
        f"{_html_details('Complete events.ndjson', raw)}"
        "</div>"
    )
    return _html_page("Events View", body, job_id=job_id)


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
            + _html_details("Planner full raw combined", display.get("combined"))
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
        "<div class=\"card\"><h2>Planner Stream Steps</h2>"
        f"{''.join(step_sections) if step_sections else '<p>No planner stream files.</p>'}"
        "</div>"
    )
    return _html_page("Planner Stream View", body, job_id=job_id)



def _stateful_refresh_script(refresh_seconds: int = 0) -> str:
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
  function restoreState() {{
    var state = readState();
    var details = state.details || {{}};
    document.querySelectorAll("details").forEach(function(el, index) {{
      var k = detailKey(el, index);
      if (Object.prototype.hasOwnProperty.call(details, k)) {{
        el.open = !!details[k];
      }}
      el.addEventListener("toggle", writeState);
    }});
    if (typeof state.scrollY === "number") {{
      window.scrollTo(0, state.scrollY);
    }}
  }}
  window.addEventListener("beforeunload", writeState);
  document.addEventListener("DOMContentLoaded", restoreState);
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


def _collect_gpu0_repair_nodes(value: Any, *, path: str = "root") -> list[dict[str, Any]]:
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
        "<aside class=\"gpu0-corrections-window\">"
        "<h2>GPU0 corrections JSON</h2>"
        f"{_html_pre(payload)}"
        "</aside>"
    )


def agent_jobs_index_html(*, limit: int, title: str, refresh_seconds: int) -> str:
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
            f"<a href=\"/jobs/{job_id}/planner-stream\">planner stream</a></td>"
            "</tr>"
        )
    body = (
        "<div class=\"card\">"
        f"<div class=\"status\">{html.escape(title)} Agent Jobs</div>"
        "<p class=\"muted\">Auto-refresh pagina disattivato. Aggiorna manualmente la lista job quando serve.</p>"
        "</div>"
        "<div class=\"card\">"
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
{_json_tree_css()}
</style>
{_stateful_refresh_script(0)}
</head>
<body>
{body}
</body>
</html>"""


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
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #111; color: #ddd; }}
a {{ color: #8fd3ff; }}
.card {{ border: 1px solid #444; border-radius: 8px; padding: 14px; margin-bottom: 14px; background: #1b1b1b; }}
pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; line-height: 1.35; }}
.status {{ font-size: 20px; font-weight: 700; }}
.audit-ok {{ border-left: 4px solid #45a75a; padding-left: 10px; }}
.audit-bad {{ border-left: 4px solid #d15b5b; padding-left: 10px; }}
{_gpu0_panel_css()}
</style>
{_stateful_refresh_script(0)}
</head>
<body>
{_gpu0_panel_html(job_id)}
<div class="card">
  <div class="status">IA Live Control View - {html.escape(job_id)}</div>
  <p><b>Status:</b> {html.escape(str((payload.get('job') or {}).get('status') or ''))}</p>
  <p><b>Goal:</b> {html.escape(str((payload.get('job') or {}).get('goal') or ''))}</p>
  <p><b>Current step:</b> {html.escape(str((payload.get('job') or {}).get('current_step') or ''))}</p>
  <p>Historical steps are kept in the complete JSON view only.</p>
  <p>{_dashboard_links(job_id)}</p>
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
    if not status.get("ok"):
        return f"<html><body><h1>Job not found</h1>{_html_pre(status)}</body></html>"
    root = agent_job_root(job_id)
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
    latest_step = _latest_planner_step(root)
    prompt_capture = _latest_planner_prompt_capture(root, latest_step)
    stream_display = _planner_stream_display(root, latest_step)
    native_stream = dict(stream_display.get("native_stream") or {})
    native_stream.pop("raw_ndjson", None)
    latest_decision: dict[str, Any] = {}
    latest_guard: dict[str, Any] = {}
    for ev in reversed(events):
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        event_type = str(ev.get("event_type") or "")
        if not latest_decision and event_type == "planner_decision":
            latest_decision = payload
        if not latest_guard and event_type == "planner_decision_rejected":
            latest_guard = payload
        if latest_decision and latest_guard:
            break
    request_sections = (
        _html_details(
            "Prompt capture summary",
            {
                "path": prompt_capture.get("path"),
                "planner_url": prompt_capture.get("planner_url"),
                "planner_model": prompt_capture.get("planner_model"),
                "num_ctx_effective": prompt_capture.get("num_ctx_effective"),
                "prompt_budget_report": prompt_capture.get("prompt_budget_report"),
            },
            open_by_default=True,
        )
        + _html_details("Prompt sent to 11434: messages/tools/options", prompt_capture.get("prompt_sent_to_11434"))
        + _html_details("Planner user payload", prompt_capture.get("planner_user_payload"))
    )
    stream_sections = (
        _html_details("Native stream summary", native_stream, open_by_default=True)
        + _html_details("Planner thinking / reasoning raw", stream_display.get("thinking"))
        + _html_details("Planner emitted content or native tool calls", stream_display.get("content"), open_by_default=True)
        + _html_details("Planner full raw combined", stream_display.get("combined"))
    )
    decision_sections = (
        _html_details("Latest planner decision", latest_decision, open_by_default=True)
        + _html_details("Latest validator guard / rejection", latest_guard, open_by_default=True)
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
{_gpu0_panel_css()}
</style>
{_stateful_refresh_script(0)}
</head>
<body>
{_gpu0_panel_html(job_id)}
<div class="card">
  <div class="status">Job {html.escape(job_id)} - {html.escape(str(status.get('status')))}</div>
  <p><b>Goal:</b> {html.escape(str(status.get('goal') or ''))}</p>
  <p><b>Workspace:</b> {html.escape(str(status.get('workspace') or ''))}</p>
  <p>{_dashboard_links(job_id)}</p>
</div>
<div class="card">
  <h2>Final summary</h2>
  <pre>{final_summary}</pre>
</div>
<div class="card">
  <h2>Planner request to 11434</h2>
  {request_sections or "<p>No planner prompt capture available.</p>"}
</div>
<div class="card">
  <h2>Planner stream from 11434</h2>
  {stream_sections or "<p>No planner stream available.</p>"}
</div>
<div class="card">
  <h2>Planner decision and validator</h2>
  {decision_sections or "<p>No planner decision available.</p>"}
</div>
<div class="card">
  <h2>Events</h2>
  <table>
    <thead><tr><th>Time</th><th>Step</th><th>Type</th><th>Message</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
</body>
</html>"""

