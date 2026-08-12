#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def candidate_paths(repo_root: Path, raw: str) -> list[Path]:
    raw = raw.strip().strip('"').strip("'")
    p = Path(raw)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append((Path.cwd() / p).resolve())
        candidates.append((repo_root / p).resolve())
    normalized = raw.replace("\\", "/")
    p2 = Path(normalized)
    if p2.is_absolute():
        candidates.append(p2)
    else:
        candidates.append((Path.cwd() / p2).resolve())
        candidates.append((repo_root / p2).resolve())
    name = Path(normalized).name
    for base in [repo_root / "output" / "validation", repo_root]:
        if base.exists() and name:
            candidates.extend(match.resolve() for match in base.rglob(name))
    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def load_json_from_candidates(candidates: list[Path]) -> tuple[dict[str, Any] | None, Path | None, list[str]]:
    diagnostics: list[str] = []
    for path in candidates:
        if not path.exists():
            diagnostics.append(f"missing:{path}")
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            diagnostics.append(f"read_error:{path}:{type(exc).__name__}:{exc}")
            continue
        try:
            data = json.loads(text)
        except Exception as exc:
            diagnostics.append(f"json_error:{path}:{type(exc).__name__}:{exc}")
            continue
        if not isinstance(data, dict):
            diagnostics.append(f"json_not_object:{path}")
            continue
        return data, path, diagnostics
    return None, None, diagnostics


def check(data: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    classifications: list[str] = []
    if data is None:
        return ["gpu0_companion_report_missing_or_invalid"], ["gpu0_companion_report_missing"]
    checks = [
        (data.get("kind") == "gpu0_companion_worker_lane", "invalid_gpu0_companion_kind"),
        (data.get("production_role") == "companion_worker", "gpu0_companion_role_missing"),
        (data.get("passed") is True, "gpu0_companion_report_not_passed"),
        (int(data.get("companion_task_count") or 0) > 0, "gpu0_companion_no_tasks"),
        (int(data.get("tool_request_count") or 0) > 0, "gpu0_companion_no_tool_requests"),
        (data.get("gpu0_workload_passed") is True, "gpu0_companion_workload_not_passed"),
    ]
    for ok, code in checks:
        if not ok:
            errors.append(code)
            classifications.append(code)
    return errors, classifications


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    candidates = candidate_paths(repo_root, args.report)
    data, selected, diagnostics = load_json_from_candidates(candidates)
    errors, classifications = check(data)

    result = {
        "schema_version": 3,
        "kind": "gpu0_companion_contract",
        "passed": not errors,
        "classifications": classifications,
        "errors": errors,
        "requested_report": args.report,
        "selected_report": str(selected) if selected else "",
        "selected_report_exists": bool(selected and selected.exists()),
        "candidate_count": len(candidates),
        "diagnostics": diagnostics[:50],
    }

    out = Path(args.output)
    if not out.is_absolute():
        out = repo_root / out
    md = Path(args.markdown_output)
    if not md.is_absolute():
        md = repo_root / md
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md.write_text(
        "# GPU0 Companion Contract\n\n"
        + f"- Passed: `{result['passed']}`\n"
        + f"- Selected report: `{result['selected_report']}`\n"
        + f"- Classifications: `{classifications}`\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": result["passed"], "classifications": classifications, "output": str(out), "selected_report": result["selected_report"]}, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
