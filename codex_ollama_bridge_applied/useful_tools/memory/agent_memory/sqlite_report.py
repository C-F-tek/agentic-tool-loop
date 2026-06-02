"""Report assembly for runtime SQLite memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ia_carmine._shared.file_backed_transport import INLINE_TEXT_MAX_CHARS

from .common import (
    is_under,
    read_arg_file,
    relative_path,
    resolve_repo_path,
    split_csv_values,
    utc_now_iso,
)
from .sqlite_store import (
    clear_operational,
    operational_status,
    persistent_status,
    remember_operational,
    remember_persistent,
    search_operational,
    search_persistent,
)


def now_iso() -> str:
    return utc_now_iso()


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    return resolve_repo_path(repo_root, value)


def repo_rel(path: Path, repo_root: Path) -> str:
    return relative_path(path, repo_root)


def parse_tags(values: list[str]) -> list[str]:
    return split_csv_values(values)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    operational_db = resolve_path(repo_root, args.database)
    persistent_db = resolve_path(repo_root, args.persistent_database)
    output_root = resolve_path(repo_root, "output")
    errors: list[str] = []
    warnings: list[str] = []
    content_text = ""
    if getattr(args, "content", ""):
        errors.append("content_inline_requires_content_file")
        if len(str(args.content)) > INLINE_TEXT_MAX_CHARS:
            errors.append("content_inline_too_large")
    if getattr(args, "content_file", ""):
        try:
            content_text = read_arg_file(repo_root, args.content_file)
        except OSError as exc:
            errors.append(f"content_file read failed: {type(exc).__name__}: {exc}")
    result: dict[str, Any] = {}
    operation = args.action
    memory_scope = args.scope
    operational_db_allowed = is_under(operational_db, output_root)
    operational_write = False
    operational_clear = False
    persistent_write = False
    def memory_status() -> dict[str, Any]:
        return (
            operational_status(operational_db)
            if memory_scope == "operational"
            else persistent_status(persistent_db)
        )

    if memory_scope == "operational" and not operational_db_allowed:
        errors.append("operational database must be under output/**")
    else:
        try:
            if operation == "status":
                result = memory_status()
            elif operation == "remember":
                if memory_scope == "operational":
                    result = remember_operational(
                        operational_db,
                        summary=args.summary,
                        content=content_text,
                        role=args.role,
                        tags=parse_tags(args.tag),
                        metadata={
                            "tool": "agent_runtime_sqlite_memory",
                            "request_id": args.request_id,
                        },
                    )
                    operational_write = True
                    result.update(memory_status())
                elif memory_scope == "persistent":
                    if not args.allow_persistent_write or args.confirm != "persistent_write":
                        raise ValueError(
                            "persistent remember requires --allow-persistent-write and --confirm persistent_write"
                        )
                    result = remember_persistent(
                        persistent_db,
                        summary=args.summary,
                        content=content_text,
                        source=args.role,
                        tags=parse_tags(args.tag),
                        metadata={
                            "tool": "agent_runtime_sqlite_memory",
                            "request_id": args.request_id,
                            "explicit_confirm": args.confirm,
                        },
                    )
                    persistent_write = True
                    result.update(memory_status())
                else:
                    raise ValueError(f"unsupported memory scope for remember: {memory_scope}")
            elif operation == "search":
                status = memory_status()
                result = {
                    "query": args.query,
                    "sqlite_search_backend": status.get("sqlite_search_backend"),
                    "sqlite_fts5_enabled": status.get("sqlite_fts5_enabled"),
                    "records": (
                        search_operational(operational_db, args.query, args.limit)
                        if memory_scope == "operational"
                        else search_persistent(persistent_db, args.query, args.limit)
                    ),
                }
            elif operation == "clear_operational":
                if memory_scope != "operational":
                    raise ValueError("clear_operational is allowed only for operational memory")
                result = clear_operational(operational_db, args.confirm)
                operational_write = True
                operational_clear = True
                result.update(memory_status())
            else:
                raise ValueError(f"unsupported action: {operation}")
        except Exception as exc:  # noqa: BLE001 - report-only tool result.
            errors.append(f"{type(exc).__name__}: {exc}")

    backend = "unknown"
    fts5_enabled = False
    if isinstance(result, dict):
        backend = str(result.get("sqlite_search_backend", backend))
        fts5_enabled = bool(result.get("sqlite_fts5_enabled", False))

    return {
        "schema_version": 1,
        "kind": "agent_runtime_sqlite_memory",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": persistent_write,
        "persistent_memory_write_performed": persistent_write,
        "operational_sqlite_write_performed": operational_write,
        "persistent_sqlite_write_performed": persistent_write,
        "operational_memory_write_performed": operational_write,
        "operational_memory_clear_performed": operational_clear,
        "sqlite_search_backend": backend,
        "sqlite_fts5_enabled": fts5_enabled,
        "action": operation,
        "scope": memory_scope,
        "operational_database": repo_rel(operational_db, repo_root),
        "persistent_database": repo_rel(persistent_db, repo_root),
        "operational_database_under_output": operational_db_allowed,
        "result": result,
        "guardrails": {
            "persistent_memory_read_only": True,
            "persistent_memory_write_performed": persistent_write,
            "persistent_memory_promotion_performed": False,
            "persistent_memory_write_authorized": bool(
                args.allow_persistent_write and args.confirm == "persistent_write"
            ),
            "sqlite_write_performed": persistent_write,
            "sqlite_search_backend": backend,
            "sqlite_fts5_enabled": fts5_enabled,
            "operational_sqlite_write_performed": operational_write,
            "operational_memory_clear_performed": operational_clear,
            "operational_database_must_be_under_output": True,
            "operational_database_under_output": operational_db_allowed,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "git_write_performed": False,
        },
    }

def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Runtime SQLite Memory", ""]
    for key in (
        "passed",
        "action",
        "scope",
        "operational_database",
        "persistent_database",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "operational_sqlite_write_performed",
        "operational_memory_clear_performed",
        "sqlite_search_backend",
        "sqlite_fts5_enabled",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("result", {}), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report.get("guardrails", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"
