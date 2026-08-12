#!/usr/bin/env python3
"""Build semantic, upload-friendly evidence chunks.

The tool is report-only: it reads existing evidence/report files and writes
chunk manifests plus ordered chunk files. Ollama is enabled by default for local
chunk summaries; use --no-ollama to disable it. No NPU/GPU audit is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"
DEFAULT_CHUNK_MAX_CHARS = 12000
DEFAULT_CHUNK_OVERLAP_LINES = 12
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def split_path_values(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for item in str(value).split(','):
            item = item.strip()
            if item:
                out.append(item)
    return out


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding='utf-8-sig'), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding='utf-8', errors='replace'), None
        except OSError as exc:
            return '', str(exc)
    except OSError as exc:
        return '', str(exc)


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r'[^A-Za-z0-9._-]+', '_', value.strip())
    text = re.sub(r'_+', '_', text).strip('._-')
    return text[:90] or fallback


def compact_text(value: str, limit: int = 220) -> str:
    text = re.sub(r'\s+', ' ', value).strip()
    return text[:limit] + ('...' if len(text) > limit else '')


def line_count(text: str) -> int:
    return len(text.splitlines())


def markdown_sections(lines: list[str]) -> list[dict[str, Any]]:
    headings: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
        if match:
            headings.append((idx, match.group(2).strip()))
    if not headings:
        return []
    sections: list[dict[str, Any]] = []
    for pos, (start, title) in enumerate(headings):
        end = headings[pos + 1][0] - 1 if pos + 1 < len(headings) else len(lines)
        if start <= end:
            sections.append({'line_start': start, 'line_end': end, 'title': title, 'kind': 'markdown_heading_section'})
    return sections


def json_sections(lines: list[str]) -> list[dict[str, Any]]:
    anchors: list[tuple[int, str]] = []
    pattern = re.compile(r'^\s{0,4}"([A-Za-z0-9_.$-]{2,120})"\s*:\s*([\[{"0-9tfn-]|$)')
    for idx, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if match:
            key = match.group(1)
            if key not in {'path', 'id', 'kind', 'passed', 'errors', 'warnings'}:
                anchors.append((idx, key))
    if not anchors:
        return []
    sections: list[dict[str, Any]] = []
    for pos, (start, key) in enumerate(anchors):
        end = anchors[pos + 1][0] - 1 if pos + 1 < len(anchors) else len(lines)
        if start <= end:
            sections.append({'line_start': start, 'line_end': end, 'title': key, 'kind': 'json_key_section'})
    return sections


def fallback_sections(lines: list[str], max_chars: int) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    start = 1
    current_chars = 0
    for idx, line in enumerate(lines, start=1):
        current_chars += len(line) + 1
        if current_chars >= max_chars and idx >= start:
            sections.append({'line_start': start, 'line_end': idx, 'title': f'lines {start}-{idx}', 'kind': 'size_window_section'})
            start = idx + 1
            current_chars = 0
    if start <= len(lines):
        sections.append({'line_start': start, 'line_end': len(lines), 'title': f'lines {start}-{len(lines)}', 'kind': 'size_window_section'})
    return sections


def detect_sections(path: Path, text: str, max_chars: int) -> list[dict[str, Any]]:
    lines = text.splitlines()
    suffix = path.suffix.lower()
    if suffix in {'.md', '.markdown'}:
        sections = markdown_sections(lines)
    elif suffix == '.json':
        sections = json_sections(lines)
    else:
        sections = []
    if not sections:
        return fallback_sections(lines, max_chars)
    return sections


def section_text(lines: list[str], start: int, end: int) -> str:
    return '\n'.join(lines[start - 1:end])


def split_large_section(lines: list[str], section: dict[str, Any], max_chars: int) -> list[dict[str, Any]]:
    start = int(section['line_start'])
    end = int(section['line_end'])
    out: list[dict[str, Any]] = []
    current_start = start
    current_chars = 0
    for idx in range(start, end + 1):
        current_chars += len(lines[idx - 1]) + 1
        if current_chars >= max_chars and idx >= current_start:
            out.append({'line_start': current_start, 'line_end': idx, 'title': section['title'], 'kind': section['kind'] + '_split'})
            current_start = idx + 1
            current_chars = 0
    if current_start <= end:
        out.append({'line_start': current_start, 'line_end': end, 'title': section['title'], 'kind': section['kind'] + ('_split' if len(out) else '')})
    return out


def normalize_sections(lines: list[str], sections: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in sections:
        text = section_text(lines, int(section['line_start']), int(section['line_end']))
        if len(text) > max_chars:
            out.extend(split_large_section(lines, section, max_chars))
        else:
            out.append(section)
    return out


def pack_sections(lines: list[str], sections: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for section in sections:
        text = section_text(lines, int(section['line_start']), int(section['line_end']))
        extra = len(text) + 1
        if current and current_chars + extra > max_chars:
            chunks.append(build_chunk_from_sections(current))
            current = []
            current_chars = 0
        current.append(section)
        current_chars += extra
    if current:
        chunks.append(build_chunk_from_sections(current))
    return chunks


def build_chunk_from_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    start = min(int(item['line_start']) for item in sections)
    end = max(int(item['line_end']) for item in sections)
    titles = [str(item.get('title') or '') for item in sections if item.get('title')]
    kinds = sorted(set(str(item.get('kind') or 'section') for item in sections))
    return {
        'line_start': start,
        'line_end': end,
        'section_titles': titles[:12],
        'section_kinds': kinds,
    }


def deterministic_summary(text: str, titles: list[str]) -> str:
    title_part = '; '.join(titles[:5]) if titles else 'no explicit section title'
    preview = compact_text(text, 260)
    return f"Chunk deterministico. Sezioni: {title_part}. Preview: {preview}"


def call_ollama_summary(
    *,
    host: str,
    model: str,
    text: str,
    titles: list[str],
    timeout: int,
    max_input_chars: int,
    keep_alive: str,
) -> tuple[str | None, str | None, float]:
    prompt = (
        "Sei un summarizer locale per evidence bundle tecnici. "
        "Riassumi questo chunk in italiano tecnico in massimo 5 righe. "
        "Indica: scopo, segnali principali, eventuali guardrail o errori, perché serve a una AI cloud. "
        "Non inventare.\n\n"
        f"Titoli sezioni: {titles[:8]}\n\n"
        f"Chunk:\n{text[:max_input_chars]}"
    )
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'keep_alive': keep_alive,
        'options': {'temperature': 0.1, 'num_predict': 220},
    }
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        host.rstrip('/') + '/api/generate',
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(exc), round(time.perf_counter() - started, 3)
    elapsed = round(time.perf_counter() - started, 3)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f'invalid ollama JSON: {exc}', elapsed
    text_out = str(data.get('response') or '').strip()
    if not text_out:
        return None, 'empty ollama response', elapsed
    return text_out, None, elapsed


def fence_for(text: str) -> str:
    return '````' if '```' in text else '```'


def render_chunk_file(
    *,
    source_rel: str,
    source_sha256: str | None,
    chunk: dict[str, Any],
    chunk_index: int,
    chunk_count: int,
    content: str,
    context_before: str,
    context_after: str,
    summary: str,
    summary_source: str,
    previous_file: str | None,
    next_file: str | None,
    language_hint: str,
) -> str:
    fence = fence_for(content)
    lines = [
        f"# Evidence Chunk {chunk_index:04d}/{chunk_count:04d}",
        "",
        f"- source: `{source_rel}`",
        f"- source_sha256: `{source_sha256}`",
        f"- line_start: `{chunk['line_start']}`",
        f"- line_end: `{chunk['line_end']}`",
        f"- section_kinds: `{chunk.get('section_kinds')}`",
        f"- previous_chunk_file: `{previous_file or ''}`",
        f"- next_chunk_file: `{next_file or ''}`",
        f"- summary_source: `{summary_source}`",
        "",
        "## Local chunk summary",
        "",
        summary,
        "",
    ]
    if context_before:
        lines.extend(["## Context before", "", context_before, ""])
    lines.extend(["## Chunk content", "", f"{fence}{language_hint}", content, fence, ""])
    if context_after:
        lines.extend(["## Context after", "", context_after, ""])
    return '\n'.join(lines)


def chunk_one_source(args: argparse.Namespace, repo_root: Path, source_path: Path, chunk_dir: Path, warnings: list[str]) -> dict[str, Any]:
    text, error = read_text(source_path)
    rel = repo_rel(repo_root, source_path)
    if error:
        return {'path': rel, 'exists': source_path.exists(), 'ok': False, 'error': error, 'chunks': []}
    lines = text.splitlines()
    sections = detect_sections(source_path, text, int(args.chunk_max_chars))
    sections = normalize_sections(lines, sections, int(args.chunk_max_chars))
    chunks = pack_sections(lines, sections, int(args.chunk_max_chars))
    source_sha = sha256_file(source_path)
    suffix_slug = source_path.suffix.lower().lstrip('.') or 'txt'
    sha_slug = (source_sha or 'nosha')[:12]
    source_slug = slugify(f"{Path(rel).stem}_{suffix_slug}_{sha_slug}", 'source')
    chunk_entries: list[dict[str, Any]] = []
    language_hint = source_path.suffix.lower().lstrip('.') or 'text'
    pending_files: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_file = chunk_dir / f"{source_slug}_chunk_{idx:04d}.md"
        pending_files.append(repo_rel(repo_root, chunk_file))
    for idx, chunk in enumerate(chunks, start=1):
        start = int(chunk['line_start'])
        end = int(chunk['line_end'])
        content = section_text(lines, start, end)
        before_start = max(1, start - int(args.chunk_overlap_lines))
        after_end = min(len(lines), end + int(args.chunk_overlap_lines))
        context_before = section_text(lines, before_start, start - 1) if before_start < start else ''
        context_after = section_text(lines, end + 1, after_end) if end < after_end else ''
        summary_source = 'deterministic'
        summary = deterministic_summary(content, list(chunk.get('section_titles') or []))
        ollama_elapsed = 0.0
        ollama_error = None
        if not args.no_ollama:
            generated, ollama_error, ollama_elapsed = call_ollama_summary(
                host=args.ollama_host,
                model=args.ollama_model,
                text=content,
                titles=list(chunk.get('section_titles') or []),
                timeout=int(args.ollama_timeout_seconds),
                max_input_chars=int(args.ollama_max_input_chars),
                keep_alive=args.ollama_keep_alive,
            )
            if generated:
                summary = generated
                summary_source = 'ollama'
            elif ollama_error:
                warnings.append(f"{rel} chunk {idx}: Ollama summary fallback used: {ollama_error}")
        previous_file = pending_files[idx - 2] if idx > 1 else None
        next_file = pending_files[idx] if idx < len(pending_files) else None
        chunk_file = chunk_dir / f"{source_slug}_chunk_{idx:04d}.md"
        chunk_text = render_chunk_file(
            source_rel=rel,
            source_sha256=source_sha,
            chunk=chunk,
            chunk_index=idx,
            chunk_count=len(chunks),
            content=content,
            context_before=context_before,
            context_after=context_after,
            summary=summary,
            summary_source=summary_source,
            previous_file=previous_file,
            next_file=next_file,
            language_hint=language_hint,
        )
        chunk_file.write_text(chunk_text, encoding='utf-8', newline='\n')
        chunk_entries.append(
            {
                'chunk_id': f"{rel}#L{start}-L{end}",
                'chunk_file': repo_rel(repo_root, chunk_file),
                'source_path': rel,
                'source_sha256': source_sha,
                'line_start': start,
                'line_end': end,
                'raw_chars': len(content),
                'chunk_sha256': sha256_text(chunk_text),
                'summary': summary,
                'summary_source': summary_source,
                'ollama_elapsed_seconds': ollama_elapsed,
                'ollama_error': ollama_error,
                'previous_chunk_file': previous_file,
                'next_chunk_file': next_file,
                'section_titles': chunk.get('section_titles') or [],
                'section_kinds': chunk.get('section_kinds') or [],
            }
        )
    return {
        'path': rel,
        'exists': source_path.exists(),
        'ok': True,
        'size_bytes': source_path.stat().st_size if source_path.exists() else None,
        'line_count': len(lines),
        'sha256': source_sha,
        'chunk_count': len(chunk_entries),
        'chunks': chunk_entries,
    }


def render_manifest_markdown(report: dict[str, Any]) -> str:
    lines = ["# Semantic Evidence Chunk Manifest", ""]
    lines.append(f"- Passed: `{report.get('passed')}`")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(f"- Ollama enabled: `{report.get('ollama', {}).get('enabled')}`")
    lines.append(f"- Ollama model: `{report.get('ollama', {}).get('model')}`")
    lines.append(f"- Chunk files: `{len(report.get('chunk_files') or [])}`")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source in report.get('sources', []):
        lines.append(f"- `{source.get('path')}` chunks=`{source.get('chunk_count')}` lines=`{source.get('line_count')}` sha256=`{source.get('sha256')}`")
        for chunk in source.get('chunks', [])[:20]:
            lines.append(f"  - `{chunk.get('chunk_file')}` lines `{chunk.get('line_start')}-{chunk.get('line_end')}` summary_source=`{chunk.get('summary_source')}`")
        if len(source.get('chunks', [])) > 20:
            lines.append(f"  - ... {len(source.get('chunks', [])) - 20} more chunks")
    if report.get('warnings'):
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for warning in report.get('warnings', [])[:80]:
            lines.append(f"- {warning}")
    lines.append("")
    return '\n'.join(lines)


def write_zip(zip_output: Path, repo_root: Path, paths: list[Path]) -> str:
    zip_output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_output, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if path.exists() and path.is_file():
                zf.write(path, repo_rel(repo_root, path))
    return repo_rel(repo_root, zip_output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--basename', required=True)
    parser.add_argument('--source', action='append', default=[], help='Source evidence/report file. Repeatable or comma-separated.')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--chunk-output-dir', default='')
    parser.add_argument('--chunk-max-chars', type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument('--chunk-overlap-lines', type=int, default=DEFAULT_CHUNK_OVERLAP_LINES)
    parser.add_argument('--no-ollama', action='store_true', help='Disable local Ollama summaries. Ollama is enabled by default.')
    parser.add_argument('--ollama-host', default=DEFAULT_OLLAMA_HOST)
    parser.add_argument('--ollama-model', default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument('--ollama-timeout-seconds', type=int, default=45)
    parser.add_argument('--ollama-max-input-chars', type=int, default=6000)
    parser.add_argument('--ollama-keep-alive', default='30m')
    parser.add_argument('--zip-output', default='', help='Optional zip path containing manifest and chunk files.')
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_output_path(repo_root, args.output_dir)
    chunk_dir = resolve_output_path(repo_root, args.chunk_output_dir) if args.chunk_output_dir else output_dir / f"{args.basename}_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for old_chunk in chunk_dir.glob('*.md'):
        old_chunk.unlink()

    warnings: list[str] = []
    errors: list[str] = []
    source_values = split_path_values(list(args.source or []))
    if not source_values:
        errors.append('no source files provided')
    sources: list[dict[str, Any]] = []
    for raw in source_values:
        path = resolve_output_path(repo_root, raw)
        if not path.exists() or not path.is_file():
            warnings.append(f'missing source skipped: {repo_rel(repo_root, path)}')
            continue
        sources.append(chunk_one_source(args, repo_root, path, chunk_dir, warnings))

    chunk_files = [chunk['chunk_file'] for source in sources for chunk in source.get('chunks', [])]
    duplicated_chunk_files = sorted({path for path in chunk_files if chunk_files.count(path) > 1})
    if duplicated_chunk_files:
        errors.append(f"duplicate chunk_file paths detected: {duplicated_chunk_files[:20]}")
    report = {
        'schema_version': 1,
        'kind': 'semantic_evidence_chunk_manifest',
        'generated_at': now_iso(),
        'repo_root': str(repo_root),
        'passed': not errors,
        'errors': errors,
        'warnings': warnings,
        'provider_execution_performed': False,
        'patch_application_performed': False,
        'source_writes_performed': True,
        'sqlite_write_performed': False,
        'persistent_memory_write_performed': False,
        'blender_runtime_execution_performed': False,
        'ollama': {
            'enabled': not args.no_ollama,
            'model': args.ollama_model,
            'host': args.ollama_host,
            'mode': 'local_direct_no_gpu_npu_audit',
            'disable_flag': '--no-ollama',
        },
        'chunking_policy': {
            'semantic_boundaries_first': True,
            'fallback_size_windows': True,
            'chunk_max_chars': args.chunk_max_chars,
            'chunk_overlap_lines': args.chunk_overlap_lines,
            'not_plain_truncation': True,
            'previous_next_links': True,
            'source_sha256_preserved': True,
        },
        'sources': sources,
        'chunk_files': chunk_files,
        'chunk_output_dir': repo_rel(repo_root, chunk_dir),
        'zip_output': None,
        'guardrails': {
            'report_only': True,
            'committable_location': 'docs/LOCAL_VALIDATION_EVIDENCE',
            'raw_output_commit_allowed': False,
            'provider_execution_performed': False,
            'npu_audit_performed': False,
            'gpu_audit_performed': False,
        },
    }
    manifest_json = output_dir / f"{args.basename}_chunk_manifest.json"
    manifest_md = output_dir / f"{args.basename}_chunk_manifest.md"
    write_json_report(report, manifest_json)
    write_text_report(render_manifest_markdown(report), manifest_md)
    if args.zip_output:
        zip_path = resolve_output_path(repo_root, args.zip_output)
        zip_sources = [manifest_json, manifest_md] + [resolve_output_path(repo_root, path) for path in chunk_files]
        report['zip_output'] = write_zip(zip_path, repo_root, zip_sources)
        write_json_report(report, manifest_json)
        write_text_report(render_manifest_markdown(report), manifest_md)
    print(json.dumps({'passed': report['passed'], 'manifest_json': str(manifest_json), 'manifest_md': str(manifest_md), 'chunk_count': len(chunk_files), 'zip_output': report.get('zip_output')}, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
