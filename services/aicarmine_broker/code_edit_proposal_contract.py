from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import ast
import difflib
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


EDIT_KIND_STRUCTURED = "structured_edit"
EDIT_KIND_UNIFIED_DIFF = "unified_diff"
EDIT_KIND_NO_OP = "no_op"
ALLOWED_EDIT_KINDS = {EDIT_KIND_STRUCTURED, EDIT_KIND_UNIFIED_DIFF, EDIT_KIND_NO_OP}

FORBIDDEN_TARGET_FRAGMENTS = (
    "\\.git\\",
    "/.git/",
    "output/",
    "outputs/",
    "renders/",
    "artifacts/",
    "tool-results/",
    "reads/",
    "sqlite",
    ".db",
    ".sqlite",
)

PREVIEW_MARKERS = (
    "content_preview",
    "unified_diff_preview",
    "structured_operations_preview",
    "preview_only",
    "<truncated",
    "[truncated",
)


def normalize_repo_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def target_path_errors(repo_root: Path, target_file: str) -> list[str]:
    errors: list[str] = []
    rel = normalize_repo_path(target_file)
    if not rel:
        return ["target_file_missing"]
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        errors.append("target_file_must_be_repo_relative")
    if ".." in Path(rel).parts:
        errors.append("target_file_path_traversal")
    lowered = rel.lower()
    for fragment in FORBIDDEN_TARGET_FRAGMENTS:
        if fragment in lowered:
            errors.append("target_file_forbidden_location")
            break
    try:
        resolved = (repo_root / rel).resolve()
        root_resolved = repo_root.resolve()
        if root_resolved not in resolved.parents and resolved != root_resolved:
            errors.append("target_file_outside_repo")
    except Exception:
        errors.append("target_file_resolution_failed")
    return errors


def physical_line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def default_validation_commands_for(target_file: str) -> list[str]:
    rel = normalize_repo_path(target_file)
    commands = ["git diff --check"]
    if rel.endswith(".py"):
        commands.append(f"python -m py_compile {rel}")
    return commands


def target_metadata(repo_root: Path, target_file: str) -> dict[str, Any]:
    rel = normalize_repo_path(target_file)
    path = repo_root / rel
    meta: dict[str, Any] = {
        "target_file": rel,
        "exists": path.exists(),
        "is_file": path.is_file(),
    }
    if path.is_file():
        data = path.read_bytes()
        meta.update(
            {
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "physical_line_count": physical_line_count(data.decode("utf-8", errors="replace")),
            }
        )
    return meta


def generate_unified_diff_from_texts(
    *,
    target_file: str,
    old_text: str,
    new_text: str,
    fromfile_prefix: str = "a",
    tofile_prefix: str = "b",
) -> str:
    rel = normalize_repo_path(target_file)
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{fromfile_prefix}/{rel}",
            tofile=f"{tofile_prefix}/{rel}",
            lineterm="\n",
        )
    )


