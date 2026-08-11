#!/usr/bin/env python3
"""Build a review-safe patch bundle from an agent review patch plan.

The bundle is intentionally conservative:

- reads an existing patch-plan report;
- emits a local ZIP bundle under output/**;
- generates an idempotent runner with dry-run default and explicit --apply;
- only generates managed Markdown append/update operations for concrete .md targets;
- skips runtime/code/non-Markdown/generated/unsafe targets;
- never applies patches itself, never runs providers, never writes SQLite and never
  runs Blender.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import read_json_object  # type: ignore
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore

DEFAULT_PATCH_PLAN = "output/patch_specs/agent_review_patch_plan.json"
DEFAULT_OUTPUT_DIR = "output/validation/patch_bundles"
DEFAULT_OUTPUT = "output/validation/agent_review_patch_bundle_builder.json"
DEFAULT_MARKDOWN = "output/validation/agent_review_patch_bundle_builder.md"
DEFAULT_BASENAME = "agent_review_patch_bundle"

FORBIDDEN_TARGET_PREFIXES = (
    "output/",
    "renders/",
    ".git/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
)
FORBIDDEN_TARGET_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
)
MANAGED_BEGIN_PREFIX = "<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:BEGIN"
MANAGED_END_PREFIX = "<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:END"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").strip("/")


def stable_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._").lower()
    if cleaned:
        return cleaned[:80]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def safe_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)


def target_path_error(path_value: str, repo_root: Path) -> str | None:
    normalized = normalize_repo_path(path_value)
    if not normalized:
        return "empty target path"
    if Path(normalized).is_absolute():
        return "absolute target paths are not allowed"
    full = (repo_root / normalized).resolve(strict=False)
    try:
        full.relative_to(repo_root.resolve(strict=False))
    except ValueError:
        return "target path escapes repository root"
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        return f"forbidden target prefix: {normalized}"
    if any(normalized.lower().endswith(suffix) for suffix in FORBIDDEN_TARGET_SUFFIXES):
        return f"forbidden database target: {normalized}"
    if not full.exists():
        return "target file does not exist"
    if not full.is_file():
        return "target is not a file"
    return None


def is_markdown(path_value: str) -> bool:
    return normalize_repo_path(path_value).lower().endswith((".md", ".markdown"))


def load_patch_plan(path: Path) -> tuple[dict[str, Any], list[str]]:
    data, errors = read_json_object(path)
    return data, [str(error) for error in errors]


def plan_items(patch_plan: dict[str, Any]) -> list[dict[str, Any]]:
    items = patch_plan.get("patch_plans")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def build_managed_block(plan: dict[str, Any], target: str) -> str:
    plan_id = stable_id(str(plan.get("id") or target))
    area = str(plan.get("area") or "unknown")
    source = str(plan.get("source") or "unknown")
    risk = str(plan.get("risk") or "unknown")
    rationale = str(plan.get("rationale") or "").strip()
    strategy = str(plan.get("edit_strategy") or plan.get("proposed_strategy") or "").strip()
    validation_commands = plan.get("validation_commands") if isinstance(plan.get("validation_commands"), list) else []
    stop_conditions = plan.get("stop_conditions") if isinstance(plan.get("stop_conditions"), list) else []
    block_id = f"{plan_id}:{stable_id(target)}"
    lines = [
        "",
        f"{MANAGED_BEGIN_PREFIX} id={block_id} -->",
        "",
        "### IA-Carmine agent-review patch note",
        "",
        "This managed note records an evidence-backed manual-review patch plan. It is intentionally compact and idempotent.",
        "",
        f"- Plan id: `{plan.get('id')}`",
        f"- Area: `{area}`",
        f"- Source: `{source}`",
        f"- Risk: `{risk}`",
        f"- Target: `{target}`",
    ]
    if rationale:
        lines.append(f"- Rationale: {rationale}")
    if strategy:
        lines.append(f"- Strategy: {strategy}")
    if validation_commands:
        lines.append("- Validation commands:")
        for command in validation_commands[:8]:
            lines.append(f"  - `{command}`")
    if stop_conditions:
        lines.append("- Stop conditions:")
        for condition in stop_conditions[:8]:
            lines.append(f"  - {condition}")
    lines.extend(["", f"{MANAGED_END_PREFIX} id={block_id} -->", ""])
    return "\n".join(lines)


def collect_operations(patch_plan: dict[str, Any], repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    operations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for plan in plan_items(patch_plan):
        plan_id = str(plan.get("id") or "unknown")
        targets = plan.get("target_files") if isinstance(plan.get("target_files"), list) else []
        if not targets:
            skipped.append({"id": plan_id, "reason": "plan has no target_files"})
            continue
        for raw_target in targets:
            target = normalize_repo_path(raw_target)
            key = f"{plan_id}:{target}"
            if key in seen:
                continue
            seen.add(key)
            error = target_path_error(target, repo_root)
            if error:
                skipped.append({"id": plan_id, "target": target, "reason": error})
                continue
            if not is_markdown(target):
                skipped.append({"id": plan_id, "target": target, "reason": "non-Markdown targets are manual-review-only in this bundle"})
                continue
            full = resolve_path(repo_root, target)
            try:
                original = full.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped.append({"id": plan_id, "target": target, "reason": "target is not UTF-8 text"})
                continue
            block = build_managed_block(plan, target)
            block_hash = hashlib.sha256(block.encode("utf-8")).hexdigest()
            operations.append(
                {
                    "id": stable_id(key),
                    "plan_id": plan_id,
                    "target": target,
                    "kind": "markdown_managed_block",
                    "mode": "append_or_replace_managed_block",
                    "managed_begin_prefix": MANAGED_BEGIN_PREFIX,
                    "managed_end_prefix": MANAGED_END_PREFIX,
                    "block_hash_sha256": block_hash,
                    "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                    "block": block,
                    "manual_review_required": True,
                }
            )
    return operations, skipped


def bundle_runner_source() -> str:
    return r'''#!/usr/bin/env python3
"""Apply or inspect an IA-Carmine agent-review patch bundle.

