from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_MAX_LINES = 400
DEFAULT_INCLUDE_SUFFIXES = (
    ".md",
    ".py",
    ".ps1",
    ".psm1",
    ".psd1",
    ".sh",
    ".bat",
    ".cmd",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
)
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "output",
    "renders",
    "indexAI/code_chunks",
    "indexAI/project_code_chunks",
}


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def normalize_rel(path: Path, repo_root: Path) -> str:
    return repo_relative(path, repo_root).replace("\\", "/").lstrip("./")


def split_csv(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            item = part.strip()
            if item and item not in out:
                out.append(item)
    return out


def is_excluded(path: Path, repo_root: Path, excluded_dirs: set[str]) -> bool:
    rel = normalize_rel(path, repo_root)
    parts = rel.split("/")
    for excluded in excluded_dirs:
        ex = excluded.strip("/")
        if not ex:
            continue
        if rel == ex or rel.startswith(ex + "/"):
            return True
        if "/" not in ex and ex in parts:
            return True
    return False


def iter_candidate_files(repo_root: Path, suffixes: tuple[str, ...], excluded_dirs: set[str]) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path, repo_root, excluded_dirs):
            continue
        if path.suffix.lower() in suffixes:
            yield path


def count_lines(path: Path) -> tuple[int | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            return sum(1 for _ in handle), None
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix in {".py", ".ps1", ".psm1", ".psd1", ".sh", ".bat", ".cmd"}:
        return "script"
    return "source"


def build_report(
    repo_root: Path,
    *,
    max_lines: int,
    include_suffixes: tuple[str, ...],
    excluded_dirs: set[str],
) -> dict[str, object]:
    checked: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []
    errors: list[str] = []

    for path in sorted(iter_candidate_files(repo_root, include_suffixes, excluded_dirs)):
        rel = normalize_rel(path, repo_root)
        line_count, error = count_lines(path)
        if error:
            errors.append(f"{rel}: {error}")
            continue
        item = {
            "path": rel,
            "line_count": line_count,
            "limit": max_lines,
            "kind": classify_file(path),
            "over_limit": bool(line_count is not None and line_count > max_lines),
        }
        checked.append(item)
        if item["over_limit"]:
            violations.append(item)

    return {
        "schema_version": 1,
        "kind": "file_line_limit_report",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "max_lines": max_lines,
        "include_suffixes": list(include_suffixes),
        "excluded_dirs": sorted(excluded_dirs),
        "checked_file_count": len(checked),
        "violation_count": len(violations),
        "violations": violations,
        "errors": errors,
        "passed": not errors and not violations,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
    }


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    violations = data.get("violations") if isinstance(data.get("violations"), list) else []
    lines = [
        "# File line-limit report",
        "",
        f"- Passed: `{data.get('passed')}`",
        f"- Max lines: `{data.get('max_lines')}`",
        f"- Checked files: `{data.get('checked_file_count')}`",
        f"- Violations: `{data.get('violation_count')}`",
        "",
        "## Violations",
        "",
    ]
    if not violations:
        lines.append("No files exceed the configured limit.")
    else:
        lines.extend(["| File | Kind | Lines | Limit |", "|---|---|---:|---:|"])
        for item in violations:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| `{}` | `{}` | {} | {} |".format(
                    item.get("path"),
                    item.get("kind"),
                    item.get("line_count"),
                    item.get("limit"),
                )
            )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report files that exceed the IA-Carmine 400-line policy.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--include-suffix", action="append", default=[])
    parser.add_argument("--exclude-dir", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", default="")
    parser.add_argument("--fail-on-violations", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    suffixes = tuple(split_csv(args.include_suffix) or DEFAULT_INCLUDE_SUFFIXES)
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_dirs.update(split_csv(args.exclude_dir))

    report = build_report(
        repo_root,
        max_lines=args.max_lines,
        include_suffixes=suffixes,
        excluded_dirs=excluded_dirs,
    )
    write_json(Path(args.output), report)
    if args.markdown_output:
        write_markdown(Path(args.markdown_output), report)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.fail_on_violations and not report.get("passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
