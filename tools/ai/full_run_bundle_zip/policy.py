from __future__ import annotations

TEXT_SUFFIX_ALLOWLIST = {".json", ".md", ".csv", ".txt", ".log"}
DEFAULT_EVIDENCE_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"

FORBIDDEN_PREFIXES = (
    "output/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
    "renders/",
)

FORBIDDEN_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
    ".wav",
    ".mp3",
    ".aac",
    ".flac",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
)

FORBIDDEN_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)


def forbidden_reason(rel_path: str, *, allow_output: bool = False) -> str | None:
    """Return why a repository path is unsafe for the review ZIP."""
    rel = rel_path.replace("\\", "/").lstrip("./")
    lower = rel.lower()
    prefixes = FORBIDDEN_PREFIXES if not allow_output else tuple(
        prefix for prefix in FORBIDDEN_PREFIXES if prefix != "output/"
    )
    for prefix in prefixes:
        if lower.startswith(prefix.lower()):
            return f"forbidden prefix: {prefix}"
    for suffix in FORBIDDEN_SUFFIXES:
        if lower.endswith(suffix):
            return f"forbidden suffix: {suffix}"
    for fragment in FORBIDDEN_FRAGMENTS:
        if fragment in lower:
            return f"forbidden fragment: {fragment}"
    return None


def default_required_recursive_roots(stamp: str) -> list[str]:
    """Return default recursive evidence roots that must not be lost."""
    return [
        f"{DEFAULT_EVIDENCE_DIR}/full_toolbox_{stamp}_cloud_semantic_deterministic_chunks",
    ]
