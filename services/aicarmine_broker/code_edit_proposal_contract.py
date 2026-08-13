"""Code edit proposal contract for bounded validation and evidence collection.

This module owns the canonical code edit proposal schema used by the broker's
structured_edit and unified_diff workflows. It validates target paths, generates
unified diffs, collects tree-sitter / AST / ast-grep evidence, and produces a
complete proposal payload for manual review or patch application.

Key responsibilities:
- Path normalization and validation against repository root
- Unified diff generation from old/new text pairs
- Structured operations normalization with preview-marker detection
- Tree-sitter parsing, Python AST anchor searching, and ast-grep evidence collection
- Complete proposal payload assembly with errors, warnings, and metadata
"""
from __future__ import annotations

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
    """Normalize a repo-relative path by stripping ./ prefix and normalizing separators.

    Args:
        value: The raw path string to normalize.
    Returns:
        The normalized path with forward slashes and ./ prefix stripped.
    """
    raw = str(value or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def target_path_errors(repo_root: Path, target_file: str) -> list[str]:
    """Validate target_file against repo_root and return any path errors.

    Checks for missing target, absolute paths, path traversal, forbidden
    locations (tool-results, .git, etc.), and outside-repo resolution.

    Args:
        repo_root: The repository root path.
        target_file: The relative file path to validate.
    Returns:
        A list of error strings if validation fails, empty list otherwise.
    """
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
    """Count physical lines in a text string.

    Args:
        text: The text to count lines in.
    Returns:
        The number of lines, handling empty strings and trailing newline correctly.
    """
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def default_validation_commands_for(target_file: str) -> list[str]:
    """Return default validation commands for a target file.

    Includes git diff --check and py_compile for Python files.

    Args:
        target_file: The relative path of the target file.
    Returns:
        A list of shell command strings for validation.
    """
    rel = normalize_repo_path(target_file)
    commands = ["git diff --check"]
    if rel.endswith(".py"):
        commands.append(f"python -m py_compile {rel}")
    return commands


def target_metadata(repo_root: Path, target_file: str) -> dict[str, Any]:
    """Compute metadata for a target file including size, sha256, and line count.

    Args:
        repo_root: The repository root path.
        target_file: The relative file path.
    Returns:
        A dictionary with target_file, exists, is_file, size_bytes, sha256, and line count.
    """
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
    target_file: str,
    old_text: str,
    new_text: str,
    fromfile_prefix: str = "a",
    tofile_prefix: str = "b",
) -> str:
    """Generate a unified diff between old_text and new_text for the target file.

    Uses difflib.unified_diff with proper file prefixes for the target path.

    Args:
        target_file: The relative path of the target file.
        old_text: The original text content.
        new_text: The new text content.
        fromfile_prefix: Prefix for the 'from' filename in the diff header.
        tofile_prefix: Prefix for the 'to' filename in the diff header.
    Returns:
        The unified diff string.
    """
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
    """Check if a value contains any preview/truncation markers.

    Used to detect incomplete code_product payloads that contain truncated content.

    Args:
        value: The value to check (string, dict, or list).
    Returns:
        True if any preview marker is found, False otherwise.
    """
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in PREVIEW_MARKERS)
    if isinstance(value, dict):
        return any(_contains_preview_marker(k) or _contains_preview_marker(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_preview_marker(item) for item in value)
    return False


def validate_unified_diff_text(
    
    unified_diff: str,
    target_file: str,
    require_unidiff: bool = True,
) -> list[str]:
    """Validate a unified diff string for completeness and correctness.

    Checks for missing diff text, preview markers, proper diff markers (---, +@@),
    target file presence in the diff, and optional unidiff parsing validation.

    Args:
        unified_diff: The unified diff string to validate.
        target_file: The expected target file path.
        require_unidiff: Whether to require unidiff dependency for parsing validation.
    Returns:
        A list of error strings if validation fails, empty list otherwise.
    """
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
            except Exception as exc:
                errors.append(f"unidiff_parse_failed:{type(exc).__name__}")
    return errors


def normalize_structured_operations(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize structured operations from a value, validating each operation.

    Checks that the value is a list of dicts, validates operation fields,
    and checks for preview markers indicating incomplete payloads.

    Args:
        value: The value to normalize (expected to be a list).
    Returns:
        A tuple of (valid_operations_list, errors_list).
    """
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
    """Parse a Python file with tree-sitter and return AST evidence.

    Requires tree_sitter and tree_sitter_python dependencies. Only supports 'python' language.

    Args:
        repo_root: The repository root path.
        target_file: The relative path of the Python file.
        language: The language identifier (must be 'python').
    Returns:
        A tuple of (evidence_dict, errors_list).
    """
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
    except Exception as exc:
        errors.append(f"tree_sitter_parse_failed:{type(exc).__name__}")
    return evidence, errors


def python_ast_anchor_evidence(repo_root: Path, target_file: str, ast_anchor: str) -> tuple[dict[str, Any], list[str]]:
    """Search Python AST for nodes matching an anchor name string.

    Parses the target file and walks the AST looking for nodes whose 'name'
    attribute matches the provided anchor string.

    Args:
        repo_root: The repository root path.
        target_file: The relative path of the Python file.
        ast_anchor: The anchor name string to search for.
    Returns:
        A tuple of (evidence_dict, errors_list).
    """
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
    """Run ast-grep search and return evidence.

    Requires ast-grep CLI. Searches for the pattern in the target file.

    Args:
        repo_root: The repository root path.
        target_file: The relative path of the target file.
        pattern: The ast-grep search pattern.
    Returns:
        A tuple of (evidence_dict, errors_list).
    """
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
    """Build a code edit proposal with validation evidence.

    Supports structured_edit, unified_diff, and no_op edit kinds.
    Collects validation evidence from tree-sitter, AST anchors, and ast-grep.

    Args:
        repo_root: The repository root path.
        target_file: The relative path of the target file.
        edit_kind: The type of edit (structured_edit, unified_diff, or no_op).
        rationale: The reason for the edit.
        unified_diff: The unified diff string (for unified_diff kind).
        structured_operations: List of structured operations (for structured_edit kind).
        old_text: The original text content.
        new_text: The new text content.
        validation_commands: List of validation command strings.
        require_unidiff: Whether to require unidiff dependency.
        ast_anchor: AST anchor name to search for.
        ast_grep_rule: ast-grep search pattern.
        tree_sitter_language: Language for tree-sitter parsing.
    Returns:
        A dictionary containing the proposal with all validation evidence.
    """
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
            except Exception as exc:
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