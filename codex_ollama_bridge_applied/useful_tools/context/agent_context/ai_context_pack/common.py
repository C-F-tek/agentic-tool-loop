"""Path and text helpers for AI context packs."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

try:
    from Tools.validation._shared.report_utils import physical_line_count
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[4]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation._shared.report_utils import physical_line_count

from .profiles import FORBIDDEN_PATH_EXACT, FORBIDDEN_PATH_FRAGMENTS, FORBIDDEN_PATH_PREFIXES

def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()

def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()

def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")

def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = sanitized.strip("._-")
    return sanitized or "ai_context_pack"

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def context_unavailable_reason(entry: dict[str, Any]) -> str:
    """Return the most specific reason a context entry is unavailable."""
    return str(entry.get("policy_error") or entry.get("read_error") or "")

def path_escapes_repo(repo_root: Path, path: Path) -> bool:
    """Return true when a resolved path is outside the repository root."""
    try:
        path.relative_to(repo_root)
    except ValueError:
        return True
    return False

def path_policy_error(path: str) -> str | None:
    normalized = normalize_repo_path(path)
    if not normalized:
        return "empty path"
    if Path(normalized).is_absolute():
        return "absolute paths are not allowed in context profiles"
    if normalized in FORBIDDEN_PATH_EXACT:
        return f"forbidden exact path: {normalized}"
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES):
        return f"forbidden path prefix: {normalized}"
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_PATH_FRAGMENTS) and lower.endswith(".json"):
        return f"forbidden full-analysis JSON path: {normalized}"
    if "*" in normalized or normalized.endswith("/"):
        return "context profile entries must be concrete files"
    return None

def safe_read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except UnicodeDecodeError as exc:
        return None, f"text decode failed: {exc}"
    except OSError as exc:
        return None, str(exc)

def split_markdown_parts(path: Path) -> list[Path]:
    """Return ordered files for the canonical split Markdown directory layout.

    Supported layout:

        name.md/
          README.md
          part-001.md
          part-002.md
    """
    if not path.is_dir() or not path.name.endswith(".md"):
        return []
    parts: list[Path] = []
    readme = path / "README.md"
    if readme.is_file():
        parts.append(readme)
    parts.extend(sorted(item for item in path.glob("part-*.md") if item.is_file()))
    return parts

def safe_read_split_markdown(path: Path) -> tuple[str | None, str | None, int]:
    parts = split_markdown_parts(path)
    if not parts:
        return None, "path is not a file", 0

    chunks: list[str] = []
    total_size = 0
    for part in parts:
        text, error = safe_read_text(part)
        if error or text is None:
            return (
                None,
                f"split markdown read failed for {part.name}: {error}",
                total_size,
            )
        total_size += part.stat().st_size
        chunks.append(f"<!-- split-source: {part.name} -->\n{text.rstrip()}\n")
    return "\n".join(chunks), None, total_size
