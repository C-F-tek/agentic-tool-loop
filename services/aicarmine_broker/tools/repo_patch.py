from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.deterministic_common import (
    bounded_int_arg,
    deterministic_input_error,
    resolve_deterministic_executable,
    run_argv,
)


def _newline_policy_bytes(data: bytes) -> str:
    crlf_count = data.count(b"\r\n")
    lf_count = data.count(b"\n") - crlf_count
    cr_count = data.count(b"\r") - crlf_count
    policies = [
        name
        for name, count in (
            ("crlf", crlf_count),
            ("lf", lf_count),
            ("cr", cr_count),
        )
        if count
    ]
    if not policies:
        return "none"
    if len(policies) > 1:
        return "mixed"
    return policies[0]


def _apply_newline_policy_bytes(data: bytes, policy: str) -> bytes:
    if policy not in {"crlf", "lf", "cr"}:
        return data
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if policy == "crlf":
        return normalized.replace(b"\n", b"\r\n")
    if policy == "cr":
        return normalized.replace(b"\n", b"\r")
    return normalized


def _rollback_change_set_files(root: Path, records: list[dict[str, Any]]) -> None:
    for record in records:
        full_path = (root / record["path"]).resolve(strict=False)
        full_path.relative_to(root.resolve())
        if record["existed"]:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(Path(str(record["backup_path"])).read_bytes())
        elif full_path.exists() and full_path.is_file():
            full_path.unlink()


def _compute_old_text_not_found_details(
    old_text: str,
    file_content: str,
    rel: str,
) -> dict[str, Any]:
    """Compute detailed diagnostic information when old_text is not found in file_content.

    Detection order:
      1. old_text_is_prefix — exact match at start but file has more content
      2. partial_match_mismatch — some lines match then diverge
      3. content_mismatch_at_start — fuzzy match finds embedded content (e.g., imports after docstring)
      4. completely_different_content — no meaningful similarity
    """
    result: dict[str, Any] = {}

    old_lines = old_text.splitlines(keepends=True)
    file_lines = file_content.splitlines(keepends=True)

    # Strip trailing whitespace for comparison but track original
    old_stripped = [line.rstrip() for line in old_lines]
    file_stripped = [line.rstrip() for line in file_lines]

    def _lines_equal_stripped(a: str, b: str) -> bool:
        return a.strip() == b.strip()

    match_len = 0
    for i in range(min(len(old_stripped), len(file_stripped))):
        if _lines_equal_stripped(old_stripped[i], file_stripped[i]):
            match_len += 1
        else:
            break

    # Pattern 1: old_text is a prefix of the file (exact match at start but file has more)
    if match_len > 0 and match_len == len(old_stripped):
        if old_text.strip() == file_content[:len(old_text)].strip():
            remaining_in_file = file_content[len(old_text):].lstrip()
            if remaining_in_file:
                result.update({
                    "mismatch_type": "old_text_is_prefix",
                    "solvable": True,
                    "description": (
                        "The requested old_text matches the beginning of the file, "
                        f"but the file contains additional content afterwards. "
                        f"The file has {len(file_lines)} lines; old_text covers lines 1-{match_len}. "
                        f"Remaining file content starts with: {remaining_in_file[:200].strip()!r}"
                    ),
                    "common_patterns": [
                        "old_text is correct but incomplete — include all lines you want to replace",
                        "verify the exact boundaries of text to replace",
                    ],
                })
                return result

    # Pattern 2: partial match at start (some lines match, then diverge)
    if match_len > 0 and match_len < len(old_stripped):
        mismatch_idx = match_len
        expected_line = old_lines[mismatch_idx].rstrip()
        actual_line = file_lines[mismatch_idx].rstrip()
        result.update({
            "mismatch_type": "partial_match_mismatch",
            "solvable": True,
            "description": (
                f"old_text partially matches: {match_len}/{len(old_lines)} lines matched. "
                f"Mismatch at line {mismatch_idx + 1}. "
                f"Expected: {expected_line[:60]!r} "
                f"Actual:   {actual_line[:60]!r}"
            ),
            "common_patterns": [
                "Some lines match but content diverges partway through",
                "Use repo_read to get exact file content around the mismatch",
                "Verify old_text boundaries are correct",
            ],
            "matched_lines": match_len,
            "total_old_text_lines": len(old_lines),
            "mismatch_at_line": mismatch_idx + 1,
            "expected_content": expected_line[:80],
            "actual_content": actual_line[:80],
        })
        return result

    # Pattern 3: fuzzy match — search for best partial match anywhere in file
    # This catches cases like imports that are embedded after a docstring or other preamble.
    best_ratio = 0
    best_start = 0
    old_text_stripped = old_text.strip()

    for i in range(len(file_stripped)):
        window_size = min(5, len(old_stripped), len(file_stripped) - i)
        if window_size < 1:
            continue
        window = file_stripped[i:i + window_size]
        window_text = "\n".join(window)
        ratio = SequenceMatcher(None, old_text_stripped[:200], window_text[:200]).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i

    if best_ratio > 0.5 and best_start < len(file_lines):
        result.update({
            "mismatch_type": "content_mismatch_at_start",
            "solvable": True,
            "description": (
                f"old_text does not match the beginning of the file. "
                f"Best fuzzy match found at line {best_start + 1} "
                f"(similarity: {best_ratio:.0%}). "
                f"The file starts with: {file_lines[0].rstrip()[:80]!r}"
            ),
            "common_patterns": [
                "The file content may have changed since old_text was drafted",
                "Use repo_read to get the exact current file content",
                "Check if the file path is correct",
            ],
            "fuzzy_match_line": best_start + 1,
            "fuzzy_similarity": round(best_ratio, 2),
        })
        return result

    # Pattern 4: completely different content
    result.update({
        "mismatch_type": "completely_different_content",
        "solvable": False,
        "description": (
            "old_text does not match any part of the file. "
            f"The file has {len(file_lines)} lines; old_text has {len(old_lines)} lines. "
            f"File starts with: {file_lines[0].rstrip()[:80]!r}"
        ),
        "common_patterns": [
            "The file may have been modified since old_text was created",
            "The file path may be incorrect",
            "Use repo_read to verify current file content",
        ],
        "file_starts_with": file_lines[0].rstrip()[:80],
    })
    return result


