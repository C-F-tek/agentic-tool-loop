#!/usr/bin/env python3
"""Validate generated Blender Python scripts with reusable policy rules.

The policy is intentionally conservative and non-destructive. It is designed to
catch known incompatible or dangerous patterns before a generated script is run
inside Blender, while keeping the underlying rule engine reusable for other
file/application contexts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from Tools.validation.generated_file_policy import PolicyRule
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
    from Tools.validation.generated_file_policy import PolicyRule  # type: ignore
    from Tools.validation.generated_python_policy import (  # type: ignore
        evaluate_python_paths,
        evaluate_python_text,
        generated_python_rule_dicts,
    )


BLENDER_GENERATED_SCRIPT_RULES: tuple[PolicyRule, ...] = (
    PolicyRule(
        rule_id="requires_bpy_import",
        description="generated Blender scripts should import bpy explicitly",
        pattern=r"(^|\n)\s*import\s+bpy\b|(^|\n)\s*from\s+bpy\b",
        kind="required",
        severity="error",
    ),
    PolicyRule(
        rule_id="forbid_musgrave_node",
        description="ShaderNodeTexMusgrave is unavailable in Blender 5.x and caused a real runtime failure",
        pattern=r"ShaderNodeTexMusgrave",
        kind="forbidden",
        severity="error",
    ),
    PolicyRule(
        rule_id="forbid_open_mainfile",
        description="generated scripts must not open another Blender project file",
        pattern=r"bpy\.ops\.wm\.open_mainfile\s*\(",
        kind="forbidden",
        severity="error",
    ),
    PolicyRule(
        rule_id="forbid_quit_blender",
        description="generated scripts must not quit Blender",
        pattern=r"bpy\.ops\.wm\.quit_blender\s*\(",
        kind="forbidden",
        severity="error",
    ),
    PolicyRule(
        rule_id="warn_save_as_mainfile",
        description="generated scripts should not save .blend files unless the workflow explicitly asks for it",
        pattern=r"bpy\.ops\.wm\.save_as_mainfile\s*\(",
        kind="forbidden",
        severity="warning",
    ),
)


def default_candidate_paths(repo_root: Path) -> list[Path]:
    """Return safe default generated-script candidate paths when they exist."""
    candidates = [
        repo_root / "output" / "implementation_draft.py",
        repo_root / "output" / "ai_pipeline" / "generated_scene.py",
        repo_root / "Scripting" / "v61b" / "hotpatch" / "generated_scene_patch.py",
    ]
    return [path for path in candidates if path.exists()]


def sample_results() -> list[dict[str, Any]]:
    """Run deterministic in-memory policy samples."""
    samples = {
        "valid_minimal_blender_script": "import bpy\nscene = bpy.context.scene\n",
        "blocked_musgrave_node": "import bpy\nnode = nodes.new('ShaderNodeTexMusgrave')\n",
        "blocked_open_file": "import bpy\nbpy.ops.wm.open_mainfile(filepath='other.blend')\n",
        "warning_save_file": "import bpy\nbpy.ops.wm.save_as_mainfile(filepath='scene.blend')\n",
        "warning_python_eval_exec": "import bpy\nvalue = eval('1 + 1')\n",
        "missing_bpy_import": "print('not a Blender script')\n",
    }
    return [evaluate_python_text(name, text, BLENDER_GENERATED_SCRIPT_RULES).to_dict() for name, text in samples.items()]


def _repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def check_policy(repo_root: Path, paths: list[str]) -> dict[str, Any]:
    """Evaluate generated Blender script policy."""
    explicit_paths = [_repo_path(repo_root, item) for item in paths]
    target_paths = explicit_paths or default_candidate_paths(repo_root)
    path_results = evaluate_python_paths(target_paths, BLENDER_GENERATED_SCRIPT_RULES) if target_paths else []
    samples = sample_results()

    sample_expectations = {
        "valid_minimal_blender_script": True,
        "blocked_musgrave_node": False,
        "blocked_open_file": False,
        "warning_save_file": True,
        "warning_python_eval_exec": True,
        "missing_bpy_import": False,
    }
    sample_errors = []
    for item in samples:
        expected = sample_expectations[item["label"]]
        if item["passed"] is not expected:
            sample_errors.append(f"sample {item['label']} expected passed={expected}, got {item['passed']}")

    path_errors = [item.to_dict() for item in path_results if not item.passed]
    errors = sample_errors + [f"path policy failed: {item['label']}" for item in path_errors]
    warnings = [
        f"{item['label']}: {finding['message']}"
        for item in [*samples, *[result.to_dict() for result in path_results]]
        for finding in item["findings"]
        if finding["severity"] == "warning"
    ]

    return {
        "schema_version": 1,
        "kind": "generated_blender_script_policy",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "generic_python_policy": True,
        "generic_python_rule_count": len(generated_python_rule_dicts()),
        "adapter_rule_count": len(BLENDER_GENERATED_SCRIPT_RULES),
        "rule_count": len(generated_python_rule_dicts(BLENDER_GENERATED_SCRIPT_RULES)),
        "rules": generated_python_rule_dicts(BLENDER_GENERATED_SCRIPT_RULES),
        "sample_results": samples,
        "path_count": len(path_results),
        "path_results": [item.to_dict() for item in path_results],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", action="append", default=[], help="Generated Blender Python script path to validate. Can be repeated.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_policy(repo_root, args.path)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