def _contains_preview_marker(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in PREVIEW_MARKERS)
    if isinstance(value, dict):
        return any(_contains_preview_marker(k) or _contains_preview_marker(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_preview_marker(item) for item in value)
    return False


def validate_unified_diff_text(
    *,
    unified_diff: str,
    target_file: str,
    require_unidiff: bool = True,
) -> list[str]:
    errors: list[str] = []
    diff_text = str(unified_diff or "")
    rel = normalize_repo_path(target_file)
    if not diff_text.strip():
        return ["unified_diff_missing"]
    if _contains_preview_marker(diff_text):
        errors.append("code_product_payload_not_complete")
    for marker in ("---", "+++", "@@"):
        if marker not in diff_text:
            errors.append("invalid_unified_diff_markers")
            break
    normalized = diff_text.replace("\\", "/")
    target_tokens = {rel, f"a/{rel}", f"b/{rel}"}
    if rel and not any(token in normalized for token in target_tokens):
        errors.append("unified_diff_target_missing")
    if require_unidiff:
        try:
            from unidiff import PatchSet  # type: ignore
        except Exception:
            errors.append("unidiff_dependency_missing")
        else:
            try:
                parsed = PatchSet(diff_text.splitlines(True))
                if not parsed:
                    errors.append("unidiff_parse_empty")
            except Exception:
                pass
                errors.append(f"unidiff_parse_failed:{type(exc).__name__}")
    return errors


def normalize_structured_operations(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if value is None:
        return [], ["structured_operations_missing"]
    if not isinstance(value, list):
        return [], ["structured_operations_must_be_list"]
    operations: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"structured_operation_{index}_must_be_object")
            continue
        op = dict(item)
        if _contains_preview_marker(op):
            errors.append("code_product_payload_not_complete")
        if not op.get("operation"):
            errors.append(f"structured_operation_{index}_operation_missing")
        operations.append(op)
    if not operations:
        errors.append("structured_operations_empty")
    return operations, errors


def tree_sitter_parse_evidence(repo_root: Path, target_file: str, language: str) -> tuple[dict[str, Any], list[str]]:
    rel = normalize_repo_path(target_file)
    evidence: dict[str, Any] = {"language": language, "target_file": rel}
    errors: list[str] = []
    if language != "python":
        return evidence, [f"tree_sitter_language_unsupported:{language}"]
    try:
        from tree_sitter import Language, Parser  # type: ignore
        import tree_sitter_python  # type: ignore
    except Exception:
        return evidence, ["tree_sitter_dependency_missing"]
    try:
        parser_language = Language(tree_sitter_python.language())
        try:
            parser = Parser(parser_language)
        except TypeError:
            parser = Parser()
            if hasattr(parser, "set_language"):
                parser.set_language(parser_language)
            else:
                parser.language = parser_language
        data = (repo_root / rel).read_bytes()
        tree = parser.parse(data)
        root = tree.root_node
        evidence.update(
            {
                "ok": not bool(root.has_error),
                "root_type": root.type,
                "has_error": bool(root.has_error),
                "node_count_estimate": root.named_child_count,
            }
        )
        if root.has_error:
            errors.append("tree_sitter_parse_error")
    except Exception:
        errors.append(f"tree_sitter_parse_failed:{type(exc).__name__}")
    return evidence, errors


def python_ast_anchor_evidence(repo_root: Path, target_file: str, ast_anchor: str) -> tuple[dict[str, Any], list[str]]:
    rel = normalize_repo_path(target_file)
    anchor = str(ast_anchor or "").strip()
    evidence: dict[str, Any] = {"target_file": rel, "anchor": anchor}
    if not anchor:
        return evidence, []
    try:
        text = (repo_root / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
    except Exception as exc:
        return evidence, [f"ast_anchor_parse_failed:{type(exc).__name__}"]
    matches: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        name = getattr(node, "name", None)
        if name == anchor:
            matches.append(
                {
                    "node_type": type(node).__name__,
                    "lineno": getattr(node, "lineno", None),
                    "end_lineno": getattr(node, "end_lineno", None),
                }
            )
    evidence["matches"] = matches
    evidence["ok"] = bool(matches)
    return evidence, ([] if matches else ["ast_anchor_not_found"])


def ast_grep_evidence(repo_root: Path, target_file: str, pattern: str) -> tuple[dict[str, Any], list[str]]:
    rel = normalize_repo_path(target_file)
    evidence: dict[str, Any] = {"target_file": rel, "pattern": pattern}
    if not pattern:
        return evidence, []
    exe = shutil.which("ast-grep") or shutil.which("sg")
    if not exe:
        return evidence, ["ast_grep_dependency_missing"]
    target = str((repo_root / rel).resolve())
    cmd = [exe, "run", "--pattern", pattern, target]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=20,
        )
    except Exception as exc:
        return evidence, [f"ast_grep_failed:{type(exc).__name__}"]
    evidence.update(
        {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "match_found": completed.returncode == 0 and bool(completed.stdout.strip()),
        }
    )
    if completed.returncode not in (0, 1):
        return evidence, [f"ast_grep_failed_returncode:{completed.returncode}"]
    if not evidence["match_found"]:
        return evidence, ["ast_grep_match_not_found"]
    return evidence, []


def build_code_edit_proposal(
    *,
    repo_root: Path,
    target_file: str,
    edit_kind: str,
    rationale: str,
    unified_diff: str | None = None,
    structured_operations: Any = None,
    old_text: str | None = None,
    new_text: str | None = None,
    validation_commands: list[str] | None = None,
    require_unidiff: bool = True,
    ast_anchor: str | None = None,
    ast_grep_rule: str | None = None,
    tree_sitter_language: str | None = None,
) -> dict[str, Any]:
    rel = normalize_repo_path(target_file)
    kind = str(edit_kind or "").strip()
    errors = target_path_errors(repo_root, rel)
    warnings: list[str] = []
    if kind not in ALLOWED_EDIT_KINDS:
        errors.append("edit_kind_invalid")
    rationale_text = str(rationale or "").strip()
    if not rationale_text:
        errors.append("rationale_missing")

    if kind == EDIT_KIND_UNIFIED_DIFF and not unified_diff and old_text is not None and new_text is not None:
        target_path = repo_root / rel
        if target_path.is_file():
            try:
                original_text = target_path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                pass
                errors.append(f"target_file_read_failed:{type(exc).__name__}")
            else:
                occurrences = original_text.count(old_text)
                if occurrences < 1:
                    errors.append("old_text_not_found_in_target")
                else:
                    updated_text = original_text.replace(old_text, new_text, 1)
                    unified_diff = generate_unified_diff_from_texts(
                        target_file=rel,
                        old_text=original_text,
                        new_text=updated_text,
                    )
                    if occurrences > 1:
                        warnings.append("old_text_multiple_occurrences_first_replaced")
        else:
            errors.append("target_file_not_found_for_old_text")

    normalized_operations: list[dict[str, Any]] = []
    if kind == EDIT_KIND_UNIFIED_DIFF:
        diff_errors = validate_unified_diff_text(
            unified_diff=str(unified_diff or ""),
            target_file=rel,
            require_unidiff=require_unidiff,
        )
        errors.extend(diff_errors)
        if any(str(error).startswith("unidiff_parse_failed:") for error in diff_errors):
            warnings.append("retry_with_exact_old_text_new_text_from_repo_read")
    elif kind == EDIT_KIND_STRUCTURED:
        normalized_operations, operation_errors = normalize_structured_operations(structured_operations)
        errors.extend(operation_errors)
    elif kind == EDIT_KIND_NO_OP:
        if unified_diff:
            errors.append("no_op_must_not_include_unified_diff")
        if structured_operations:
            errors.append("no_op_must_not_include_structured_operations")

    evidence: dict[str, Any] = {}
    if tree_sitter_language:
        tree_evidence, tree_errors = tree_sitter_parse_evidence(repo_root, rel, tree_sitter_language)
        evidence["tree_sitter"] = tree_evidence
        errors.extend(tree_errors)
    if ast_anchor:
        anchor_evidence, anchor_errors = python_ast_anchor_evidence(repo_root, rel, ast_anchor)
        evidence["ast_anchor"] = anchor_evidence
        errors.extend(anchor_errors)
    if ast_grep_rule:
        grep_evidence, grep_errors = ast_grep_evidence(repo_root, rel, ast_grep_rule)
        evidence["ast_grep"] = grep_evidence
        errors.extend(grep_errors)

    payload: dict[str, Any] = {
        "kind": "code_edit_proposal",
        "target_file": rel,
        "edit_kind": kind,
        "rationale": rationale_text,
        "source_writes_performed": False,
        "patch_application_performed": False,
        "manual_review_required": True,
        "validation_commands": validation_commands or default_validation_commands_for(rel),
        "target_metadata": target_metadata(repo_root, rel),
        "errors": errors,
        "warnings": warnings,
    }
    if kind == EDIT_KIND_UNIFIED_DIFF:
        payload["unified_diff"] = str(unified_diff or "")
    if kind == EDIT_KIND_STRUCTURED:
        payload["structured_operations"] = normalized_operations
    if evidence:
        payload["ast_evidence"] = evidence
    return payload