def repo_apply_patch(args: dict[str, Any], root: Path) -> dict[str, Any]:
    path = str(args.get("path") or "").strip()
    old_text = args.get("old_text")
    new_text = args.get("new_text")
    try:
        max_replacements = bounded_int_arg(args, "max_replacements", default=1, minimum=1, maximum=100)
    except (ValueError, TypeError) as exc:
        return deterministic_input_error("repo_apply_patch", exc)

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
    except (OSError, ValueError, PermissionError):
        return {
            "ok": False,
            "tool": "repo_apply_patch",
            "path": path,
            "error_type": "path_resolution_failed",
            "error": f"Could not resolve path: {path}",
        }

    if not full.exists() or not full.is_file():
        return {"ok": False, "tool": "repo_apply_patch", "path": rel, "error": "file_not_found"}

    original_bytes = full.read_bytes()
    before_sha256 = hashlib.sha256(original_bytes).hexdigest()
    original = original_bytes.decode("utf-8-sig", errors="replace")
    occurrences = original.count(old_text)
    if occurrences < 1:
        details = _compute_old_text_not_found_details(old_text, original, rel)

        return {
            "ok": False,
            "tool": "repo_apply_patch",
            "path": rel,
            "error": "old_text_not_found",
            "error_details": details,
            "old_text_preview": old_text[:1000],
            "file_content_preview": original[:1000],
            "old_text_line_count": len(old_text.splitlines()),
            "file_line_count": len(original.splitlines()),
            "repair_hints": [
                "read_current_file_before_retry",
                "old_text_must_be_exact_match",
                "use_repo_read_with_max_chars_80000",
                f"repo_read path={rel} max_chars=80000",
            ],
            "suggested_next_tool_calls": [
                {
                    "tool": "repo_read",
                    "arguments": {"path": rel, "max_chars": 80000},
                    "reason": "read_file_to_verify_old_text_and_get_exact_content",
                },
            ],
            "diagnostic_summary": details.get("description", ""),
            "is_solvable": details.get("solvable", False),
            "common_fix_patterns": details.get("common_patterns", []),
        }

    replacements = min(occurrences, max_replacements)
    updated = original.replace(old_text, new_text, replacements)

    safe_name = rel.replace("/", "__").replace("\\", "__")
    backup = root / "artifacts" / f"{safe_name}.{now()}.before.txt"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original_bytes)
    full.write_text(updated, encoding="utf-8", newline="")
    after_bytes = full.read_bytes()
    after_sha256 = hashlib.sha256(after_bytes).hexdigest()

    validation_candidates: list[dict[str, Any]] = [{
        "tool": "repo_validate",
        "arguments": {"paths": [rel], "timeout_seconds": 300},
        "reason": "validate_modified_file_after_repo_apply_patch",
    }]
    if rel.endswith(".py"):
        validation_candidates.append({
            "tool": "repo_ruff_check",
            "arguments": {"paths": [rel], "timeout_seconds": 180},
            "reason": "python_static_validation_after_repo_apply_patch",
        })

    payload = {
        "ok": True,
        "tool": "repo_apply_patch",
        "path": rel,
        "modified_paths": [rel],
        "changed": updated != original,
        "occurrences_found": occurrences,
        "replacements": replacements,
        "line_count_before": len(original.splitlines()),
        "line_count_after": len(updated.splitlines()),
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "post_write_validation_required": updated != original,
        "validation_candidates": validation_candidates if updated != original else [],
        "backup_artifact": str(backup),
    }
    write_json(root / "tool-results" / f"{now()}-repo_apply_patch.json", payload)
    return payload


