#!/usr/bin/env python3
"""Patch run_unified_local_ai_refactor.ps1 with LightFull0To10 dispatch."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

REPOROOT_MARKER = "[string]$RepoRoot"
LIGHT_PARAM_MARKER = "[switch]$LightFull0To10"
DISPATCH_BEGIN = "# IA-CARMINE-LIGHTFULL0TO10-DISPATCH-BEGIN"
DISPATCH_END = "# IA-CARMINE-LIGHTFULL0TO10-DISPATCH-END"


def find_param_block(text: str) -> tuple[int, int]:
    start = text.find("param(")
    if start < 0:
        raise ValueError("param block not found")
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return start, index
    raise ValueError("param block closing parenthesis not found")


def add_repo_root_param(text: str) -> tuple[str, bool]:
    if REPOROOT_MARKER in text:
        return text, False
    start, _end = find_param_block(text)
    insert_at = text.find("\n", start)
    if insert_at < 0:
        raise ValueError("param opening newline not found")
    insert_at += 1
    insert = '    [string]$RepoRoot = ".",\n'
    return text[:insert_at] + insert + text[insert_at:], True


def add_light_params(text: str) -> tuple[str, bool]:
    if LIGHT_PARAM_MARKER in text:
        return text, False
    _start, end = find_param_block(text)
    insert = (
        ",\n"
        "    [switch]$LightFull0To10,\n"
        "    [string]$LightFull0To10OutputDir = \"output/validation/unified_light_full0to10_profile\",\n"
        "    [switch]$LightFull0To10NoExternalProbes\n"
    )
    return text[:end] + insert + text[end:], True


def dispatch_block() -> str:
    return f"""
{DISPATCH_BEGIN}
if ($LightFull0To10) {{
    $LightProfileScript = Join-Path $PSScriptRoot "run_unified_light_full0to10_profile.ps1"
    if (-not (Test-Path $LightProfileScript)) {{
        throw "LightFull0To10 profile script not found: $LightProfileScript"
    }}

    if ([string]::IsNullOrWhiteSpace($RepoRoot)) {{
        $ResolvedLightRepoRoot = (Resolve-Path ".").Path
    }} else {{
        $ResolvedLightRepoRoot = (Resolve-Path $RepoRoot).Path
    }}

    $LightArgs = @(
        "-RepoRoot", $ResolvedLightRepoRoot,
        "-OutputDir", $LightFull0To10OutputDir
    )

    if (-not $PSBoundParameters.ContainsKey("LightFull0To10NoExternalProbes") -or $LightFull0To10NoExternalProbes) {{
        $LightArgs += "-NoExternalProbes"
    }}

    Write-Host "[LightFull0To10] Dispatching evidence-only profile..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LightProfileScript @LightArgs
    exit $LASTEXITCODE
}}
{DISPATCH_END}
""".lstrip("\n")


def replace_existing_dispatch(text: str) -> tuple[str, bool]:
    start = text.find(DISPATCH_BEGIN)
    end = text.find(DISPATCH_END)
    if start < 0 or end < 0:
        return text, False
    end = text.find("\n", end)
    if end < 0:
        end = len(text)
    else:
        end += 1
    return text[:start] + dispatch_block() + text[end:], True


def add_dispatch(text: str) -> tuple[str, bool]:
    replaced, did_replace = replace_existing_dispatch(text)
    if did_replace:
        return replaced, True

    needle = '$ErrorActionPreference = "Stop"'
    index = text.find(needle)
    if index >= 0:
        insert_at = text.find("\n", index)
        insert_at = len(text) if insert_at < 0 else insert_at + 1
        return text[:insert_at] + "\n" + dispatch_block() + text[insert_at:], True

    _start, end = find_param_block(text)
    insert_at = text.find("\n", end)
    insert_at = end + 1 if insert_at < 0 else insert_at + 1
    return text[:insert_at] + "\n" + dispatch_block() + text[insert_at:], True


def patch_text(text: str) -> tuple[str, dict[str, bool]]:
    updated, repo_root_added = add_repo_root_param(text)
    updated, light_params_added = add_light_params(updated)
    updated, dispatch_changed = add_dispatch(updated)
    return updated, {
        "repo_root_added": repo_root_added,
        "light_params_added": light_params_added,
        "dispatch_changed": dispatch_changed,
    }


def validate(updated: str) -> list[str]:
    errors: list[str] = []
    required = (
        REPOROOT_MARKER,
        LIGHT_PARAM_MARKER,
        "$LightFull0To10OutputDir",
        "$LightFull0To10NoExternalProbes",
        "$ResolvedLightRepoRoot",
        DISPATCH_BEGIN,
        DISPATCH_END,
        "run_unified_light_full0to10_profile.ps1",
    )
    for token in required:
        if token not in updated:
            errors.append(f"missing token: {token}")
    if "git restore docs" in updated.lower():
        errors.append("unexpected git restore docs token")
    return errors


def write_report(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--launcher", default="Tools/workflow/run_unified_local_ai_refactor.ps1")
    parser.add_argument("--backup-dir", default="output/validation/unified_launcher_lightfull0to10_patch_v2")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    launcher = repo / args.launcher
    backup_dir = repo / args.backup_dir
    report_path = Path(args.report) if args.report else backup_dir / "launcher_lightfull0to10_patch_report.json"

    original = launcher.read_text(encoding="utf-8", errors="replace")
    updated, changes = patch_text(original)
    errors = validate(updated)
    changed = original != updated

    backup_path = backup_dir / "run_unified_local_ai_refactor.ps1.before_lightfull0to10_v2"
    if args.apply and changed:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(launcher, backup_path)
        launcher.write_text(updated, encoding="utf-8")

    report = {
        "kind": "unified_launcher_lightfull0to10_patch_v2",
        "passed": not errors,
        "apply": bool(args.apply),
        "changed": changed,
        "launcher": str(launcher),
        "backup": str(backup_path) if args.apply and changed else None,
        "changes": changes,
        "errors": errors,
        "source_writes_performed": bool(args.apply and changed),
        "provider_execution_performed": False,
        "patch_application_performed": bool(args.apply and changed),
    }
    write_report(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
