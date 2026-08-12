#!/usr/bin/env python3
"""Validate generic policy checks for generated Python scripts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from Tools.validation.generated_python_policy import (
        evaluate_python_paths,
        evaluate_python_text,
        generated_python_rule_dicts,
    )
except ImportError:  # Allows direct execution from Tools/validation.
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from Tools.validation.generated_python_policy import (  # type: ignore
        evaluate_python_paths,
        evaluate_python_text,
        generated_python_rule_dicts,
    )


def _repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def sample_results() -> list[dict[str, Any]]:
    """Run deterministic in-memory policy samples."""
    samples = {
        "valid_minimal_python": ("result = 1 + 1\n", True, 0),
        "syntax_error": ("def broken(:\n    pass\n", False, 0),
        "warning_eval_exec": ("value = eval('1 + 1')\n", True, 1),
        "warning_os_system": ("import os\nos.system('echo ok')\n", True, 1),
        "warning_os_system_alias": ("import os as os_mod\nos_mod.system('echo ok')\n", True, 1),
        "warning_subprocess_shell_true": ("import subprocess\nsubprocess.run('echo ok', shell=True)\n", True, 1),
        "warning_subprocess_alias_shell_true": (
            "from subprocess import check_output as run_cmd\nrun_cmd('echo ok', shell=True)\n",
            True,
            1,
        ),
        "safe_subprocess_no_shell": ("import subprocess\nsubprocess.run(['echo', 'ok'], check=False)\n", True, 0),
    }
    rendered: list[dict[str, Any]] = []
    for label, (text, expected_passed, expected_min_warnings) in samples.items():
        data = evaluate_python_text(label, text).to_dict()
        data["expected_passed"] = expected_passed
        data["expected_min_warnings"] = expected_min_warnings
        data["sample_passed"] = data["passed"] is expected_passed and data["warning_count"] >= expected_min_warnings
        rendered.append(data)
    return rendered


def check_policy(repo_root: Path, paths: list[str]) -> dict[str, Any]:
    """Evaluate generic generated Python policy samples and optional files."""
    target_paths = [_repo_path(repo_root, item) for item in paths]
    path_results = evaluate_python_paths(target_paths) if target_paths else []
    samples = sample_results()

    errors = []
    for item in samples:
        if not item["sample_passed"]:
            errors.append(
                "sample {label} expected passed={expected_passed} and warnings>={expected_min_warnings}, "
                "got passed={passed} warnings={warning_count}".format(**item)
            )
    errors.extend(f"path policy failed: {item.label}" for item in path_results if not item.passed)
    warnings = [
        f"{item['label']}: {finding['message']}"
        for item in [*samples, *[result.to_dict() for result in path_results]]
        for finding in item["findings"]
        if finding["severity"] == "warning"
    ]

    return {
        "schema_version": 1,
        "kind": "generated_python_policy",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "rule_count": len(generated_python_rule_dicts()),
        "rules": generated_python_rule_dicts(),
        "sample_results": samples,
        "path_count": len(path_results),
        "path_results": [item.to_dict() for item in path_results],
        "notes": [
            "This validator checks generated Python concepts, not input domains or output applications.",
            "Application-specific adapters should pass their own rules through generated_python_policy.",
            "Warnings do not fail validation; syntax errors and adapter errors do.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", action="append", default=[], help="Generated Python script path to validate. Can be repeated.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_policy(repo_root, args.path)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = repo_root / output
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
