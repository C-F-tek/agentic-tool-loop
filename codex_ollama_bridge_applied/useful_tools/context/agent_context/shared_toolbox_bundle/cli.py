from __future__ import annotations

from .collection import artifact_hints_from_reports, coalesce_list, existing_paths, report_templates_for_stamp, artifact_templates_for_stamp
from .common import *  # noqa: F403
from .summary import build_final_summary, write_final_summary

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--basename", default=None)
    parser.add_argument("--output-dir", default="docs/LOCAL_VALIDATION_EVIDENCE")
    parser.add_argument(
        "--task-md",
        default="docs/LOCAL_AI_TASKS/shared-runtime-toolbox-ai-to-ai-next-task-2026-05-03.md",
    )
    parser.add_argument(
        "--architecture-md",
        default="docs/LOCAL_AI_TASKS/shared-runtime-toolbox-orchestration-architecture.md",
    )
    parser.add_argument("--orchestrator-report", action="append", default=[])
    parser.add_argument("--gpu-report", action="append", default=[])
    parser.add_argument("--sync-report", action="append", default=[])
    parser.add_argument("--contract-replay-report", action="append", default=[])
    parser.add_argument("--code-interpreter-report", action="append", default=[])
    parser.add_argument("--python-syntax-report", action="append", default=[])
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--include-missing-optional", action="store_true")
    parser.add_argument("--validate-bundle", action="store_true")
    parser.add_argument("--validation-output", default=None)
    parser.add_argument("--max-included-artifact-chars", type=int, default=14000)
    parser.add_argument("--max-included-artifacts", type=int, default=40)
    parser.add_argument(
        "--no-recursive-defaults",
        action="store_true",
        help="Disable bounded recursive default discovery for stamped JSON/Markdown files.",
    )
    parser.add_argument(
        "--recursive-report-root",
        action="append",
        default=[],
        help="Extra recursive root for stamped JSON reports; repeatable or comma-separated.",
    )
    parser.add_argument(
        "--recursive-artifact-root",
        action="append",
        default=[],
        help="Extra recursive root for stamped Markdown/JSON artifacts; repeatable or comma-separated.",
    )
    parser.add_argument(
        "--recursive-include-unstamped",
        action="store_true",
        help="Allow recursive discovery of files without the stamp in their path. Use only on narrow roots.",
    )
    parser.add_argument("--recursive-max-files", type=int, default=DEFAULT_RECURSIVE_MAX_FILES)
    parser.add_argument(
        "--chunk-large-files-lines",
        type=int,
        default=DEFAULT_CHUNK_LINES,
        help="Build pointer-style chunk metadata for JSON/Markdown files above this line count. Set 0 to disable.",
    )
    return parser.parse_args(argv)

