#!/usr/bin/env python3
"""Read-only MCP server for local agent job HTML views."""

from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
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

SERVER_NAME = "aicarmine-job-view-mcp"
SERVER_VERSION = "0.1.0"

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
WINDOWS_USER_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\s<>'\"]+")
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

VIEW_NAMES = {
    "jobs_index",
    "job_dashboard",
    "status_json",
    "status_json_section",
    "final_json",
    "final_json_section",
    "final_markdown",
    "events",
    "events_section",
    "planner_stream",
    "ia_view",
    "ia_view_section",
    "planner_lab_index",
    "planner_lab",
}


def string_prop(default: str | None = None, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if enum is not None:
        schema["enum"] = enum
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _resolve_path(value: str, default: Path, root: Path) -> Path:
    text = str(value or "").strip()
    candidate = Path(text).expanduser() if text else default
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _effective_paths(root: Path) -> dict[str, Path]:
    workspace = _resolve_path(
        os.environ.get("AICARMINE_VULKAN_WORKSPACE", ""),
        root / "qwen-agent-workspace" / "vulkan-broker",
        root,
    )
    job_root = _resolve_path(
        os.environ.get("AICARMINE_AGENT_JOB_ROOT", ""),
        workspace / "agent-jobs",
        root,
    )
    job_db = _resolve_path(
        os.environ.get("AICARMINE_AGENT_JOB_DB", ""),
        job_root / "agent_jobs.sqlite3",
        root,
    )
    return {"workspace": workspace, "job_root": job_root, "job_db": job_db}


def _configure_broker_env(root: Path) -> dict[str, Path]:
    paths = _effective_paths(root)
    os.environ["AICARMINE_LAB_REPO"] = str(root)
    os.environ["AICARMINE_CODEX_MCP_REPO_ROOT"] = str(root)
    os.environ["AICARMINE_VULKAN_WORKSPACE"] = str(paths["workspace"])
    os.environ["AICARMINE_AGENT_JOB_ROOT"] = str(paths["job_root"])
    os.environ["AICARMINE_AGENT_JOB_DB"] = str(paths["job_db"])
    return paths


def _patch_broker_modules(root: Path) -> dict[str, Path]:
    paths = _configure_broker_env(root)
    modules = [
        "aicarmine_broker.config",
        "aicarmine_broker.config.compatibility",
        "aicarmine_broker.job_store",
    ]
    for module_name in modules:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr, value in (
            ("LAB_REPO", root),
            ("WORKSPACE", paths["workspace"]),
            ("AGENT_JOB_ROOT", paths["job_root"]),
            ("AGENT_JOB_DB", paths["job_db"]),
        ):
            if hasattr(module, attr):
                setattr(module, attr, value)
    return paths


def _load_renderers(root: Path) -> tuple[Any, Any, dict[str, Path]]:
    paths = _patch_broker_modules(root)
    from aicarmine_broker import job_html, job_planner_lab  # noqa: PLC0415

    _patch_broker_modules(root)
    return job_html, job_planner_lab, paths


def _safe_job_id(value: Any) -> str:
    job_id = str(value or "").strip()
    if not job_id:
        raise ValueError("missing job_id")
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"invalid job_id: {job_id}")
    return job_id


def _view_name(value: Any, default: str = "job_dashboard") -> str:
    view = str(value or default).strip()
    if view not in VIEW_NAMES:
        raise ValueError(f"invalid view: {view}")
    return view


