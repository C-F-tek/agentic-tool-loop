#!/usr/bin/env python3
"""Build runtime tool capability manifest for cloud handoff.

Report-only manifest builder. It describes the IA-Carmine runtime tool body:
allowlisted tools, allowed args, guardrails, source files and observed usage.
No provider, Blender runtime, patch application, Git write or SQLite write is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.agent_runtime_tool_broker import TOOL_SPECS
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.agent_runtime_tool_broker import TOOL_SPECS  # type: ignore
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest.json"
DEFAULT_MARKDOWN = "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_capability_manifest.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def classify_tool_category(tool_name: str) -> str:
    if 'inventory' in tool_name or 'line_count' in tool_name:
        return 'inventory'
    if tool_name.startswith('check_') or tool_name.endswith('_smoke'):
        return 'validation'
    if 'context' in tool_name:
        return 'context'
    if 'sqlite' in tool_name or 'memory' in tool_name:
        return 'memory_status'
    if 'code_interpreter' in tool_name:
        return 'static_analysis'
    if 'refactor' in tool_name or 'duplication' in tool_name:
        return 'refactor_analysis'
    return 'support_tool'


def safe_default_mode(tool_name: str) -> str:
    if tool_name == 'runtime_sqlite_memory':
        return 'controlled read-only/status by default; persistent write requires explicit confirm'
    return 'report-only'


def tool_guardrails(tool_name: str) -> list[str]:
    guardrails = [
        'no free shell exposure',
        'broker allowlist required',
        'no provider execution',
        'no patch application',
        'no Blender runtime execution',
        'no Git writes',
    ]
    if tool_name == 'runtime_sqlite_memory':
        guardrails.append('persistent memory write requires allow_persistent_write=true and confirm=persistent_write')
        guardrails.append('operational scratch writes allowed only under output/** when broker-controlled')
    else:
        guardrails.append('no SQLite or persistent memory write')
    return guardrails


def source_entry(repo_root: Path, rel_path: str, role: str) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        'path': rel_path,
        'role': role,
        'exists': path.exists(),
        'size_bytes': path.stat().st_size if path.exists() and path.is_file() else None,
        'sha256': sha256_file(path),
    }


def usage_by_tool(usage_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary = safe_dict(usage_report.get('summary'))
    by_tool = safe_dict(summary.get('by_tool'))
    result: dict[str, dict[str, Any]] = {}
    for tool, value in by_tool.items():
        if isinstance(value, dict):
            result[str(tool)] = value
    for entry in safe_list(usage_report.get('tool_calls')):
        if not isinstance(entry, dict):
            continue
        tool = str(entry.get('tool') or 'unknown')
        item = result.setdefault(tool, {'count': 0, 'executed': 0, 'failed': 0, 'blocked': 0, 'elapsed_seconds': 0.0})
        item['count'] = int(item.get('count') or 0) + 1
        if entry.get('executed') is True:
            item['executed'] = int(item.get('executed') or 0) + 1
        if entry.get('failed') is True:
            item['failed'] = int(item.get('failed') or 0) + 1
        if entry.get('blocked') is True:
            item['blocked'] = int(item.get('blocked') or 0) + 1
    return result


def caller_modes(usage_report: dict[str, Any]) -> dict[str, Any]:
    summary = safe_dict(usage_report.get('summary'))
    return {
        'observed_by_caller_ai': safe_dict(summary.get('by_caller_ai')),
        'observed_by_phase': safe_dict(summary.get('by_phase')),
        'supported_callers': ['gpu', 'npu', 'orchestrator', 'ollama-local', 'deterministic'],
        'cloud_handoff_rule': 'cloud receives capability manifest plus runtime usage telemetry; local execution remains broker-controlled',
    }


def build_tool_rows(repo_root: Path, usage: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted(TOOL_SPECS):
        spec = TOOL_SPECS[name]
        rows.append(
            {
                'tool_name': spec.name,
                'category': classify_tool_category(spec.name),
                'description': spec.description,
                'allowed_args': list(spec.allowed_args),
                'safe_default_mode': safe_default_mode(spec.name),
                'guardrails': tool_guardrails(spec.name),
                'usage_observed': usage.get(spec.name, {'count': 0, 'executed': 0, 'failed': 0, 'blocked': 0, 'elapsed_seconds': 0.0}),
                'broker_builder': getattr(spec.builder, '__name__', ''),
            }
        )
    return rows


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    usage_path = resolve_output_path(repo_root, args.tool_usage) if args.tool_usage else None
    usage_report = read_json(usage_path) if usage_path else {}
    usage = usage_by_tool(usage_report)
    sources = [
        source_entry(repo_root, 'Tools/ai/agent_runtime_tool_broker.py', 'runtime_tool_broker_allowlist_source'),
        source_entry(repo_root, 'Tools/ai/build_runtime_tool_usage_telemetry.py', 'runtime_tool_usage_telemetry_builder'),
        source_entry(repo_root, 'Tools/ai/build_semantic_evidence_chunks.py', 'semantic_cloud_handoff_chunker'),
        source_entry(repo_root, 'Tools/ai/build_shared_toolbox_ai_to_ai_bundle.py', 'shared_toolbox_bundle_builder'),
    ]
    if usage_path:
        sources.append(source_entry(repo_root, repo_rel(repo_root, usage_path), 'observed_runtime_tool_usage_report'))
    return {
        'schema_version': 1,
        'kind': 'runtime_tool_capability_manifest',
        'generated_at': now_iso(),
        'repo_root': str(repo_root),
        'passed': True,
        'errors': [],
        'warnings': [],
        'provider_execution_performed': False,
        'patch_application_performed': False,
        'source_writes_performed': False,
        'sqlite_write_performed': False,
        'persistent_memory_write_performed': False,
        'blender_runtime_execution_performed': False,
        'tool_count': len(TOOL_SPECS),
        'tool_usage_summary': safe_dict(usage_report.get('summary')),
        'declared_runtime_tool_counters': safe_dict(usage_report.get('declared_runtime_tool_counters')),
        'tools': build_tool_rows(repo_root, usage),
        'caller_modes': caller_modes(usage_report),
        'source_files': sources,
        'cloud_handoff_policy': {
            'include_with_evidence_chunks': True,
            'include_runtime_usage_telemetry': True,
            'include_patch_plan_and_recommendations': True,
            'no_free_shell': True,
            'tool_execution_requires_local_broker': True,
            'cloud_model_may_reason_about_tools_but_must_not_execute_them': True,
        },
        'guardrails': {
            'report_only': True,
            'committable_location': 'docs/LOCAL_VALIDATION_EVIDENCE',
            'provider_execution_performed': False,
            'patch_application_performed': False,
            'sqlite_write_performed': False,
            'persistent_memory_write_performed': False,
            'blender_runtime_execution_performed': False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ['# Runtime Tool Capability Manifest', '']
    lines.append(f"- Passed: `{report.get('passed')}`")
    lines.append(f"- Tool count: `{report.get('tool_count')}`")
    usage_summary = safe_dict(report.get('tool_usage_summary'))
    lines.append(f"- Declared runtime tool requests: `{usage_summary.get('runtime_tool_request_count')}`")
    lines.append(f"- Broker runtime tool executions: `{usage_summary.get('runtime_tool_execution_count')}`")
    lines.append(f"- Declared not executed count: `{usage_summary.get('declared_not_executed_count')}`")
    lines.append(f"- Provider execution performed: `{report.get('provider_execution_performed')}`")
    lines.append(f"- Patch application performed: `{report.get('patch_application_performed')}`")
    lines.append('')
    lines.append('## Cloud handoff policy')
    lines.append('')
    for key, value in safe_dict(report.get('cloud_handoff_policy')).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append('')
    lines.append('## Caller modes')
    lines.append('')
    modes = safe_dict(report.get('caller_modes'))
    lines.append(f"- Supported callers: `{modes.get('supported_callers')}`")
    lines.append(f"- Rule: {modes.get('cloud_handoff_rule')}")
    lines.append('')
    lines.append('## Tools')
    lines.append('')
    for tool in safe_list(report.get('tools')):
        if not isinstance(tool, dict):
            continue
        lines.append(f"### `{tool.get('tool_name')}`")
        lines.append('')
        lines.append(f"- Category: `{tool.get('category')}`")
        lines.append(f"- Safe mode: `{tool.get('safe_default_mode')}`")
        lines.append(f"- Description: {tool.get('description')}")
        lines.append(f"- Allowed args: `{tool.get('allowed_args')}`")
        lines.append(f"- Usage observed: `{tool.get('usage_observed')}`")
        lines.append('- Guardrails:')
        for guardrail in safe_list(tool.get('guardrails')):
            lines.append(f"  - {guardrail}")
        lines.append('')
    lines.append('## Source files')
    lines.append('')
    for source in safe_list(report.get('source_files')):
        if isinstance(source, dict):
            lines.append(f"- `{source.get('path')}` role=`{source.get('role')}` exists=`{source.get('exists')}` sha256=`{source.get('sha256')}`")
    lines.append('')
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--tool-usage', default='', help='runtime_tool_usage_telemetry JSON path')
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--markdown-output', default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_output_path(repo_root, args.output)
    markdown = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end='')
    write_text_report(render_markdown(report), markdown)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
