"""Markdown reference extraction for repository consistency maps."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from Tools.ai.repository_consistency_map.constants import (
    BACKTICK_RE,
    DOC_EXTENSIONS,
    FLAG_RE,
    MD_LINK_RE,
    PATH_TOKEN_RE,
    PY_COMMAND_RE,
    TEXT_EXTENSIONS,
)
from Tools.ai.repository_consistency_map.paths import (
    bounded_worker_count,
    iter_files,
    line_for_offset,
    normalize_ref,
    read_text,
    repo_rel,
    resolve_repo_reference,
    snippet_for_line,
)


def extract_markdown_references(
    repo_root: Path,
    path_index: dict[str, str],
    *,
    max_snippet_chars: int,
    workers: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    references: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    warnings: list[str] = []
    markdown_files = iter_files(repo_root, DOC_EXTENSIONS)

    def scan_markdown_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        file_references: list[dict[str, Any]] = []
        file_commands: list[dict[str, Any]] = []
        file_warnings: list[str] = []
        rel = repo_rel(path, repo_root)
        text, error = read_text(path)
        if error:
            file_warnings.append(f"{rel}: {error}")
            return file_references, file_commands, file_warnings
        seen_refs: set[tuple[str, int]] = set()
        candidates: list[tuple[str, int]] = []
        for match in PATH_TOKEN_RE.finditer(text):
            candidates.append((match.group("path"), match.start()))
        for match in MD_LINK_RE.finditer(text):
            link = match.group("link").split("#", 1)[0]
            if Path(link).suffix.lower() in TEXT_EXTENSIONS | {".json", ".csv"}:
                candidates.append((link, match.start()))
        for match in BACKTICK_RE.finditer(text):
            value = match.group(1).strip()
            if Path(value).suffix.lower() in TEXT_EXTENSIONS | {".json", ".csv"}:
                candidates.append((value, match.start()))
        for raw_ref, offset in candidates:
            line_no = line_for_offset(text, offset)
            key = (normalize_ref(raw_ref), line_no)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            resolved, exists, mode = resolve_repo_reference(repo_root, rel, raw_ref, path_index)
            ext = Path(normalize_ref(raw_ref)).suffix.lower()
            kind = "python" if ext == ".py" else "powershell" if ext == ".ps1" else "markdown" if ext in DOC_EXTENSIONS else "artifact"
            file_references.append(
                {
                    "source": rel,
                    "line": line_no,
                    "raw_ref": normalize_ref(raw_ref),
                    "resolved": resolved,
                    "exists": exists,
                    "resolution": mode,
                    "kind": kind,
                    "snippet": snippet_for_line(text, line_no, max_chars=max_snippet_chars),
                }
            )
        for match in PY_COMMAND_RE.finditer(text):
            line_no = line_for_offset(text, match.start())
            script_raw = normalize_ref(match.group("script"))
            resolved, exists, mode = resolve_repo_reference(repo_root, rel, script_raw, path_index)
            args_text = match.group("args") or ""
            flags = sorted(set(FLAG_RE.findall(args_text)))
            file_commands.append(
                {
                    "source": rel,
                    "line": line_no,
                    "script_raw": script_raw,
                    "script_resolved": resolved,
                    "script_exists": exists,
                    "resolution": mode,
                    "flags": flags,
                    "snippet": snippet_for_line(text, line_no, max_chars=max_snippet_chars),
                }
            )
        return file_references, file_commands, file_warnings

    worker_count = bounded_worker_count(workers, len(markdown_files))
    if worker_count > 1:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for file_references, file_commands, file_warnings in executor.map(scan_markdown_file, markdown_files):
                references.extend(file_references)
                commands.extend(file_commands)
                warnings.extend(file_warnings)
    else:
        for path in markdown_files:
            file_references, file_commands, file_warnings = scan_markdown_file(path)
            references.extend(file_references)
            commands.extend(file_commands)
            warnings.extend(file_warnings)
    return references, commands, warnings
