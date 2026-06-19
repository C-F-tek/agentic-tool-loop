#!/usr/bin/env python3
"""Content-addressed unified-diff change sets for the repo-code MCP."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import uuid4


CHANGE_SET_SCHEMA = "aicarmine.repo_code.change_set.v1"
MAX_DIFF_BYTES = 2 * 1024 * 1024
MAX_DIFF_FILES = 100
CHANGE_SET_ID_RE = re.compile(r"^[0-9a-f]{64}$")
DIFF_ARGUMENT_NAMES = ("unified_diff", "diff", "patch")


class ChangeSetError(ValueError):
    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def normalize_unified_diff_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def inline_diff_from_args(args: dict[str, Any]) -> str:
    values = [
        normalize_unified_diff_text(value)
        for name in DIFF_ARGUMENT_NAMES
        if isinstance((value := args.get(name)), str) and value.strip()
    ]
    if not values:
        return ""
    first = values[0]
    if any(value != first for value in values[1:]):
        raise ChangeSetError("ambiguous_diff_arguments")
    return first


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise ChangeSetError(
            "change_set_git_head_unavailable",
            stderr=completed.stderr[-1000:],
        )
    return completed.stdout.strip()


def _strip_patch_prefix(value: Any) -> str:
    text = str(value or "").strip().split("\t", 1)[0].replace("\\", "/")
    if text in {"/dev/null", "dev/null"}:
        return ""
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    while text.startswith("./"):
        text = text[2:]
    return text


def _safe_target_path(root: Path, path: str) -> tuple[str, Path]:
    from aicarmine_broker.code_edit_proposal_contract import target_path_errors

    normalized = path.replace("\\", "/").strip()
    errors = target_path_errors(root, normalized)
    if errors:
        raise ChangeSetError(
            "change_set_unsafe_path",
            path=normalized,
            path_errors=errors,
        )
    full = (root / normalized).resolve(strict=False)
    try:
        full.relative_to(root.resolve())
    except ValueError as exc:
        raise ChangeSetError("change_set_path_outside_repo", path=normalized) from exc
    return normalized, full


def _line_count(data: bytes) -> int:
    text = data.decode("utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def inspect_unified_diff(root: Path, diff_text: str) -> dict[str, Any]:
    try:
        from unidiff import PatchSet
    except Exception as exc:
        raise ChangeSetError(
            "unidiff_dependency_missing",
            error_type=type(exc).__name__,
        ) from exc

    normalized = normalize_unified_diff_text(diff_text)
    diff_bytes = normalized.encode("utf-8")
    if not normalized.strip():
        raise ChangeSetError("missing_unified_diff")
    if len(diff_bytes) > MAX_DIFF_BYTES:
        raise ChangeSetError(
            "unified_diff_above_maximum",
            maximum=MAX_DIFF_BYTES,
            actual=len(diff_bytes),
        )
    if "GIT binary patch" in normalized or "Binary files " in normalized:
        raise ChangeSetError("binary_patch_not_supported")
    if re.search(r"(?m)^rename (?:from|to) ", normalized):
        raise ChangeSetError("rename_patch_not_supported")

    try:
        patch = PatchSet(normalized.splitlines(True))
    except Exception as exc:
        raise ChangeSetError(
            "unidiff_parse_error",
            error_type=type(exc).__name__,
            message=str(exc)[:500],
        ) from exc
    if not patch:
        raise ChangeSetError("unidiff_parse_empty")
    if len(patch) > MAX_DIFF_FILES:
        raise ChangeSetError(
            "unified_diff_file_count_above_maximum",
            maximum=MAX_DIFF_FILES,
            actual=len(patch),
        )

    files: list[dict[str, Any]] = []
    for patched in patch:
        if bool(getattr(patched, "is_binary_file", False)):
            raise ChangeSetError("binary_patch_not_supported")
        if patched.is_removed_file:
            raise ChangeSetError(
                "removed_file_patch_not_supported",
                path=_strip_patch_prefix(patched.source_file),
            )

        source_path = _strip_patch_prefix(patched.source_file)
        target_path = _strip_patch_prefix(patched.target_file)
        if not target_path:
            raise ChangeSetError("change_set_target_path_missing")
        if source_path and source_path != target_path:
            raise ChangeSetError(
                "rename_patch_not_supported",
                source_path=source_path,
                target_path=target_path,
            )

        relative_path, full_path = _safe_target_path(root, target_path)
        exists = full_path.exists()
        if patched.is_added_file and exists:
            raise ChangeSetError(
                "added_file_already_exists",
                path=relative_path,
            )
        if not patched.is_added_file and (not exists or not full_path.is_file()):
            raise ChangeSetError(
                "modified_file_not_found",
                path=relative_path,
            )

        before_bytes = full_path.read_bytes() if exists and full_path.is_file() else b""
        files.append(
            {
                "path": relative_path,
                "change_type": "added" if patched.is_added_file else "modified",
                "added": patched.added,
                "removed": patched.removed,
                "hunks": len(patched),
                "preimage_exists": exists,
                "preimage_sha256": _sha256_bytes(before_bytes) if exists else None,
                "preimage_bytes": len(before_bytes),
                "preimage_line_count": _line_count(before_bytes),
            }
        )

    return {
        "normalized_diff": normalized,
        "diff_bytes": len(diff_bytes),
        "diff_sha256": _sha256_bytes(diff_bytes),
        "file_count": len(files),
        "files": files,
    }


def _change_set_root(root: Path) -> Path:
    return root / "state" / "repo_code" / "change_sets"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _change_set_id(root: Path, base_commit: str, diff_sha256: str) -> str:
    identity = (
        f"{CHANGE_SET_SCHEMA}\0{root.resolve()}\0{base_commit}\0{diff_sha256}"
    ).encode("utf-8")
    return _sha256_bytes(identity)


def materialize_change_set(root: Path, diff_text: str) -> dict[str, Any]:
    root = root.resolve()
    inspection = inspect_unified_diff(root, diff_text)
    base_commit = _git_head(root)
    change_set_id = _change_set_id(root, base_commit, inspection["diff_sha256"])
    directory = _change_set_root(root)
    patch_path = directory / f"{change_set_id}.patch"
    metadata_path = directory / f"{change_set_id}.json"

    metadata = {
        "schema": CHANGE_SET_SCHEMA,
        "change_set_id": change_set_id,
        "diff_sha256": inspection["diff_sha256"],
        "repo_root": str(root),
        "base_commit": base_commit,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "diff_bytes": inspection["diff_bytes"],
        "file_count": inspection["file_count"],
        "files": inspection["files"],
    }
    patch_bytes = inspection["normalized_diff"].encode("utf-8")

    if patch_path.exists() and _sha256_bytes(patch_path.read_bytes()) != inspection["diff_sha256"]:
        raise ChangeSetError("change_set_patch_hash_conflict", change_set_id=change_set_id)
    if not patch_path.exists():
        _atomic_write(patch_path, patch_bytes)
    if not metadata_path.exists():
        _atomic_write(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return _load_change_set(root, change_set_id)


def _load_change_set(root: Path, change_set_id: str) -> dict[str, Any]:
    if not CHANGE_SET_ID_RE.fullmatch(change_set_id):
        raise ChangeSetError("invalid_change_set_id")
    root = root.resolve()
    directory = _change_set_root(root)
    patch_path = directory / f"{change_set_id}.patch"
    metadata_path = directory / f"{change_set_id}.json"
    if not patch_path.is_file() or not metadata_path.is_file():
        raise ChangeSetError("change_set_not_found", change_set_id=change_set_id)

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ChangeSetError(
            "change_set_metadata_invalid",
            error_type=type(exc).__name__,
        ) from exc
    if not isinstance(metadata, dict) or metadata.get("schema") != CHANGE_SET_SCHEMA:
        raise ChangeSetError("change_set_metadata_schema_invalid")
    if metadata.get("change_set_id") != change_set_id:
        raise ChangeSetError("change_set_metadata_id_mismatch")
    if Path(str(metadata.get("repo_root") or "")).resolve() != root:
        raise ChangeSetError("change_set_repo_root_mismatch")

    patch_bytes = patch_path.read_bytes()
    diff_sha256 = _sha256_bytes(patch_bytes)
    if diff_sha256 != metadata.get("diff_sha256"):
        raise ChangeSetError("change_set_patch_hash_mismatch")
    current_commit = _git_head(root)
    if current_commit != metadata.get("base_commit"):
        raise ChangeSetError(
            "change_set_base_commit_mismatch",
            expected=metadata.get("base_commit"),
            actual=current_commit,
        )
    expected_id = _change_set_id(root, current_commit, diff_sha256)
    if expected_id != change_set_id:
        raise ChangeSetError("change_set_identity_mismatch")

    inspection = inspect_unified_diff(root, patch_bytes.decode("utf-8"))
    if metadata.get("diff_bytes") != len(patch_bytes):
        raise ChangeSetError("change_set_metadata_diff_bytes_mismatch")
    if metadata.get("file_count") != inspection["file_count"]:
        raise ChangeSetError("change_set_metadata_file_count_mismatch")
    if metadata.get("files") != inspection["files"]:
        raise ChangeSetError("change_set_metadata_files_mismatch")
    return {
        "ok": True,
        "change_set_id": change_set_id,
        "diff_sha256": diff_sha256,
        "file_count": inspection["file_count"],
        "files": inspection["files"],
        "base_commit": current_commit,
        "diff_bytes": len(patch_bytes),
        "normalized_diff": inspection["normalized_diff"],
        "metadata": metadata,
        "change_set_path": str(patch_path),
        "change_set_metadata_path": str(metadata_path),
    }


def resolve_change_set(args: dict[str, Any], root: Path) -> dict[str, Any]:
    change_set_id = str(args.get("change_set_id") or "").strip().lower()
    inline_diff = inline_diff_from_args(args)
    if not change_set_id and not inline_diff:
        raise ChangeSetError("missing_unified_diff_or_change_set_id")

    if change_set_id:
        resolved = _load_change_set(root, change_set_id)
        if inline_diff:
            inline_sha256 = _sha256_bytes(inline_diff.encode("utf-8"))
            if inline_sha256 != resolved["diff_sha256"]:
                raise ChangeSetError(
                    "change_set_diff_mismatch",
                    change_set_id=change_set_id,
                )
        return resolved
    return materialize_change_set(root, inline_diff)


def verify_change_set_preimages(root: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for item in metadata.get("files") if isinstance(metadata.get("files"), list) else []:
        if not isinstance(item, dict):
            continue
        relative_path, full_path = _safe_target_path(root, str(item.get("path") or ""))
        expected_exists = bool(item.get("preimage_exists"))
        actual_exists = full_path.is_file()
        actual_sha256 = _sha256_bytes(full_path.read_bytes()) if actual_exists else None
        if actual_exists != expected_exists or actual_sha256 != item.get("preimage_sha256"):
            mismatches.append(
                {
                    "path": relative_path,
                    "expected_exists": expected_exists,
                    "actual_exists": actual_exists,
                    "expected_sha256": item.get("preimage_sha256"),
                    "actual_sha256": actual_sha256,
                }
            )
    return mismatches


def public_change_set_fields(change_set: dict[str, Any], stage: str) -> dict[str, Any]:
    return {
        "change_set_id": change_set["change_set_id"],
        "diff_sha256": change_set["diff_sha256"],
        "file_count": change_set["file_count"],
        "change_set_stage": stage,
        "base_commit": change_set["base_commit"],
        "diff_bytes": change_set["diff_bytes"],
        "change_set_files": change_set["files"],
        "change_set_path": change_set["change_set_path"],
        "change_set_metadata_path": change_set["change_set_metadata_path"],
    }


def change_set_error_payload(tool: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ChangeSetError):
        return {
            "ok": False,
            "tool": tool,
            "error": exc.code,
            **exc.details,
        }
    return {
        "ok": False,
        "tool": tool,
        "error": "change_set_failed",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }
