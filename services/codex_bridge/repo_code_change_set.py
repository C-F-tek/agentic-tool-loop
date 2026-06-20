#!/usr/bin/env python3
"""Content-addressed unified-diff change sets for the repo-code MCP."""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
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
MAX_STRUCTURED_EDITS = 1000
CHANGE_SET_ID_RE = re.compile(r"^[0-9a-f]{64}$")
DIFF_ARGUMENT_NAMES = ("unified_diff", "diff", "patch")
STRUCTURED_EDIT_OPERATIONS = (
    "replace_exact",
    "insert_before_exact",
    "insert_after_exact",
    "create_file",
)


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


def _structured_text(
    edit: dict[str, Any],
    *,
    index: int,
    field: str,
    allow_empty: bool = True,
) -> str:
    value = edit.get(field)
    if not isinstance(value, str):
        raise ChangeSetError(
            "structured_edit_text_required",
            edit_index=index,
            field=field,
        )
    if not allow_empty and not value:
        raise ChangeSetError(
            "structured_edit_anchor_empty",
            edit_index=index,
            field=field,
        )
    if "\x00" in value:
        raise ChangeSetError(
            "structured_edit_non_text_content",
            edit_index=index,
            field=field,
        )
    return value


def _newline_policy(text: str) -> str:
    crlf_count = text.count("\r\n")
    lf_count = text.count("\n") - crlf_count
    cr_count = text.count("\r") - crlf_count
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


def _normalize_inserted_newlines(value: str, policy: str) -> str:
    if policy not in {"crlf", "lf", "cr"}:
        return value
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if policy == "crlf":
        return normalized.replace("\n", "\r\n")
    if policy == "cr":
        return normalized.replace("\n", "\r")
    return normalized


def _complete_unified_diff_lines(lines: list[str]) -> str:
    completed: list[str] = []
    for line in lines:
        if line.endswith("\n"):
            completed.append(line)
        elif line.endswith("\r"):
            completed.append(f"{line}\n")
        else:
            completed.append(f"{line}\n")
            completed.append("\\ No newline at end of file\n")
    return "".join(completed)


def _structured_file_diff(
    *,
    path: str,
    before: str,
    after: str,
    create_file: bool,
) -> str:
    git_header = f"diff --git a/{path} b/{path}\n"
    if create_file and not after:
        return (
            f"{git_header}"
            "new file mode 100644\n"
            "index 0000000..e69de29\n"
        )
    diff_lines = list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="/dev/null" if create_file else f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
        )
    )
    if not diff_lines:
        return ""
    mode_header = "new file mode 100644\n" if create_file else ""
    return f"{git_header}{mode_header}{_complete_unified_diff_lines(diff_lines)}"


def build_structured_edit_diff(
    root: Path,
    edits: Any,
) -> dict[str, Any]:
    if not isinstance(edits, list):
        raise ChangeSetError("structured_edits_must_be_list")
    if not edits:
        raise ChangeSetError("structured_edits_empty")
    if len(edits) > MAX_STRUCTURED_EDITS:
        raise ChangeSetError(
            "structured_edit_count_above_maximum",
            maximum=MAX_STRUCTURED_EDITS,
            actual=len(edits),
        )

    states: dict[str, dict[str, Any]] = {}
    for index, raw_edit in enumerate(edits):
        if not isinstance(raw_edit, dict):
            raise ChangeSetError(
                "structured_edit_must_be_object",
                edit_index=index,
            )
        edit = dict(raw_edit)
        raw_path = edit.get("path")
        if not isinstance(raw_path, str):
            raise ChangeSetError(
                "structured_edit_path_required",
                edit_index=index,
            )
        relative_path, full_path = _safe_target_path(root, raw_path)
        operation = str(edit.get("operation") or "").strip()
        if operation not in STRUCTURED_EDIT_OPERATIONS:
            raise ChangeSetError(
                "structured_edit_operation_invalid",
                edit_index=index,
                operation=operation,
                allowed=list(STRUCTURED_EDIT_OPERATIONS),
            )

        state = states.get(relative_path)
        if operation == "create_file":
            if state is not None or full_path.exists():
                raise ChangeSetError(
                    "structured_edit_create_target_exists",
                    edit_index=index,
                    path=relative_path,
                )
            content = _structured_text(
                edit,
                index=index,
                field="content",
            )
            states[relative_path] = {
                "path": relative_path,
                "original": "",
                "current": content,
                "create_file": True,
                "newline_policy": _newline_policy(content),
                "operations": [operation],
            }
            if len(states) > MAX_DIFF_FILES:
                raise ChangeSetError(
                    "structured_edit_file_count_above_maximum",
                    maximum=MAX_DIFF_FILES,
                    actual=len(states),
                )
            continue

        if state is None:
            if not full_path.exists():
                raise ChangeSetError(
                    "structured_edit_target_not_found",
                    edit_index=index,
                    path=relative_path,
                )
            if not full_path.is_file():
                raise ChangeSetError(
                    "structured_edit_target_not_file",
                    edit_index=index,
                    path=relative_path,
                )
            raw_bytes = full_path.read_bytes()
            try:
                original = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ChangeSetError(
                    "structured_edit_target_not_utf8",
                    edit_index=index,
                    path=relative_path,
                ) from exc
            state = {
                "path": relative_path,
                "original": original,
                "current": original,
                "create_file": False,
                "newline_policy": _newline_policy(original),
                "operations": [],
            }
            states[relative_path] = state
            if len(states) > MAX_DIFF_FILES:
                raise ChangeSetError(
                    "structured_edit_file_count_above_maximum",
                    maximum=MAX_DIFF_FILES,
                    actual=len(states),
                )

        expected = edit.get("expected_occurrences", 1)
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            raise ChangeSetError(
                "structured_edit_expected_occurrences_invalid",
                edit_index=index,
                path=relative_path,
                actual=expected,
            )

        if operation == "replace_exact":
            anchor_field = "old_text"
            replacement_field = "new_text"
        else:
            anchor_field = "anchor"
            replacement_field = "content"
        anchor = _structured_text(
            edit,
            index=index,
            field=anchor_field,
            allow_empty=False,
        )
        replacement = _structured_text(
            edit,
            index=index,
            field=replacement_field,
        )
        replacement = _normalize_inserted_newlines(
            replacement,
            str(state["newline_policy"]),
        )

        current = str(state["current"])
        occurrences = current.count(anchor)
        if occurrences == 0:
            raise ChangeSetError(
                "structured_edit_anchor_not_found",
                edit_index=index,
                path=relative_path,
                expected_occurrences=expected,
                actual_occurrences=0,
            )
        if occurrences > expected:
            raise ChangeSetError(
                "structured_edit_ambiguous",
                edit_index=index,
                path=relative_path,
                expected_occurrences=expected,
                actual_occurrences=occurrences,
            )
        if occurrences != expected:
            raise ChangeSetError(
                "structured_edit_occurrence_mismatch",
                edit_index=index,
                path=relative_path,
                expected_occurrences=expected,
                actual_occurrences=occurrences,
            )

        if operation == "replace_exact":
            updated = current.replace(anchor, replacement, expected)
        elif operation == "insert_before_exact":
            updated = current.replace(anchor, f"{replacement}{anchor}", expected)
        else:
            updated = current.replace(anchor, f"{anchor}{replacement}", expected)
        if updated == current:
            raise ChangeSetError(
                "structured_edit_no_change",
                edit_index=index,
                path=relative_path,
            )
        state["current"] = updated
        state["operations"].append(operation)

    diff_parts: list[str] = []
    files: list[dict[str, Any]] = []
    for state in states.values():
        before = str(state["original"])
        after = str(state["current"])
        if before == after:
            raise ChangeSetError(
                "structured_edit_no_change",
                path=state["path"],
            )
        file_diff = _structured_file_diff(
            path=str(state["path"]),
            before=before,
            after=after,
            create_file=bool(state["create_file"]),
        )
        if not file_diff:
            raise ChangeSetError(
                "structured_edit_diff_empty",
                path=state["path"],
            )
        diff_parts.append(file_diff)
        files.append(
            {
                "path": state["path"],
                "change_type": "added" if state["create_file"] else "modified",
                "operation_count": len(state["operations"]),
                "operations": list(state["operations"]),
                "newline_policy": state["newline_policy"],
            }
        )

    normalized_diff = normalize_unified_diff_text("".join(diff_parts))
    return {
        "unified_diff": normalized_diff,
        "edit_count": len(edits),
        "file_count": len(files),
        "files": files,
    }


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


def inspect_unified_diff(
    root: Path,
    diff_text: str,
    *,
    capture_preimages: bool = True,
) -> dict[str, Any]:
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
        file_info: dict[str, Any] = {
            "path": relative_path,
            "change_type": "added" if patched.is_added_file else "modified",
            "added": patched.added,
            "removed": patched.removed,
            "hunks": len(patched),
        }
        if capture_preimages:
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
            before_bytes = (
                full_path.read_bytes()
                if exists and full_path.is_file()
                else b""
            )
            file_info.update(
                {
                    "preimage_exists": exists,
                    "preimage_sha256": (
                        _sha256_bytes(before_bytes) if exists else None
                    ),
                    "preimage_bytes": len(before_bytes),
                    "preimage_line_count": _line_count(before_bytes),
                }
            )
        files.append(file_info)

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

    inspection = inspect_unified_diff(
        root,
        patch_bytes.decode("utf-8"),
        capture_preimages=False,
    )
    if metadata.get("diff_bytes") != len(patch_bytes):
        raise ChangeSetError("change_set_metadata_diff_bytes_mismatch")
    if metadata.get("file_count") != inspection["file_count"]:
        raise ChangeSetError("change_set_metadata_file_count_mismatch")
    metadata_files = metadata.get("files")
    if not isinstance(metadata_files, list) or len(metadata_files) != inspection["file_count"]:
        raise ChangeSetError("change_set_metadata_files_invalid")
    static_keys = ("path", "change_type", "added", "removed", "hunks")
    for expected, actual in zip(metadata_files, inspection["files"], strict=True):
        if not isinstance(expected, dict) or any(
            expected.get(key) != actual.get(key) for key in static_keys
        ):
            raise ChangeSetError("change_set_metadata_files_mismatch")
    return {
        "ok": True,
        "change_set_id": change_set_id,
        "diff_sha256": diff_sha256,
        "file_count": inspection["file_count"],
        "files": metadata_files,
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
