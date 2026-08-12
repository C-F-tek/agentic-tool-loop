"""Constants for repository consistency mapping."""

from __future__ import annotations

import re

DEFAULT_OUTPUT = "output/analysis/repository_consistency_map.json"
DEFAULT_MARKDOWN = "output/analysis/repository_consistency_map.md"
DEFAULT_MAX_SNIPPET_CHARS = 220
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "output",
    "renders",
    ".mypy_cache",
    ".pytest_cache",
}
TEXT_EXTENSIONS = {".md", ".markdown", ".py", ".ps1"}
SCRIPT_EXTENSIONS = {".py", ".ps1"}
DOC_EXTENSIONS = {".md", ".markdown"}
GENERATED_EVIDENCE_CHUNK_RE = re.compile(
    r"(^|/)docs/local_validation_evidence/.*(?:_cloud_semantic(?:_deterministic)?_chunks/|_chunks/|_chunk_\d{4}\.md$)",
    re.IGNORECASE,
)
PATH_TOKEN_RE = re.compile(
    r"(?P<path>(?:\.?[A-Za-z0-9_./\\-]+/)?[A-Za-z0-9_.-]+\.(?:py|ps1|md|markdown|json|csv|sqlite|db))",
    re.IGNORECASE,
)
PY_COMMAND_RE = re.compile(
    r"(?:^|[\s`>])(?P<python>python(?:\.exe)?|py)\s+(?P<script>[A-Za-z0-9_./\\-]+\.py)(?P<args>[^\n`]*)",
    re.IGNORECASE,
)
FLAG_RE = re.compile(r"(?<![\w-])--[A-Za-z0-9][A-Za-z0-9_-]*")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<link>[^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
