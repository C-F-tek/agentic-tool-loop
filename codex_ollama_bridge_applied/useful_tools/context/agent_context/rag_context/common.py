"""Shared helpers for the internal RAG context provider."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = "output/ai_runtime_memory/rag/rag.sqlite"
DEFAULT_EMBEDDING_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_BATCH_SIZE = 8
DEFAULT_CHUNK_MIN_CHARS = 1500
DEFAULT_CHUNK_MAX_CHARS = 4000
DEFAULT_CHUNK_OVERLAP_CHARS = 300
DEFAULT_MAX_FILE_SIZE = 250000
DEFAULT_TOP_K = 20
DEFAULT_CHAR_BUDGET = 32000
DEFAULT_FUSION_K = 60

TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".css",
    ".go",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

JSON_MAX_FILE_SIZE = 80000
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".npucache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv314",
    "__pycache__",
    "bin",
    "build",
    "cache",
    "dist",
    "logs",
    "node_modules",
    "output",
    "renders",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".7z",
    ".bak",
    ".bin",
    ".bmp",
    ".db",
    ".dll",
    ".exe",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".pyc",
    ".pyd",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
    ".webp",
    ".zip",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def safe_id(value: str, default: str = "rag") -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("._:-")
    return normalized or default


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def resolve_repo_path(repo_root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path) -> tuple[str, str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if b"\x00" in data[:4096]:
        return "", "binary_nul_detected"
    try:
        return data.decode("utf-8-sig"), ""
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "utf8_replacement_used"


def language_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    return {
        ".md": "markdown",
        ".ps1": "powershell",
        ".py": "python",
        ".sql": "sql",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, suffix.lstrip(".") or "text")


def report_flags() -> dict[str, bool]:
    return {
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
    }


def db_path_warning(repo_root: Path, db_path: Path) -> str:
    rel = repo_rel(repo_root, db_path)
    if rel.startswith("output/") or rel.startswith("indexAI/") or db_path.suffix in {
        ".db",
        ".sqlite",
        ".sqlite3",
    }:
        return ""
    return f"rag db path is not obviously ignored by repo policy: {rel}"
