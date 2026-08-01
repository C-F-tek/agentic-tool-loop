from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.deterministic_common import bounded_int_arg, deterministic_input_error


def _read_paths_from_items(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str) and item.strip():
            paths.append(item.strip())
        elif isinstance(item, dict):
            for key in ("path", "file", "filename", "name"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    paths.append(candidate.strip())
                    break
            nested = item.get("paths") or item.get("files")
            if isinstance(nested, list):
                paths.extend(str(p).strip() for p in nested if str(p).strip())
    return paths


def repo_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    paths: list[str] = []
    if isinstance(args.get("paths"), list):
        paths.extend(str(p) for p in args["paths"] if str(p).strip())
    if args.get("path"):
        paths.append(str(args["path"]))
    paths.extend(_read_paths_from_items(args.get("items") or args.get("item")))

    deduped: list[str] = []
    for raw_path in paths:
        raw_s = str(raw_path).strip()
        if raw_s and raw_s not in deduped:
            deduped.append(raw_s)
    paths = deduped

    try:
        max_chars = bounded_int_arg(args, "max_chars", default=80000, minimum=1, maximum=200000)
        requested_max_paths = bounded_int_arg(
            args,
            ("max_paths", "limit"),
            default=len(paths) or 1,
            minimum=1,
            maximum=max(1, len(paths)),
        )
        max_paths = min(requested_max_paths, len(paths))
        before = bounded_int_arg(args, "before", default=40, minimum=0, maximum=1000)
        after = bounded_int_arg(args, "after", default=120, minimum=0, maximum=1000)
        line = bounded_int_arg(args, "line", default=0, minimum=0, maximum=10_000_000)
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return deterministic_input_error("repo_read", exc)
    items: list[dict[str, Any]] = []

    for raw in paths[:max_paths]:
        try:
            rel = safe_rel_path(raw)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
            if not full.exists() or not full.is_file():
                items.append({"ok": False, "path": rel, "error": "file_not_found"})
                continue
            text = full.read_text(encoding="utf-8-sig", errors="replace")
            if line:
                lines = text.splitlines()
                n = max(1, min(int(line), max(1, len(lines))))
                start = max(1, n - before)
                end = min(len(lines), n + after)
                content = "\n".join(
                    f"{i}: {lines[i - 1]}" for i in range(start, end + 1)
                )
            else:
                content = text
            item: dict[str, Any] = {
                "ok": True,
                "path": rel,
                "size_bytes": full.stat().st_size,
                "line_count": len(text.splitlines()),
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }
            safe_name = rel.replace("/", "__").replace("\\", "__")
            artifact = root / "reads" / f"{safe_name}.json"
            artifact_item = dict(item)
            artifact_item["content"] = content
            artifact_item["truncated"] = False
            artifact_item["inline_result_truncated"] = item["truncated"]
            artifact_item["inline_max_chars"] = max_chars
            write_json(artifact, artifact_item)
            item["artifact"] = str(artifact)
            items.append(item)
        except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
            items.append(
                {
                    "ok": False,
                    "path": raw,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    if not paths:
        payload = {
            "ok": False,
            "tool": "repo_read",
            "count": 0,
            "items": [],
            "error": "missing path/paths/items",
            "input_keys": sorted(str(k) for k in args.keys()),
        }
    else:
        success_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is True)
        failed_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is False)
        payload = {
            "ok": success_count > 0,
            "tool": "repo_read",
            "count": len(items),
            "requested_count": len(paths),
            "max_paths": max_paths,
            "success_count": success_count,
            "failed_count": failed_count,
            "all_ok": bool(items) and success_count == len(items),
            "items": items,
        }
    write_json(root / "tool-results" / f"{now()}-repo_read.json", payload)
    return payload
