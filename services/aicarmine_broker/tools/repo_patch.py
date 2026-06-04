from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json


def repo_apply_patch(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    old_text = args.get("old_text")
    new_text = args.get("new_text")
    max_replacements = max(1, min(int(args.get("max_replacements") or 1), 20))

    if not path:
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing path"}
    if not isinstance(old_text, str) or old_text == "":
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing old_text"}
    if not isinstance(new_text, str):
        return {"ok": False, "tool": "repo_apply_patch", "error": "missing new_text"}

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_apply_patch",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if not full.exists() or not full.is_file():
        return {"ok": False, "tool": "repo_apply_patch", "path": rel, "error": "file_not_found"}

    original = full.read_text(encoding="utf-8-sig", errors="replace")
    occurrences = original.count(old_text)
    if occurrences < 1:
        return {
            "ok": False,
            "tool": "repo_apply_patch",
            "path": rel,
            "error": "old_text_not_found",
            "old_text_preview": old_text[:1000],
        }

    replacements = min(occurrences, max_replacements)
    updated = original.replace(old_text, new_text, replacements)

    safe_name = rel.replace("/", "__").replace("\\", "__")
    backup = root / "artifacts" / f"{safe_name}.{now()}.before.txt"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(original, encoding="utf-8")
    full.write_text(updated, encoding="utf-8")

    payload = {
        "ok": True,
        "tool": "repo_apply_patch",
        "path": rel,
        "changed": updated != original,
        "occurrences_found": occurrences,
        "replacements": replacements,
        "line_count_before": len(original.splitlines()),
        "line_count_after": len(updated.splitlines()),
        "backup_artifact": str(backup),
    }
    write_json(root / "tool-results" / f"{now()}-repo_apply_patch.json", payload)
    return payload


def repo_write_file(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    content = args.get("content")
    mode = str(args.get("mode") or "overwrite").strip().lower()
    encoding = str(args.get("encoding") or "utf-8").strip() or "utf-8"

    if not path:
        return {"ok": False, "tool": "repo_write_file", "error": "missing path"}
    if not isinstance(content, str):
        return {"ok": False, "tool": "repo_write_file", "path": path, "error": "missing string content"}
    if mode not in {"overwrite", "create", "append"}:
        return {
            "ok": False,
            "tool": "repo_write_file",
            "path": path,
            "error": "mode must be overwrite, create or append",
        }

    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_write_file",
            "path": path,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    if full.exists() and full.is_dir():
        return {"ok": False, "tool": "repo_write_file", "path": rel, "error": "target_is_directory"}
    if mode == "create" and full.exists():
        return {"ok": False, "tool": "repo_write_file", "path": rel, "error": "file_exists"}

    backup_path = before_sha256 = ""
    before_size = 0
    if full.exists() and full.is_file():
        old_bytes = full.read_bytes()
        before_size = len(old_bytes)
        before_sha256 = hashlib.sha256(old_bytes).hexdigest()
        safe_name = rel.replace("/", "__").replace("\\", "__")
        backup = root / "backups" / f"{now()}-{safe_name}.bak"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(old_bytes)
        backup_path = str(backup)

    full.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with full.open("a", encoding=encoding, errors="replace", newline="") as handle:
            handle.write(content)
    else:
        full.write_text(content, encoding=encoding, errors="replace", newline="")

    after_bytes = full.read_bytes()
    after_sha256 = hashlib.sha256(after_bytes).hexdigest()

    payload = {
        "ok": True,
        "tool": "repo_write_file",
        "path": rel,
        "mode": mode,
        "backup_path": backup_path,
        "before_size": before_size,
        "after_size": len(after_bytes),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "line_count_after": len(full.read_text(encoding=encoding, errors="replace").splitlines()),
    }
    artifact = root / "tool-results" / f"{now()}-repo_write_file.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