def build_shared_toolbox_bundle(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    stamp = args.stamp or datetime.now().strftime(DEFAULT_STAMP_FORMAT)
    basename = args.basename or f"{DEFAULT_BASENAME_PREFIX}_{stamp}"
    output_dir = resolve_output_path(repo_root, args.output_dir)

    explicit_reports = coalesce_list(
        list(args.report or []),
        list(args.orchestrator_report or []),
        list(args.gpu_report or []),
        list(args.sync_report or []),
        list(args.contract_replay_report or []),
        list(args.code_interpreter_report or []),
        list(args.python_syntax_report or []),
    )
    report_candidates = coalesce_list(explicit_reports, report_templates_for_stamp(stamp))
    reports, missing_reports = existing_paths(
        repo_root,
        report_candidates,
        label="report",
        include_missing_optional=bool(args.include_missing_optional),
    )

    initial_bundle_paths = [
        repo_relative(output_dir / f"{basename}.json", repo_root),
        repo_relative(output_dir / f"{basename}.md", repo_root),
    ]
    report_declared_artifacts = artifact_hints_from_reports(repo_root, reports)
    artifact_candidates = coalesce_list(
        [args.task_md, args.architecture_md],
        list(args.artifact or []),
        report_declared_artifacts,
        artifact_templates_for_stamp(stamp),
    )
    artifacts, missing_artifacts = existing_paths(
        repo_root,
        artifact_candidates,
        label="artifact",
        include_missing_optional=bool(args.include_missing_optional),
    )

    recursive_report_roots = (
        [] if args.no_recursive_defaults else list(DEFAULT_RECURSIVE_REPORT_ROOTS)
    )
    recursive_artifact_roots = (
        [] if args.no_recursive_defaults else list(DEFAULT_RECURSIVE_ARTIFACT_ROOTS)
    )
    recursive_report_roots = coalesce_list(
        recursive_report_roots, list(args.recursive_report_root or [])
    )
    recursive_artifact_roots = coalesce_list(
        recursive_artifact_roots, list(args.recursive_artifact_root or [])
    )

    summary = build_final_summary(
        repo_root=repo_root,
        stamp=stamp,
        report_paths=reports,
        artifact_paths=artifacts,
        bundle_paths=initial_bundle_paths,
        recommended_next_task_md=args.task_md,
        missing_reports=missing_reports,
        missing_artifacts=missing_artifacts,
    )
    final_json, final_md = write_final_summary(repo_root, summary)
    reports_with_summary = coalesce_list(reports, [repo_relative(final_json, repo_root)])
    artifacts_with_summary = coalesce_list(artifacts, [repo_relative(final_md, repo_root)])

    bundle, outputs_text = build_bundle(
        repo_root,
        reports_with_summary,
        basename,
        output_dir,
        [],
        artifacts_with_summary,
        True,
        int(args.max_included_artifact_chars),
        int(args.max_included_artifacts),
        recursive_report_roots,
        recursive_artifact_roots,
        stamp,
        bool(args.recursive_include_unstamped),
        int(args.recursive_max_files),
        int(args.chunk_large_files_lines),
    )
    bundle_paths = outputs_text.splitlines()
    summary["compact_bundle_paths"] = [
        repo_relative(Path(path), repo_root) for path in bundle_paths
    ]
    summary["recursive_defaults"] = bundle.get("recursive_default_discovery", {})
    summary["chunked_file_index"] = bundle.get("artifact_chunk_index", [])
    final_json, final_md = write_final_summary(repo_root, summary)

    # Rebuild once so the included final summary artifact contains the final
    # bundle path, recursive discovery and chunk index metadata.
    bundle, outputs_text = build_bundle(
        repo_root,
        reports_with_summary,
        basename,
        output_dir,
        [],
        artifacts_with_summary,
        True,
        int(args.max_included_artifact_chars),
        int(args.max_included_artifacts),
        recursive_report_roots,
        recursive_artifact_roots,
        stamp,
        bool(args.recursive_include_unstamped),
        int(args.recursive_max_files),
        int(args.chunk_large_files_lines),
    )
    bundle_paths = outputs_text.splitlines()

    validation_report: dict[str, Any] | None = None
    validation_output_path: Path | None = None
    if args.validate_bundle:
        bundle_json = output_dir / f"{basename}.json"
        validation_report = validate_github_evidence_bundles(repo_root, [bundle_json])
        validation_output = (
            args.validation_output or f"output/validation/{basename}_validation.json"
        )
        validation_output_path = resolve_output_path(repo_root, validation_output)
        write_json_report(validation_report, validation_output_path)

    return {
        "schema_version": 1,
        "kind": "shared_toolbox_ai_to_ai_bundle_builder_result",
        "repo_root": str(repo_root),
        "stamp": stamp,
        "passed": bool(summary.get("passed"))
        and (validation_report is None or bool(validation_report.get("passed"))),
        "final_summary_json": repo_relative(final_json, repo_root),
        "final_summary_markdown": repo_relative(final_md, repo_root),
        "bundle_outputs": [repo_relative(Path(path), repo_root) for path in bundle_paths],
        "validation_output": (
            repo_relative(validation_output_path, repo_root) if validation_output_path else None
        ),
        "bundle_decision": bundle.get("decision"),
        "provider_execution_performed": bool(summary.get("provider_execution_performed")),
        "patch_application_performed": bool(summary.get("patch_application_performed")),
        "sqlite_write_performed": bool(summary.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(summary.get("persistent_memory_write_performed")),
        "recursive_default_discovery": bundle.get("recursive_default_discovery", {}),
        "artifact_chunk_index": bundle.get("artifact_chunk_index", []),
        "errors": list(summary.get("errors") or [])
        + list((validation_report or {}).get("errors") or []),
        "warnings": list(summary.get("warnings") or [])
        + list((validation_report or {}).get("warnings") or []),
        "missing_reports": missing_reports,
        "missing_artifacts": missing_artifacts,
    }

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_shared_toolbox_bundle(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("passed") else 2
