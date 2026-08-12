"""Shared helpers for lightweight validation reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def resolve_output_path(repo_root: Path, output_arg: str) -> Path:
    """Resolve a report output path relative to the repository root when needed."""
    output = Path(output_arg)
    if not output.is_absolute():
        output = repo_root / output
    return output.resolve()


def write_json_report(report: dict[str, Any], output: Path | None = None) -> str:
    """Serialize a report, optionally write it, and return the rendered JSON text."""
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    return text


def failed_result_errors(results: Iterable[dict[str, Any]], *, label_key: str = "path") -> list[str]:
    """Build compact root-level error strings from result entries with ok=false."""
    errors: list[str] = []
    for item in results:
        if item.get("ok") is not False:
            continue
        label = str(item.get(label_key) or item.get("name") or item.get("package") or "unknown")
        error = str(item.get("error") or item.get("reason") or "failed")
        errors.append(f"{label}: {error}")
    return errors


def warning_result_messages(results: Iterable[dict[str, Any]], *, label_key: str = "path") -> list[str]:
    """Build compact root-level warning strings from result entries exposing warnings."""
    warnings: list[str] = []
    for item in results:
        raw = item.get("warnings")
        if not raw:
            continue
        label = str(item.get(label_key) or item.get("name") or item.get("package") or "unknown")
        if isinstance(raw, list):
            warnings.extend(f"{label}: {warning}" for warning in raw)
        else:
            warnings.append(f"{label}: {raw}")
    return warnings

def read_json_report(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read a JSON report object, returning a safe default on missing/invalid input."""
    if default is None:
        default = {}
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def write_text_report(text: str, output: Path) -> str:
    """Write UTF-8 text report content and return the written text."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return text


def split_csv_values(value: Any) -> list[str]:
    """Split repeatable/comma-separated CLI-style values into a compact list."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized and normalized not in out:
                out.append(normalized)
    return out


def physical_line_count(text: str) -> int:
    """Return physical line count for text using repository report semantics."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def count_file_lines(path: Path, *, encoding: str = "utf-8-sig") -> tuple[int, str | None]:
    """Count physical lines in a text file without raising on read errors."""
    try:
        text = path.read_text(encoding=encoding, errors="replace")
    except OSError as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    return physical_line_count(text), None


def _normalize_line_count_path(value: Any) -> str:
    """Normalize a path value found in line-count CSV/JSON evidence."""
    return str(value or "").strip().replace("\\", "/").lstrip("./")


def parse_line_count_csv_row(row: dict[str, Any]) -> tuple[str, int] | None:
    """Parse one File/Lines or Path/lines CSV row into a normalized tuple."""
    path = _normalize_line_count_path(row.get("Path") or row.get("File"))
    raw_lines = row.get("Lines") or row.get("lines")
    if not path or raw_lines is None:
        return None
    try:
        return path, int(str(raw_lines).strip())
    except ValueError:
        return None


def load_line_count_csv_map(csv_path: Path) -> tuple[dict[str, int], list[str]]:
    """Load line-count CSV evidence into a normalized path -> lines map."""
    import csv

    counts: dict[str, int] = {}
    warnings: list[str] = []
    if not csv_path.exists():
        return counts, [f"line-count CSV missing: {csv_path}"]
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                parsed = parse_line_count_csv_row(dict(row))
                if parsed is None:
                    continue
                path, lines = parsed
                counts[path] = lines
    except OSError as exc:
        warnings.append(f"unable to read line-count CSV: {type(exc).__name__}: {exc}")
    return counts, warnings


def line_count_for_path(path_value: str, counts: dict[str, int]) -> int | None:
    """Return a line-count hint, allowing suffix matching for absolute CSV paths."""
    normalized = _normalize_line_count_path(path_value)
    if normalized in counts:
        return counts[normalized]
    matches = [lines for path, lines in counts.items() if _normalize_line_count_path(path).endswith(normalized)]
    return matches[0] if len(matches) == 1 else None


def load_line_count_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """Load File/Lines rows from a Python line-count CSV report."""
    import csv

    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return sorted(rows, key=lambda item: int(item.get("Lines") or 0), reverse=True)


def render_full_python_line_count_markdown(*, stamp: str, csv_path: Path, rows: list[dict[str, str]]) -> str:
    """Render an untruncated Markdown inventory from line-count CSV rows."""
    total_lines = sum(int(row.get("Lines") or 0) for row in rows)
    lines: list[str] = [
        "# Full Python Line Count Inventory",
        "",
        f"- Stamp: {stamp}",
        f"- CSV: {csv_path}",
        f"- File count: {len(rows)}",
        f"- Total Python lines: {total_lines}",
        "- Visibility rule: all counted Python files are listed below; do not truncate to top 10/top 20.",
        "",
        "| Lines | File |",
        "|---:|---|",
    ]
    for row in rows:
        lines.append(f"| {row.get('Lines') or 0} | `{row.get('File') or ''}` |")
    return "\n".join(lines) + "\n"


def write_full_python_line_count_markdown(*, stamp: str, csv_path: Path, output: Path) -> dict[str, Any]:
    """Build and write full line-count Markdown from a line-count CSV."""
    rows = load_line_count_csv_rows(csv_path)
    markdown = render_full_python_line_count_markdown(stamp=stamp, csv_path=csv_path, rows=rows)
    write_text_report(markdown, output)
    return {
        "csv_path": str(csv_path),
        "markdown_path": str(output),
        "file_count": len(rows),
        "total_lines": sum(int(row.get("Lines") or 0) for row in rows),
    }