Default mode is dry-run. Use --apply explicitly to write managed Markdown blocks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

MANAGED_BEGIN_PREFIX = "<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:BEGIN"
MANAGED_END_PREFIX = "<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:END"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_git_status(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"GIT_STATUS_ERROR: {type(exc).__name__}: {exc}"
    return completed.stdout.strip()


def replace_or_append_managed_block(text: str, operation: dict[str, Any]) -> tuple[str, str]:
    block = str(operation["block"])
    begin_prefix = str(operation.get("managed_begin_prefix") or MANAGED_BEGIN_PREFIX)
    end_prefix = str(operation.get("managed_end_prefix") or MANAGED_END_PREFIX)
    block_id = ""
    for line in block.splitlines():
        if line.startswith(begin_prefix):
            marker = "id="
            if marker in line:
                block_id = line.split(marker, 1)[1].split("-->", 1)[0].strip()
            break
    if not block_id:
        return text.rstrip() + "\n" + block, "append"
    begin_marker = f"{begin_prefix} id={block_id} -->"
    end_marker = f"{end_prefix} id={block_id} -->"
    start = text.find(begin_marker)
    if start == -1:
        return text.rstrip() + "\n" + block, "append"
    end = text.find(end_marker, start)
    if end == -1:
        raise ValueError(f"managed begin marker exists without matching end marker: {block_id}")
    end += len(end_marker)
    replacement = text[:start].rstrip() + "\n" + block.strip() + "\n" + text[end:].lstrip()
    return replacement.rstrip() + "\n", "replace"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--manifest", default="patches/manifest.json")
    parser.add_argument("--report", default="patch_bundle_result.json")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    bundle_root = Path(__file__).resolve().parent
    manifest_path = bundle_root / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    status = run_git_status(repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    results: list[dict[str, Any]] = []

    if status and not args.allow_dirty:
        errors.append("working tree is not clean; rerun with --allow-dirty only after manual review")

    for operation in manifest.get("operations", []):
        target = str(operation.get("target") or "")
        target_path = (repo_root / target).resolve(strict=False)
        try:
            target_path.relative_to(repo_root)
        except ValueError:
            errors.append(f"target escapes repo root: {target}")
            continue
        if operation.get("kind") != "markdown_managed_block":
            warnings.append(f"skipped unsupported operation kind for {target}: {operation.get('kind')}")
            continue
        if not target_path.exists() or not target_path.is_file():
            errors.append(f"target missing: {target}")
            continue
        text = target_path.read_text(encoding="utf-8")
        before_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            new_text, action = replace_or_append_managed_block(text, operation)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{target}: {type(exc).__name__}: {exc}")
            continue
        after_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        changed = before_hash != after_hash
        if args.apply and not errors and changed:
            target_path.write_text(new_text, encoding="utf-8", newline="\n")
        results.append(
            {
                "id": operation.get("id"),
                "target": target,
                "action": action,
                "changed": changed,
                "applied": bool(args.apply and changed and not errors),
                "before_sha256": before_hash,
                "after_sha256": after_hash,
            }
        )

    report = {
        "schema_version": 1,
        "kind": "agent_review_patch_bundle_result",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": bool(args.apply and not errors),
        "source_writes_performed": bool(args.apply and not errors),
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "apply_requested": bool(args.apply),
        "allow_dirty": bool(args.allow_dirty),
        "operation_count": len(manifest.get("operations", [])),
        "changed_count": sum(1 for item in results if item.get("changed")),
        "applied_count": sum(1 for item in results if item.get("applied")),
        "results": results,
        "git_status_before": status,
    }
    report_path = bundle_root / args.report
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "errors": report["errors"],
        "warnings": report["warnings"],
        "apply_requested": report["apply_requested"],
        "operation_count": report["operation_count"],
        "changed_count": report["changed_count"],
        "applied_count": report["applied_count"],
        "report": str(report_path),
        "patch_application_performed": report["patch_application_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


def validation_script_source() -> str:
    return r'''param(
    [string]$RepoRoot = "."
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot
python .\Tools\validation\check_python_syntax.py --repo-root . --output .\output\validation\python_syntax_after_patch_bundle.json
python .\Tools\validation\check_validation_report_contract.py --repo-root . --report-file .\output\validation\python_syntax_after_patch_bundle.json --output .\output\validation\validation_report_contract_after_patch_bundle.json
git diff --check
git status --short
'''


def readme_source(bundle_name: str, operation_count: int, skipped_count: int) -> str:
    return f"""# IA-Carmine Agent Review Patch Bundle

Bundle: `{bundle_name}`

This bundle is generated from an `agent_review_patch_plan` report.

- Operations: `{operation_count}`
- Skipped candidates: `{skipped_count}`
- Default mode: dry-run
- Apply mode: explicit `--apply`
- Supported automatic operation: managed Markdown block append/replace only

## Dry-run

```powershell
python .\\run_patch_bundle.py --repo-root C:\\Users\\carmi\\blender\\blender-audio-project
```

## Apply

```powershell
python .\\run_patch_bundle.py --repo-root C:\\Users\\carmi\\blender\\blender-audio-project --apply
```

If your working tree is intentionally dirty, add `--allow-dirty` only after manual review.

## Validate after apply

```powershell
.\\scripts\\validate_after_patch.ps1 -RepoRoot C:\\Users\\carmi\\blender\\blender-audio-project
```

## Guardrails

This bundle never executes providers, never runs Blender, never writes SQLite and never performs Git operations.
"""


def build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    patch_plan_path = resolve_path(repo_root, args.patch_plan)
    output_dir = resolve_path(repo_root, args.output_dir)
    errors: list[str] = []
    warnings: list[str] = []
    patch_plan, load_errors = load_patch_plan(patch_plan_path)
    errors.extend(f"patch_plan: {error}" for error in load_errors)

    operations: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if patch_plan:
        if patch_plan.get("kind") != "agent_review_patch_plan":
            warnings.append(f"unexpected patch plan kind: {patch_plan.get('kind')}")
        operations, skipped = collect_operations(patch_plan, repo_root)
    if not operations and not errors:
        errors.append("no supported Markdown operations were produced from the patch plan")

    bundle_stamp = args.stamp or stamp()
    bundle_name = f"{args.basename}_{bundle_stamp}"
    bundle_root = output_dir / bundle_name
    patches_dir = bundle_root / "patches"
    scripts_dir = bundle_root / "scripts"
    bundle_zip = output_dir / f"{bundle_name}.zip"

    if args.write_bundle and not errors:
        patches_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": 1,
            "kind": "agent_review_patch_bundle_manifest",
            "generated_at": now_iso(),
            "repo_root": str(repo_root),
            "patch_plan": repo_rel(patch_plan_path, repo_root),
            "operation_count": len(operations),
            "skipped_candidate_count": len(skipped),
            "operations": operations,
            "skipped_candidates": skipped,
            "guardrails": {
                "dry_run_default": True,
                "explicit_apply_required": True,
                "markdown_managed_blocks_only": True,
                "provider_execution_performed": False,
                "patch_application_performed_by_builder": False,
                "sqlite_write_performed": False,
                "persistent_memory_write_performed": False,
            },
        }
        (patches_dir / "manifest.json").write_text(safe_json(manifest) + "\n", encoding="utf-8")
        (bundle_root / "run_patch_bundle.py").write_text(bundle_runner_source(), encoding="utf-8", newline="\n")
        (scripts_dir / "validate_after_patch.ps1").write_text(validation_script_source(), encoding="utf-8", newline="\n")
        (bundle_root / "README.md").write_text(readme_source(bundle_name, len(operations), len(skipped)), encoding="utf-8", newline="\n")
        with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(bundle_root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(bundle_root.parent).as_posix())

    report = {
        "schema_version": 1,
        "kind": "agent_review_patch_bundle_builder",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "patch_plan": repo_rel(patch_plan_path, repo_root),
        "bundle_name": bundle_name,
        "bundle_dir": repo_rel(bundle_root, repo_root),
        "bundle_zip": repo_rel(bundle_zip, repo_root) if bundle_zip.exists() else "",
        "write_bundle": bool(args.write_bundle),
        "operation_count": len(operations),
        "skipped_candidate_count": len(skipped),
        "operations": [
            {key: value for key, value in operation.items() if key != "block"}
            for operation in operations
        ],
        "skipped_candidates": skipped,
        "guardrails": {
            "report_only_builder": True,
            "dry_run_default_bundle": True,
            "explicit_apply_required": True,
            "markdown_managed_blocks_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Patch Bundle Builder", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Bundle: `{report.get('bundle_name')}`")
    lines.append(f"- Bundle ZIP: `{report.get('bundle_zip')}`")
    lines.append(f"- Operation count: `{report['operation_count']}`")
    lines.append(f"- Skipped candidates: `{report['skipped_candidate_count']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- SQLite write performed: `{report['sqlite_write_performed']}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        lines.extend(f"- {error}" for error in report["errors"])
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    lines.append("## Operations")
    if not report.get("operations"):
        lines.append("- none")
    for operation in report.get("operations", []):
        lines.append(f"- `{operation.get('id')}` -> `{operation.get('target')}`")
    if report.get("skipped_candidates"):
        lines.append("")
        lines.append("## Skipped candidates")
        for item in report["skipped_candidates"]:
            lines.append(f"- `{item.get('id')}` `{item.get('target', '')}`: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--patch-plan", default=DEFAULT_PATCH_PLAN)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--stamp", default="")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--write-bundle", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_bundle(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "errors": report["errors"],
                "warnings": report["warnings"],
                "output": str(output),
                "markdown": str(markdown_output),
                "bundle_zip": report.get("bundle_zip"),
                "operation_count": report["operation_count"],
                "skipped_candidate_count": report["skipped_candidate_count"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
