"""Repository path policy and read-candidate ranking helpers."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .path_tokens import repo_rel_token


SafeRelPath = Callable[[str], str]


def repo_existing_file(path: str, *, repo_root: Path, safe_rel_path: SafeRelPath) -> bool:
    try:
        rel = safe_rel_path(repo_rel_token(path))
        full = (repo_root / rel).resolve(strict=False)
        full.relative_to(repo_root)
        return full.exists() and full.is_file()
    except Exception:
        return False


def repo_existing_dir(path: str, *, repo_root: Path, safe_rel_path: SafeRelPath) -> bool:
    try:
        rel = safe_rel_path(repo_rel_token(path))
        full = (repo_root / rel).resolve(strict=False)
        full.relative_to(repo_root)
        return full.exists() and full.is_dir()
    except Exception:
        return False


def repo_path_kind(path: str, *, repo_root: Path) -> str:
    p = repo_rel_token(path)
    try:
        full = (repo_root / p).resolve(strict=False)
        full.relative_to(repo_root)
        if full.exists() and full.is_file():
            return "file"
        if full.exists() and full.is_dir():
            return "dir"
    except Exception:
        pass
    name = p.rsplit("/", 1)[-1].lower()
    if "." in name and not p.endswith("/"):
        return "file"
    return "dir"


def repo_doc_or_config(path: str, *, repo_root: Path) -> bool:
    p = repo_rel_token(path)
    if not p or p == "." or repo_path_kind(p, repo_root=repo_root) == "dir":
        return False
    name = p.rsplit("/", 1)[-1].lower()
    return (
        p.lower().endswith(".md")
        or name in {"pyproject.toml", "package.json", "requirements.txt", "setup.py", "setup.cfg", "tox.ini"}
        or name.startswith("modelfile")
        or name in {"makefile", "dockerfile"}
    )


def repo_code_file(path: str) -> bool:
    p = repo_rel_token(path).lower()
    return p.endswith((
        ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".cpp", ".c",
        ".h", ".cs", ".java", ".kt", ".swift", ".sh", ".bat", ".cmd",
    ))


def repo_readable_evidence_file(
    path: str,
    *,
    repo_root: Path,
    generic_readable_suffixes: Sequence[str],
) -> bool:
    p = repo_rel_token(path)
    if not p or p == "." or repo_path_kind(p, repo_root=repo_root) == "dir":
        return False
    return (
        repo_doc_or_config(p, repo_root=repo_root)
        or repo_code_file(p)
        or p.lower().endswith(tuple(generic_readable_suffixes))
    )


def path_under_scope(path: str, scope: str) -> bool:
    if not scope:
        return True
    p = repo_rel_token(path)
    s = repo_rel_token(scope).strip("/")
    if not s or s == ".":
        return True
    return p == s or p.startswith(s + "/")


def top_dir(path: str) -> str:
    p = repo_rel_token(path).strip("/")
    return p.split("/", 1)[0] if "/" in p else p


def low_signal_top_dir(path: str) -> bool:
    top = top_dir(path).lower()
    return (
        not top
        or top in {".git", ".github", ".vscode", ".codex", "__pycache__", ".pytest_cache"}
        or top in {"assets", "docs", "chatgpt", "examples", "patch_specs"}
        or top.endswith(".md")
    )


def read_candidate_sort_key(
    path: str,
    *,
    repo_root: Path,
    named_read_priority: Mapping[str, int],
) -> tuple[int, int, int, int, str]:
    p = repo_rel_token(path)
    low = p.lower()
    name = low.rsplit("/", 1)[-1]
    if name in named_read_priority:
        return (named_read_priority[name], 0, p.count("/"), 0, low)
    package_marker = name in {"__init__.py", "__main__.py"}
    fixture = "/fixtures/" in low or low.endswith("_fixture.json") or "/tests/fixtures/" in low
    if repo_code_file(p):
        kind_rank = 0
    elif repo_doc_or_config(p, repo_root=repo_root):
        kind_rank = 1
    else:
        kind_rank = 2
    area_rank = 0
    if "/_shared/" in low or low.startswith("ia_carmine/_shared/"):
        area_rank = 0
    elif low.startswith("ia_carmine/context/"):
        area_rank = 1
    elif low.startswith("ia_carmine/"):
        area_rank = 2
    penalty = 0
    if package_marker:
        penalty += 50
    if fixture:
        penalty += 40
    if low.endswith(".json") and not repo_doc_or_config(p, repo_root=repo_root):
        penalty += 10
    return (len(named_read_priority) + kind_rank, penalty, area_rank, p.count("/"), low)


def dynamic_read_candidate_paths(
    paths: list[str],
    *,
    read_ok: set[str] | None = None,
    target_scope: str = "",
    repo_root: Path,
    named_read_priority: Mapping[str, int],
    generic_readable_suffixes: Sequence[str],
) -> list[str]:
    already = read_ok or set()
    target_scope = repo_rel_token(target_scope)
    priority: list[str] = []
    regular: list[str] = []
    seen: set[str] = set()

    for raw in paths:
        p = repo_rel_token(raw)
        if not p or p in seen or p in already:
            continue
        if target_scope and not path_under_scope(p, target_scope):
            continue
        if not repo_readable_evidence_file(
            p,
            repo_root=repo_root,
            generic_readable_suffixes=generic_readable_suffixes,
        ):
            continue
        seen.add(p)
        name = p.rsplit("/", 1)[-1].lower()
        if name in named_read_priority:
            priority.append(p)
            continue
        regular.append(p)

    priority.sort(key=lambda p: (named_read_priority[p.rsplit("/", 1)[-1].lower()], p.count("/"), p.lower()))
    regular.sort(key=lambda p: read_candidate_sort_key(p, repo_root=repo_root, named_read_priority=named_read_priority))
    return priority + regular


def scope_candidate_source_paths(list_rows: list[dict[str, Any]], target_scope: str) -> list[str]:
    target_scope = repo_rel_token(target_scope)
    paths: list[str] = []
    if not target_scope:
        return paths
    for row in list_rows:
        for raw in row.get("paths_preview") or []:
            p = repo_rel_token(raw)
            if p and path_under_scope(p, target_scope) and p not in paths:
                paths.append(p)
    return paths


def scope_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    target_scope: str,
    *,
    read_ok: list[str] | set[str] | None = None,
    repo_root: Path,
    named_read_priority: Mapping[str, int],
    generic_readable_suffixes: Sequence[str],
) -> list[str]:
    already = set(read_ok or [])
    return dynamic_read_candidate_paths(
        scope_candidate_source_paths(list_rows, target_scope),
        read_ok=already,
        target_scope=target_scope,
        repo_root=repo_root,
        named_read_priority=named_read_priority,
        generic_readable_suffixes=generic_readable_suffixes,
    )


def meaningful_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    *,
    read_ok: list[str] | set[str] | None = None,
    repo_root: Path,
    named_read_priority: Mapping[str, int],
    generic_readable_suffixes: Sequence[str],
) -> list[str]:
    already = set(read_ok or [])
    out: list[str] = []
    for row in list_rows:
        area = repo_rel_token(row.get("path") or "")
        if area in ("", ".") or low_signal_top_dir(area):
            continue
        row_paths = [
            repo_rel_token(p)
            for p in (row.get("paths_preview") or [])
            if path_under_scope(repo_rel_token(p), area)
        ]
        for p in dynamic_read_candidate_paths(
            row_paths,
            read_ok=already,
            target_scope=area,
            repo_root=repo_root,
            named_read_priority=named_read_priority,
            generic_readable_suffixes=generic_readable_suffixes,
        ):
            if p not in out:
                out.append(p)
    return out