def _truncate_text(value: str, limit: int) -> tuple[str, bool]:
    """Return full text without truncation. limit is ignored."""
    return value, False


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _compact_ws(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "..."


class _HtmlOutlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.headings: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self.details: list[dict[str, str]] = []
        self.tag_counts: Counter[str] = Counter()
        self.stack: list[str] = []
        self.unmatched_end_tags: list[str] = []
        self._capture: dict[str, Any] | None = None
        self._link: dict[str, Any] | None = None
        self._summary: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        self.tag_counts[tag] += 1
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if tag in {"h1", "h2", "h3", "h4"}:
            self._capture = {"kind": "heading", "tag": tag, "text": []}
        elif tag == "title":
            self._capture = {"kind": "title", "text": []}
        elif tag == "a":
            self._link = {"href": attr_map.get("href", ""), "text": []}
        elif tag == "form":
            self.forms.append(
                {
                    "method": attr_map.get("method", "get").upper(),
                    "action": attr_map.get("action", ""),
                }
            )
        elif tag == "summary":
            self._summary = {"text": []}

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture["text"].append(data)
        if self._link is not None:
            self._link["text"].append(data)
        if self._summary is not None:
            self._summary["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]
        elif tag not in VOID_TAGS:
            self.unmatched_end_tags.append(tag)
        if self._capture is not None:
            if self._capture.get("kind") == "title" and tag == "title":
                self.title_parts.append("".join(self._capture["text"]))
                self._capture = None
            elif self._capture.get("kind") == "heading" and tag == self._capture.get("tag"):
                self.headings.append(
                    {
                        "level": str(self._capture["tag"]),
                        "text": _compact_ws("".join(self._capture["text"])),
                    }
                )
                self._capture = None
        if tag == "a" and self._link is not None:
            self.links.append(
                {
                    "href": str(self._link.get("href") or ""),
                    "text": _compact_ws("".join(self._link.get("text") or [])),
                }
            )
            self._link = None
        if tag == "summary" and self._summary is not None:
            self.details.append({"summary": _compact_ws("".join(self._summary.get("text") or []))})
            self._summary = None


def _html_outline(html_text: str, *, max_items: int = 80) -> dict[str, Any]:
    parser = _HtmlOutlineParser()
    parser.feed(html_text)
    parser.close()
    windows_paths = sorted(set(WINDOWS_USER_PATH_RE.findall(html_text)))[:20]
    lazy_urls = sorted(set(re.findall(r"data-lazy-url=[\"']([^\"']+)", html_text)))[:max_items]
    return {
        "title": _compact_ws(" ".join(parser.title_parts), 240),
        "headings": parser.headings[:max_items],
        "links": parser.links[:max_items],
        "forms": parser.forms[:max_items],
        "details": parser.details[:max_items],
        "counts": {
            "tags": dict(parser.tag_counts),
            "links": len(parser.links),
            "forms": len(parser.forms),
            "details": len(parser.details),
            "tables": parser.tag_counts.get("table", 0),
            "scripts": parser.tag_counts.get("script", 0),
            "styles": parser.tag_counts.get("style", 0),
            "pre": parser.tag_counts.get("pre", 0),
            "code": parser.tag_counts.get("code", 0),
        },
        "lazy_urls": lazy_urls,
        "windows_user_path_hits": windows_paths,
        "balance": {
            "unclosed_stack_tail": parser.stack[-20:],
            "unmatched_end_tags": parser.unmatched_end_tags[:20],
        },
    }


def _validate_html_text(html_text: str) -> dict[str, Any]:
    lowered = html_text.lower()
    outline = _html_outline(html_text, max_items=40)
    raw_links = outline.get("links")
    links: list[Any] = raw_links if isinstance(raw_links, list) else []
    hrefs = [str(item.get("href") or "") for item in links if isinstance(item, dict)]
    file_links = [href for href in hrefs if href.lower().startswith("file:") or "c:\\users\\" in href.lower()]
    local_http_links = [
        href
        for href in hrefs
        if href.startswith("http://127.0.0.1")
        or href.startswith("http://localhost")
        or href.startswith("https://localhost")
    ]
    warnings: list[str] = []
    if outline["windows_user_path_hits"]:
        warnings.append("windows_user_paths_visible")
    if file_links:
        warnings.append("file_links_visible")
    if local_http_links:
        warnings.append("local_http_links_visible")
    if outline["balance"]["unclosed_stack_tail"] or outline["balance"]["unmatched_end_tags"]:
        warnings.append("possible_tag_balance_issue")
    return {
        "ok": True,
        "doctype_present": lowered.lstrip().startswith("<!doctype html"),
        "has_html_tag": "<html" in lowered,
        "has_head_tag": "<head" in lowered,
        "has_body_tag": "<body" in lowered,
        "has_title": bool(outline.get("title")),
        "html_chars": len(html_text),
        "script_count": outline["counts"]["scripts"],
        "inline_fetch_count": html_text.count("fetch("),
        "lazy_url_count": len(outline.get("lazy_urls") or []),
        "file_links": file_links[:20],
        "local_http_links": local_http_links[:20],
        "windows_user_path_hits": outline["windows_user_path_hits"],
        "balance": outline["balance"],
        "warnings": warnings,
    }


def _render_html(view: str, args: dict[str, Any], root: Path) -> tuple[str, dict[str, Any]]:
    job_html, job_planner_lab, paths = _load_renderers(root)
    limit = _safe_int(args.get("limit"), 50, 1, 200)
    refresh_seconds = _safe_int(args.get("refresh_seconds"), 0, 0, 60)
    meta: dict[str, Any] = {
        "view": view,
        "read_only": True,
        "mode": "local_renderer_no_http",
        "job_root": str(paths["job_root"]),
    }
    if view == "jobs_index":
        title = str(args.get("title") or "AI-Carmine Job View")
        return job_html.agent_jobs_index_html(limit=limit, title=title, refresh_seconds=refresh_seconds), meta
    if view == "planner_lab_index":
        return job_planner_lab.planner_lab_index_html(limit=limit), meta

    job_id = _safe_job_id(args.get("job_id"))
    meta["job_id"] = job_id
    section = str(args.get("section") or "").strip()
    key = str(args.get("key") or "").strip()
    index = _safe_int(args.get("index"), 0, 0, 100000)
    step = _safe_int(args.get("step"), 0, 0, 100000)

    if view == "job_dashboard":
        return job_html.agent_job_html(job_id), meta
    if view == "status_json":
        return job_html.agent_job_status_json_view_html(job_id), meta
    if view == "status_json_section":
        return job_html.agent_job_status_json_section_html(job_id, section, key=key, index=index), meta
    if view == "final_json":
        return job_html.agent_job_final_json_view_html(job_id), meta
    if view == "final_json_section":
        return job_html.agent_job_final_json_section_html(job_id, section, key=key, index=index), meta
    if view == "final_markdown":
        return job_html.agent_job_final_markdown_view_html(job_id), meta
    if view == "events":
        return job_html.agent_job_events_view_html(job_id), meta
    if view == "events_section":
        return job_html.agent_job_events_section_html(job_id, section, step=str(args.get("step") or ""), index=index), meta
    if view == "planner_stream":
        return job_html.agent_job_planner_stream_view_html(job_id), meta
    if view == "ia_view":
        return job_html.agent_job_ia_view_html(job_id), meta
    if view == "ia_view_section":
        return job_html.agent_job_ia_view_section_html(job_id, section, step=step), meta
    if view == "planner_lab":
        return job_planner_lab.agent_job_planner_lab_html(job_id), meta
    raise ValueError(f"unsupported view: {view}")


def _list_views(args: dict[str, Any], root: Path) -> dict[str, Any]:
    paths = _patch_broker_modules(root)
    return {
        "ok": True,
        "tool": "aicarmine_job_view_list_views",
        "read_only": True,
        "mode": "local_renderer_no_http",
        "job_root": str(paths["job_root"]),
        "views": [
            {"name": "jobs_index", "requires_job_id": False, "sections": []},
            {"name": "job_dashboard", "requires_job_id": True, "sections": []},
            {"name": "status_json", "requires_job_id": True, "sections": []},
            {"name": "status_json_section", "requires_job_id": True, "sections": ["key", "index"]},
            {"name": "final_json", "requires_job_id": True, "sections": []},
            {"name": "final_json_section", "requires_job_id": True, "sections": ["key", "index"]},
            {"name": "final_markdown", "requires_job_id": True, "sections": []},
            {"name": "events", "requires_job_id": True, "sections": []},
            {"name": "events_section", "requires_job_id": True, "sections": ["raw", "payload"]},
            {"name": "planner_stream", "requires_job_id": True, "sections": []},
            {"name": "ia_view", "requires_job_id": True, "sections": []},
            {
                "name": "ia_view_section",
                "requires_job_id": True,
                "sections": [
                    "prompt",
                    "planner_stream_raw",
                    "events_raw",
                    "compact_tool_result",
                    "raw_tool_result",
                    "payload_audit",
                    "runtime_debug",
                    "openwebui_payload",
                ],
            },
            {"name": "planner_lab_index", "requires_job_id": False, "sections": []},
            {"name": "planner_lab", "requires_job_id": True, "sections": []},
        ],
    }


def _render(args: dict[str, Any], root: Path) -> dict[str, Any]:
    view = _view_name(args.get("view"))
    html_text, meta = _render_html(view, args, root)
    max_chars = _safe_int(args.get("max_chars"), 50000, 1000, 500000)
    include_html = _safe_bool(args.get("include_html"), True)
    include_outline = _safe_bool(args.get("include_outline"), True)
    compact_html, truncated = _truncate_text(html_text, max_chars)
    result = {
        "ok": True,
        "tool": "aicarmine_job_view_render",
        **meta,
        "html_chars": len(html_text),
        "html_truncated": truncated,
    }
    if include_html:
        result["html"] = compact_html
    if include_outline:
        result["outline"] = _html_outline(html_text)
    return result


def _render_section(args: dict[str, Any], root: Path) -> dict[str, Any]:
    view = _view_name(args.get("view"), default="ia_view_section")
    if view not in {"status_json_section", "final_json_section", "events_section", "ia_view_section"}:
        return {
            "ok": False,
            "error": "view_is_not_section_renderable",
            "view": view,
            "allowed": ["status_json_section", "final_json_section", "events_section", "ia_view_section"],
        }
    return _render({**args, "view": view}, root)


def _ia_payload(args: dict[str, Any], root: Path) -> dict[str, Any]:
    job_html, _job_planner_lab, paths = _load_renderers(root)
    job_id = _safe_job_id(args.get("job_id"))
    include_heavy = _safe_bool(args.get("include_heavy"), False)
    max_chars = _safe_int(args.get("max_chars"), 80000, 1000, 1000000)
    payload = job_html.agent_job_ia_view_payload(job_id, include_heavy=include_heavy)
    payload_text = _json_pretty(payload)
    compact_payload_text, truncated = _truncate_text(payload_text, max_chars)
    result: dict[str, Any] = {
        "ok": bool(isinstance(payload, dict) and payload.get("ok") is not False),
        "tool": "aicarmine_job_view_ia_payload",
        "read_only": True,
        "mode": "local_renderer_no_http",
        "job_id": job_id,
        "job_root": str(paths["job_root"]),
        "include_heavy": include_heavy,
        "payload_chars": len(payload_text),
        "payload_truncated": truncated,
    }
    if not truncated:
        result["payload"] = payload
    else:
        result["payload_json"] = compact_payload_text
    return result


def _outline(args: dict[str, Any], root: Path) -> dict[str, Any]:
    view = _view_name(args.get("view"))
    html_text, meta = _render_html(view, args, root)
    return {
        "ok": True,
        "tool": "aicarmine_job_view_outline",
        **meta,
        "html_chars": len(html_text),
        "outline": _html_outline(html_text),
    }


def _links(args: dict[str, Any], root: Path) -> dict[str, Any]:
    view = _view_name(args.get("view"))
    html_text, meta = _render_html(view, args, root)
    outline = _html_outline(html_text)
    return {
        "ok": True,
        "tool": "aicarmine_job_view_links",
        **meta,
        "links": outline.get("links") or [],
        "lazy_urls": outline.get("lazy_urls") or [],
    }


def _validate_html(args: dict[str, Any], root: Path) -> dict[str, Any]:
    view = _view_name(args.get("view"))
    html_text, meta = _render_html(view, args, root)
    return {
        "ok": True,
        "tool": "aicarmine_job_view_validate_html",
        **meta,
        "validation": _validate_html_text(html_text),
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    paths = _patch_broker_modules(root)
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "read_only": True,
            "mode": "local_renderer_no_http",
            "job_root": str(paths["job_root"]),
            "job_root_exists": paths["job_root"].is_dir(),
            "render_sources": [
                "services/aicarmine_broker/job_html.py",
                "services/aicarmine_broker/job_planner_lab.py",
            ],
            "views": sorted(VIEW_NAMES),
            "no_broker_http": True,
            "no_agentic_loop": True,
            "no_service_start": True,
        }
    )
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    render_props = {
        "view": string_prop("job_dashboard", enum=sorted(VIEW_NAMES)),
        "job_id": string_prop(),
        "section": string_prop(),
        "key": string_prop(),
        "index": integer_prop(0, 0, 100000),
        "step": integer_prop(0, 0, 100000),
        "limit": integer_prop(50, 1, 200),
        "title": string_prop("AI-Carmine Job View"),
        "refresh_seconds": integer_prop(0, 0, 60),
        "include_html": boolean_prop(True),
        "include_outline": boolean_prop(True),
        "max_chars": integer_prop(50000, 1000, 500000),
    }
    section_props = dict(render_props)
    section_props["view"] = string_prop("ia_view_section", enum=["status_json_section", "final_json_section", "events_section", "ia_view_section"])

    tools["aicarmine_job_view_health"] = ToolSpec(
        name="aicarmine_job_view_health",
        description="Report job-view MCP health, render sources and read-only local renderer guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_job_view_list_views"] = ToolSpec(
        name="aicarmine_job_view_list_views",
        description="List available local job HTML views and section renderers.",
        input_schema=object_schema(),
        handler=_list_views,
    )
    tools["aicarmine_job_view_render"] = ToolSpec(
        name="aicarmine_job_view_render",
        description="Render one existing agent job HTML view locally without broker HTTP.",
        input_schema=object_schema(render_props),
        handler=_render,
    )
    tools["aicarmine_job_view_render_section"] = ToolSpec(
        name="aicarmine_job_view_render_section",
        description="Render one existing lazy/section HTML fragment locally without broker HTTP.",
        input_schema=object_schema(section_props),
        handler=_render_section,
    )
    tools["aicarmine_job_view_ia_payload"] = ToolSpec(
        name="aicarmine_job_view_ia_payload",
        description="Read the IA live control view payload directly from local job files.",
        input_schema=object_schema(
            {
                "job_id": string_prop(),
                "include_heavy": boolean_prop(False),
                "max_chars": integer_prop(80000, 1000, 1000000),
            },
            required=["job_id"],
        ),
        handler=_ia_payload,
    )
    tools["aicarmine_job_view_outline"] = ToolSpec(
        name="aicarmine_job_view_outline",
        description="Render a job view and return an HTML outline instead of the full document.",
        input_schema=object_schema(render_props),
        handler=_outline,
    )
    tools["aicarmine_job_view_links"] = ToolSpec(
        name="aicarmine_job_view_links",
        description="Render a job view and extract links and lazy section URLs.",
        input_schema=object_schema(render_props),
        handler=_links,
    )
    tools["aicarmine_job_view_validate_html"] = ToolSpec(
        name="aicarmine_job_view_validate_html",
        description="Render a job view and run bounded structural/safety checks on the HTML.",
        input_schema=object_schema(render_props),
        handler=_validate_html,
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
            health_tool="aicarmine_job_view_health",
            real_tool="aicarmine_job_view_list_views",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
