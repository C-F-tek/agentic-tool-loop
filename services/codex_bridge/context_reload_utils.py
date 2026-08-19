"""Context reloading utilities for heap startup and dynamic GPU context management."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


CANONICAL_CONTEXT_FILES = (
    "AGENTS.md",
    "README.md",
    "WORKFLOW.md",
    "docs/README.md",
)

SEMANTIC_CHUNK_ROOTS = (
    

)

REPO_SCAN_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".venv314",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "renders",
    "output",
    "indexAI/code_chunks",
}

REPO_SCAN_TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".bat",
    ".sh",
}

STRICT_EFFECTIVE_REQUIREMENTS = {
    "rag_ollama_embed_preflight",
    "rag_repo_ingest",
    "rag_context_pack",
    "gpu1_dynamic_context_pack",
    "runtime_file_refs",
}


def now_stamp() -> str:
    """Return current timestamp string."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def read_request_file(repo_root: Path, value: str) -> str:
    """Read a request file relative to repo root."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.read_text(encoding="utf-8-sig", errors="replace")


def repo_rel(repo_root: Path, path: Path) -> str:
    """Return repository relative path."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path, max_chars: int = 6000) -> str:
    """Read text with truncation limit."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            return content[:max_chars] + "\n...[truncated]\n"
        return content
    except Exception:
        return ""


def read_json(path: Path) -> dict[str, Any]:
    """Read JSON file safely."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON file with formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(path: Path, text: str) -> None:
    """Write markdown file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def resolve_project_python(repo_root: Path, explicit: str = "") -> str:
    """Resolve project Python executable."""
    if explicit:
        return str(Path(explicit).resolve())
    for candidate in (
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / "venv" / "Scripts" / "python.exe",
        repo_root / ".venv314" / "Scripts" / "python.exe",
    ):
        if candidate.exists():
            return str(candidate.resolve())
    return sys.executable or "python"


def summarize_artifact(path: Path, repo_root: Path) -> dict[str, Any]:
    """Summarize an artifact file."""
    item: dict[str, Any] = {
        "path": repo_rel(repo_root, path),
        "exists": path.exists(),
        "size_bytes": None,
        "suffix": path.suffix.lower(),
        "json_ok": False,
        "json_passed": None,
        "kind": "",
        "useful": False,
    }
    if not path.exists() or not path.is_file():
        return item
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    item["size_bytes"] = size
    item["useful"] = size > 0
    if path.suffix.lower() == ".json" and size > 0:
        data = read_json(path)
        item["json_ok"] = bool(data)
        item["json_passed"] = data.get("passed") if data else None
        item["kind"] = str(data.get("kind") or data.get("report_kind") or "")
        if data:
            item["summary_fields"] = {
                key: data.get(key)
                for key in (
                    "passed",
                    "profile",
                    "included_file_count",
                    "truncated_file_count",
                    "provider_execution_performed",
                    "patch_application_performed",
                    "source_writes_performed",
                )
                if key in data
            }
    return item


def _strict_artifact_contract_passed(artifacts: list[dict[str, Any]]) -> bool:
    """Check if strict artifact contract is passed."""
    json_artifacts = [
        item for item in artifacts if str(item.get("suffix") or "").lower() == ".json"
    ]
    return bool(json_artifacts) and any(item.get("json_passed") is True for item in json_artifacts)


def effective_tool_status(
    *,
    requirement: str,
    returncode: int,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Determine effective tool status based on requirements and artifacts."""
    useful_artifacts = [item["path"] for item in artifacts if item.get("useful")]
    passed = returncode == 0
    strict_requirement = requirement in STRICT_EFFECTIVE_REQUIREMENTS
    artifact_contract_passed = _strict_artifact_contract_passed(artifacts)
    effective_passed = (
        passed and artifact_contract_passed
        if strict_requirement
        else passed or bool(useful_artifacts)
    )
    degraded = (
        (not passed) and bool(useful_artifacts) and not strict_requirement
    )
    return {
        "passed": passed,
        "effective_passed": effective_passed,
        "degraded": degraded,
        "hard_failed": not effective_passed and not degraded,
        "artifact_useful": bool(useful_artifacts),
        "strict_artifact_contract": strict_requirement,
        "artifact_contract_passed": artifact_contract_passed,
        "useful_artifact_paths": useful_artifacts,
    }


def run_tool(
    command: list[str],
    repo_root: Path,
    *,
    name: str,
    requirement: str,
    required: bool,
    artifact_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Run a tool and capture status."""
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    artifacts = [summarize_artifact(path, repo_root) for path in (artifact_paths or [])]
    existing_artifacts = [item["path"] for item in artifacts if item.get("exists")]
    status = effective_tool_status(
        requirement=requirement,
        returncode=completed.returncode,
        artifacts=artifacts,
    )
    return {
        "name": name,
        "requirement": requirement,
        "required": required,
        "command": command,
        "returncode": completed.returncode,
        "passed": status["passed"],
        "effective_passed": status["effective_passed"],
        "degraded": status["degraded"],
        "hard_failed": status["hard_failed"],
        "artifact_useful": status["artifact_useful"],
        "strict_artifact_contract": status["strict_artifact_contract"],
        "artifact_contract_passed": status["artifact_contract_passed"],
        "artifact_paths": [item["path"] for item in artifacts],
        "existing_artifact_paths": existing_artifacts,
        "useful_artifact_paths": status["useful_artifact_paths"],
        "artifact_summaries": artifacts,
        "stdout_tail": (completed.stdout or "")[-3000:],
        "stderr_tail": (completed.stderr or "")[-3000:],
    }


def sha256_text(text: str) -> str:
    """Return SHA-256 hash for text."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest() if text else ""


__all__ = [
    "CANONICAL_CONTEXT_FILES",
    "SEMANTIC_CHUNK_ROOTS",
    "REPO_SCAN_EXCLUDED_DIRS",
    "REPO_SCAN_TEXT_SUFFIXES",
    "STRICT_EFFECTIVE_REQUIREMENTS",
    "now_stamp",
    "read_request_file",
    "repo_rel",
    "read_text",
    "read_json",
    "write_json",
    "write_markdown",
    "resolve_project_python",
    "summarize_artifact",
    "effective_tool_status",
    "run_tool",
    "sha256_text",
]