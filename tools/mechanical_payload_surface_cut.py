from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "services"

TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
}

SKIP_DIRS = {
    ".git",
    ".runs",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "venvs",
    "node_modules",
    "openwebui-data",
    "npu-models",
}

SKIP_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".exr",
    ".blend",
    ".pyc",
}

MAX_FILE_BYTES = 2_000_000

DROP_LINE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r'^\s*["\'](?:agent_context_for_30b|structured_context_for_30b|structured_result_for_30b)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:tool_result_for|called_by_30b|job_ok)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:content_sha256|final_path_sha256|json_sha256)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:final_path_mtime|final_path_size_bytes|json_chars)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:role|navigation_hint|purpose)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:full_context_location)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:events_tail_digest|history_schema|history_count)["\']\s*:\s*.*?,?\s*$',
        r'^\s*["\'](?:ExpectTool|LOOP_PAYLOAD_EXPECT_TOOL|expect_tool|expected_tool)["\']\s*:\s*.*?,?\s*$',
        r'^\s*\[string\]\$ExpectTool\s*=.*$',
        r'^.*LOOP_PAYLOAD_EXPECT_TOOL.*$',
        r'^.*-ExpectTool.*$',
    )
)

DROP_PYTHON_FUNCTIONS = {
    "_agentic_v9_build_payload_index_for_30b",
    "_agentic_v9_build_external_tool_context_for_30b",
}

DROP_IMPORT_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^\s*from\s+\.application\.materialization_report\s+import\s+build_materialization_report\s*$",
    )
)


def iter_targets() -> list[Path]:
    out: list[Path] = []
    for path in TARGET_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        out.append(path)
    return sorted(out)


def cut_python_functions(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    skipping = False
    skip_indent = ""
    for line in lines:
        if not skipping:
            match = re.match(r"^(\s*)def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
            if match and match.group(2) in DROP_PYTHON_FUNCTIONS:
                skipping = True
                skip_indent = match.group(1)
                removed += 1
                continue
            out.append(line)
            continue

        if line.strip() == "":
            continue
        starts_next_block = (
            line.startswith(skip_indent)
            and not line.startswith(skip_indent + " ")
            and not line.startswith(skip_indent + "\t")
        )
        if starts_next_block:
            skipping = False
            out.append(line)
    return "".join(out), removed


def cut_lines(text: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if any(pattern.search(bare) for pattern in DROP_LINE_PATTERNS):
            removed += 1
            continue
        if any(pattern.search(bare) for pattern in DROP_IMPORT_PATTERNS):
            removed += 1
            continue
        out.append(line)
    return "".join(out), removed


def apply_file(path: Path) -> dict[str, object]:
    before = path.read_text(encoding="utf-8", errors="replace")
    after, removed_lines = cut_lines(before)
    removed_functions = 0
    if path.suffix.lower() == ".py":
        after, removed_functions = cut_python_functions(after)
    changed = before != after
    if changed:
        path.write_text(after, encoding="utf-8", newline="")
    return {
        "path": str(path.relative_to(ROOT)),
        "changed": changed,
        "removed_lines": removed_lines,
        "removed_functions": removed_functions,
    }


def main() -> int:
    results = [apply_file(path) for path in iter_targets()]
    changed = [row for row in results if row["changed"]]
    report = {
        "schema": "mechanical_payload_surface_cut_report.v1",
        "mode": "apply",
        "root": str(ROOT),
        "target_root": str(TARGET_ROOT),
        "files_scanned": len(results),
        "files_changed": len(changed),
        "changed": changed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