def repo_apply_unified_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
    from repo_code_change_set import (
        normalize_unified_diff_text,
        verify_change_set_preimages,
    )

    diff_text = args.get("unified_diff")
    metadata = args.get("_change_set_metadata")
    change_set_id = str(args.get("change_set_id") or "").strip()
    if not isinstance(diff_text, str) or not diff_text.strip():
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "missing_unified_diff",
        }
    if not isinstance(metadata, dict) or not change_set_id:
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "missing_resolved_change_set",
        }

    mismatches = verify_change_set_preimages(root, metadata)
    if mismatches:
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "change_set_preimage_mismatch",
            "change_set_id": change_set_id,
            "mismatches": mismatches,
            "source_writes_performed": False,
            "patch_application_performed": False,
        }

    git_executable = resolve_deterministic_executable("git")
    if not git_executable:
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "git_not_available",
        }

    normalized_diff = normalize_unified_diff_text(diff_text)
    diff_bytes = normalized_diff.encode("utf-8")
    matching_args = (
        ["--ignore-spacechange"]
        if args.get("_verified_change_set") is True
        else []
    )
    check_result = run_argv(
        [
            git_executable,
            "apply",
            "--check",
            *matching_args,
            "--whitespace=error",
            "-",
        ],
        cwd=root,
        timeout=120,
        stdin_bytes=diff_bytes,
    )
    if check_result.get("returncode") != 0:
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "git_apply_check_failed",
            "change_set_id": change_set_id,
            "returncode": check_result.get("returncode"),
            "stdout_tail": check_result.get("stdout_tail", ""),
            "stderr_tail": check_result.get("stderr_tail", ""),
            "source_writes_performed": False,
            "patch_application_performed": False,
        }

    backup_root = root / "state" / "repo_code" / "backups" / f"{change_set_id}-{now()}"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_records: list[dict[str, Any]] = []
    for item in metadata.get("files") if isinstance(metadata.get("files"), list) else []:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("path") or "")
        full_path = (root / relative_path).resolve(strict=False)
        full_path.relative_to(root.resolve())
        if full_path.is_file():
            backup_path = backup_root / f"{relative_path}.before"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            before_bytes = full_path.read_bytes()
            backup_path.write_bytes(before_bytes)
            backup_records.append(
                {
                    "path": relative_path,
                    "existed": True,
                    "backup_path": str(backup_path),
                    "newline_policy": _newline_policy_bytes(before_bytes),
                }
            )
        else:
            backup_records.append(
                {
                    "path": relative_path,
                    "existed": False,
                    "backup_path": None,
                    "newline_policy": "lf",
                }
            )

    apply_result = run_argv(
        [
            git_executable,
            "apply",
            *matching_args,
            "--whitespace=error",
            "-",
        ],
        cwd=root,
        timeout=120,
        stdin_bytes=diff_bytes,
    )
    rollback_performed = False
    if apply_result.get("returncode") != 0:
        _rollback_change_set_files(root, backup_records)
        rollback_performed = True
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "git_apply_failed",
            "change_set_id": change_set_id,
            "returncode": apply_result.get("returncode"),
            "stdout_tail": apply_result.get("stdout_tail", ""),
            "stderr_tail": apply_result.get("stderr_tail", ""),
            "rollback_performed": rollback_performed,
            "backup_root": str(backup_root),
            "source_writes_performed": False,
            "patch_application_performed": False,
        }

    try:
        for record in backup_records:
            full_path = (root / record["path"]).resolve(strict=False)
            full_path.relative_to(root.resolve())
            if not full_path.is_file():
                continue
            after_apply_bytes = full_path.read_bytes()
            normalized_bytes = _apply_newline_policy_bytes(
                after_apply_bytes,
                str(record.get("newline_policy") or ""),
            )
            if normalized_bytes != after_apply_bytes:
                full_path.write_bytes(normalized_bytes)
    except (OSError, IOError, PermissionError) as exc:
        _rollback_change_set_files(root, backup_records)
        rollback_performed = True
        return {
            "ok": False,
            "tool": "repo_apply_unified_diff",
            "error": "newline_policy_restore_failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "change_set_id": change_set_id,
            "rollback_performed": rollback_performed,
            "backup_root": str(backup_root),
            "source_writes_performed": False,
            "patch_application_performed": False,
        }

    modified_paths: list[str] = []
    added_paths: list[str] = []
    file_results: list[dict[str, Any]] = []
    changed = False
    for item in metadata.get("files") if isinstance(metadata.get("files"), list) else []:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("path") or "")
        full_path = (root / relative_path).resolve(strict=False)
        full_path.relative_to(root.resolve())
        after_bytes = full_path.read_bytes()
        after_sha256 = hashlib.sha256(after_bytes).hexdigest()
        before_sha256 = item.get("preimage_sha256")
        item_changed = before_sha256 != after_sha256
        changed = changed or item_changed
        if item.get("change_type") == "added":
            added_paths.append(relative_path)
        else:
            modified_paths.append(relative_path)
        file_results.append(
            {
                "path": relative_path,
                "change_type": item.get("change_type"),
                "before_sha256": before_sha256,
                "after_sha256": after_sha256,
                "line_count_before": item.get("preimage_line_count"),
                "line_count_after": len(
                    after_bytes.decode("utf-8", errors="replace").splitlines()
                ),
            }
        )

    payload = {
        "ok": True,
        "tool": "repo_apply_unified_diff",
        "change_set_id": change_set_id,
        "write_scope": "unified_diff",
        "changed": changed,
        "modified_paths": modified_paths,
        "added_paths": added_paths,
        "files": file_results,
        "backup_root": str(backup_root),
        "rollback_performed": rollback_performed,
        "post_write_validation_required": changed,
        "validation_candidates": (
            [
                {
                    "tool": "repo_validate",
                    "arguments": {
                        "paths": [*modified_paths, *added_paths],
                        "timeout_seconds": 300,
                    },
                    "reason": "validate_modified_files_after_repo_apply_unified_diff",
                }
            ]
            if changed
            else []
        ),
    }
    artifact = root / "tool-results" / f"{now()}-repo_apply_unified_diff.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
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
    except (OSError, ValueError, PermissionError):
        return {
            "ok": False,
            "tool": "repo_write_file",
            "path": path,
            "error_type": "path_resolution_failed",
            "error": f"Could not resolve path: {path}",
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
        "post_write_validation_required": True,
        "validation_candidates": [
            {
                "tool": "repo_validate",
                "arguments": {"paths": [rel], "timeout_seconds": 300},
                "reason": "validate_file_after_repo_write",
            }
        ] + ([
            {
                "tool": "repo_ruff_check",
                "arguments": {"paths": [rel], "timeout_seconds": 180},
                "reason": "python_static_validation_after_repo_write",
            }
        ] if rel.endswith(".py") else []),
    }
    artifact = root / "tool-results" / f"{now()}-repo_write_file.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload