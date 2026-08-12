#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_startup_check(repo_root: Path, startup_output: Path) -> tuple[int, str]:
    cmd = [
        sys.executable,
        str(repo_root / "Tools" / "workflow" / "startup_check.py"),
        "--repo-root",
        str(repo_root),
        "--output",
        str(startup_output),
        "--json",
    ]
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout or ""


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# Startup check CLI contract smoke",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Startup return code: `{report.get('startup_returncode')}`",
        f"- Startup output exists: `{report.get('startup_output_exists')}`",
        f"- Startup output JSON OK: `{report.get('startup_output_json_ok')}`",
        f"- Supports `--repo-root`: `{report.get('supports_repo_root')}`",
        f"- Supports `--output`: `{report.get('supports_output')}`",
        "",
    ]

    if report.get("errors"):
        lines += ["## Errors", ""]
        for item in report["errors"]:
            lines.append(f"- {item}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke startup_check.py CLI output contract.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve(strict=False)
    output = Path(args.output).resolve(strict=False)
    markdown_output = Path(args.markdown_output).resolve(strict=False)
    startup_output = output.with_name(output.stem + "_startup_check.json")

    errors: list[str] = []

    returncode, stdout = run_startup_check(repo_root, startup_output)

    startup_json_ok = False
    startup_report = {}
    if startup_output.exists():
        try:
            startup_report = json.loads(startup_output.read_text(encoding="utf-8-sig"))
            startup_json_ok = isinstance(startup_report, dict)
        except Exception as exc:
            errors.append(f"startup output is not valid JSON: {type(exc).__name__}: {exc}")
    else:
        errors.append(f"startup output missing: {startup_output}")

    supports_repo_root = "unrecognized arguments" not in stdout
    supports_output = startup_output.exists()

    required_fields = ("schema_version", "kind", "repo_root", "passed", "errors")
    missing_required_fields = [
        field
        for field in required_fields
        if not isinstance(startup_report, dict) or field not in startup_report
    ]

    if returncode != 0:
        errors.append(f"startup_check returned {returncode}: {stdout[-1200:]}")
    if not startup_json_ok:
        errors.append("startup output JSON contract failed")
    if not supports_output:
        errors.append("--output did not create the selected report path")
    if missing_required_fields:
        errors.append("startup output missing validation report fields: " + ", ".join(missing_required_fields))
    if isinstance(startup_report, dict) and not isinstance(startup_report.get("passed"), bool):
        errors.append("startup output field passed must be boolean")
    if isinstance(startup_report, dict) and not isinstance(startup_report.get("errors"), list):
        errors.append("startup output field errors must be a list")

    report = {
        "schema_version": 1,
        "kind": "startup_check_cli_contract_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "startup_returncode": returncode,
        "startup_output": str(startup_output),
        "startup_output_exists": startup_output.exists(),
        "startup_output_json_ok": startup_json_ok,
        "supports_repo_root": supports_repo_root,
        "supports_output": supports_output,
        "startup_report_ok": startup_report.get("ok") if isinstance(startup_report, dict) else None,
        "startup_report_passed": startup_report.get("passed") if isinstance(startup_report, dict) else None,
        "startup_report_kind": startup_report.get("kind") if isinstance(startup_report, dict) else None,
        "startup_report_schema_version": startup_report.get("schema_version") if isinstance(startup_report, dict) else None,
        "startup_warning_count": startup_report.get("warning_count") if isinstance(startup_report, dict) else None,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "errors": errors,
        "warnings": [],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report, markdown_output)

    print(json.dumps({
        "passed": report["passed"],
        "output": str(output),
        "markdown_output": str(markdown_output),
        "startup_output": str(startup_output),
        "errors": errors,
    }, indent=2, ensure_ascii=False))

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
