#!/usr/bin/env python3
"""Run an explicit all-resources repository review.

This is an artifact-first IA-Carmine helper. It can inspect Markdown, code,
RAW/output artifacts, generated indexes, SQLite memory databases in read-only
mode, NPU/OpenVINO tool definitions and GPU/Ollama tool definitions.

Default behavior is CPU-only and report-only:

- no provider execution unless --use-ollama is explicitly passed;
- no live NPU execution;
- no patch application;
- no source writes except requested JSON/Markdown review outputs;
- no Blender runtime execution;
- no full analysis JSON edits;
- no SQLite DB writes or commits.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUTPUT_JSON = "output/ai_pipeline/megalithic_repo_review.json"
DEFAULT_OUTPUT_MD = "output/ai_pipeline/megalithic_repo_review.md"
DEFAULT_PROPOSALS_JSON = "output/ai_pipeline/megalithic_repo_review_proposals.json"

DOC_EXTENSIONS = {".md"}
CODE_EXTENSIONS = {".py", ".ps1", ".sh", ".yaml", ".yml", ".json"}
RAW_EXTENSIONS = {".json", ".jsonl", ".md", ".txt", ".log", ".csv", ".yaml", ".yml"}
SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
DEFAULT_EXCLUDE_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "renders"}
DEFAULT_REPORTS = (
    "output/validation/docs_contract_drift.json",
    "output/validation/code_contract_drift.json",
    "output/validation/ai_workload_report_quality.json",
    "output/validation/validation_report_contract.json",
    "output/validation/local_ai_resource_lanes.json",
    "output/validation/local_provider_probe.json",
    "output/validation/ai_workload_quality_lane_routing.json",
    "output/validation/npu_decode_quality_remediation.json",
    "output/validation/npu_review_metadata.json",
)
CANONICAL_DOCS = (
    "AGENTS.md",
    "WORKFLOW.md",
    "docs/AI_DOCS_ENTRYPOINT.md",
    "docs/LOCAL_AI_CORE_TOOL_ACTIVATION.md",
    "docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md",
    "docs/JSON_SCHEMAS.md",
    "Tools/validation/README.md",
)
CONTRACT_TERMS = (
    "provider_execution_performed",
    "patch_application_performed",
    "manual_review_only",
    "ai_workload_report_quality",
    "code_contract_drift",
    "docs_contract_drift",
    "NPU",
    "Ollama",
)
PROVIDER_TERMS = {
    "npu": ("NPU", "OpenVINO", "openvino", "openvino_genai", "npu"),
    "gpu_cuda": ("Ollama", "ollama", "gpu_cuda", "CUDA", "cuda", "GPU"),
    "cpu": ("CPU", "cpu", "validation", "contract", "report"),
}
COMMON_DUPLICATE_SYMBOLS = {"main", "read_text", "read_json_if_exists", "render_markdown", "now_iso", "split_path_values", "resolve_output_path", "write_json_report"}
PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+)(?:\.[A-Za-z0-9_.-]+)?")
POWERSHELL_FUNC_RE = re.compile(r"(?im)^\s*function\s+([A-Za-z0-9_-]+)\s*(?:\{|$)")
SHELL_FUNC_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")
MD_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


@dataclass(frozen=True)
class FileRecord:
    path: str
    extension: str
    kind: str
    chars: int
    lines: int
    symbols: tuple[str, ...]
    headings: tuple[str, ...]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def split_path_values(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized.replace("\\", "/"))
    return out


def is_excluded(path: Path, repo_root: Path, *, include_output: bool, include_index: bool) -> bool:
    rel_parts = path.relative_to(repo_root).parts
    excludes = set(DEFAULT_EXCLUDE_DIRS)
    if not include_output:
        excludes.add("output")
    if not include_index:
        excludes.add("indexAI")
    return any(part in excludes for part in rel_parts)


def iter_files(
    repo_root: Path,
    *,
    include_all_docs: bool,
    include_all_code: bool,
    include_output: bool,
    include_index: bool,
    include_raw: bool,
    include_sqlite_memory: bool,
    max_files: int,
) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    docs: list[Path] = []
    code: list[Path] = []
    raw: list[Path] = []
    sqlite_files: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if is_excluded(path, repo_root, include_output=include_output or include_raw, include_index=include_index):
            continue
        suffix = path.suffix.lower()
        rel = path.relative_to(repo_root).as_posix()
        if suffix in DOC_EXTENSIONS and (include_all_docs or rel.startswith(("docs/", "Tools/", "AGENTS", "WORKFLOW"))):
            docs.append(path)
        elif suffix in CODE_EXTENSIONS and (include_all_code or rel.startswith(("Tools/", "Scripting/", "docs/"))):
            code.append(path)
        if include_raw and suffix in RAW_EXTENSIONS and rel.startswith(("output/", "docs/LOCAL_VALIDATION_EVIDENCE/", "indexAI/")):
            raw.append(path)
        if include_sqlite_memory and suffix in SQLITE_EXTENSIONS:
            sqlite_files.append(path)
        if max_files > 0 and len(docs) + len(code) + len(raw) + len(sqlite_files) >= max_files:
            break
    return docs, code, raw, sqlite_files


def read_text(path: Path, max_chars: int = 0) -> tuple[str, bool, str | None]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return "", False, f"{type(exc).__name__}: {exc}"
    truncated = bool(max_chars > 0 and len(text) > max_chars)
    if truncated:
        text = text[:max_chars]
    return text, truncated, None


def python_symbols(text: str) -> tuple[str, ...]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError:
        return tuple(sorted(set(re.findall(r"(?m)^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", text))))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return tuple(sorted(set(names)))


def extract_symbols(path: Path, text: str) -> tuple[str, ...]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return python_symbols(text)
    if suffix == ".ps1":
        return tuple(sorted(set(POWERSHELL_FUNC_RE.findall(text))))
    if suffix == ".sh":
        return tuple(sorted(set(SHELL_FUNC_RE.findall(text))))
    return ()


def extract_headings(text: str) -> tuple[str, ...]:
    return tuple(item.strip()[:160] for item in MD_HEADING_RE.findall(text))


def build_file_records(repo_root: Path, files: Iterable[Path], *, max_chars_per_file: int) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path in files:
        text, _truncated, error = read_text(path, max_chars_per_file)
        if error:
            continue
        rel = path.relative_to(repo_root).as_posix()
        suffix = path.suffix.lower()
        kind = "doc" if suffix in DOC_EXTENSIONS else "code"
        records.append(FileRecord(path=rel, extension=suffix, kind=kind, chars=len(text), lines=len(text.splitlines()), symbols=extract_symbols(path, text), headings=extract_headings(text) if suffix in DOC_EXTENSIONS else ()))
    return records


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "data": None, "error": "missing"}
    try:
        return {"path": str(path), "exists": True, "data": json.loads(path.read_text(encoding="utf-8-sig")), "error": ""}
    except Exception as exc:
        return {"path": str(path), "exists": True, "data": None, "error": f"{type(exc).__name__}: {exc}"}


def collect_reports(repo_root: Path, report_files: list[str]) -> list[dict[str, Any]]:
    reports = []
    for rel in dict.fromkeys(report_files):
        path = repo_root / rel
        item = read_json_if_exists(path)
        data = item.get("data")
        reports.append({"path": rel, "exists": item["exists"], "kind": data.get("kind") if isinstance(data, dict) else None, "passed": data.get("passed") if isinstance(data, dict) else None, "errors": data.get("errors", [])[:10] if isinstance(data, dict) and isinstance(data.get("errors", []), list) else [], "warnings": data.get("warnings", [])[:10] if isinstance(data, dict) and isinstance(data.get("warnings", []), list) else [], "provider_execution_performed": data.get("provider_execution_performed") if isinstance(data, dict) else None, "error": item.get("error")})
    return reports


def collect_raw_artifacts(repo_root: Path, raw_files: list[Path], *, max_raw_files: int) -> list[dict[str, Any]]:
    artifacts = []
    for path in raw_files[:max_raw_files]:
        rel = path.relative_to(repo_root).as_posix()
        text, truncated, error = read_text(path, max_chars=24_000)
        json_kind = None
        if path.suffix.lower() == ".json":
            data = read_json_if_exists(path).get("data")
            json_kind = data.get("kind") if isinstance(data, dict) else None
        artifacts.append({"path": rel, "extension": path.suffix.lower(), "chars": len(text), "lines": len(text.splitlines()), "truncated": truncated, "error": error or "", "json_kind": json_kind})
    return artifacts


def inspect_sqlite_memory(repo_root: Path, sqlite_files: list[Path], *, max_tables: int) -> list[dict[str, Any]]:
    out = []
    for path in sqlite_files:
        rel = path.relative_to(repo_root).as_posix()
        item: dict[str, Any] = {"path": rel, "read_only": True, "tables": [], "error": ""}
        try:
            uri = f"file:{path.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                rows = conn.execute("select name from sqlite_master where type='table' order by name").fetchall()
                for (name,) in rows[:max_tables]:
                    try:
                        count = conn.execute(f"select count(*) from {json.dumps(name)}").fetchone()[0]
                    except Exception:
                        count = None
                    item["tables"].append({"name": name, "row_count": count})
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        out.append(item)
    return out


def discover_provider_functions(records: list[FileRecord]) -> dict[str, Any]:
    lanes: dict[str, list[dict[str, Any]]] = {"npu": [], "gpu_cuda": [], "cpu": []}
    for record in records:
        searchable = " ".join([record.path, *record.symbols])
        for lane, terms in PROVIDER_TERMS.items():
            if any(term in searchable for term in terms):
                lanes[lane].append({"path": record.path, "symbols": list(record.symbols[:40]), "lines": record.lines})
                break
    return {lane: items[:80] for lane, items in lanes.items()}


def scan_doc_references(repo_root: Path, docs: Iterable[Path]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for doc in docs:
        text, _truncated, error = read_text(doc)
        if error:
            continue
        doc_rel = doc.relative_to(repo_root).as_posix()
        for match in PATH_RE.findall(text):
            normalized = match.strip("`.,:)];\"").replace("\\", "/")
            if not normalized or normalized.startswith(("http/", "https/")):
                continue
            key = (doc_rel, normalized)
            if key in seen:
                continue
            seen.add(key)
            target = repo_root / normalized
            refs.append({"doc": doc_rel, "reference": normalized, "exists": target.exists(), "kind": "path_reference"})
    return refs


def compare_docs_to_code(repo_root: Path, docs: list[Path], file_records: list[FileRecord]) -> dict[str, Any]:
    code_paths = {record.path for record in file_records if record.kind == "code"}
    symbol_to_paths: dict[str, list[str]] = {}
    for record in file_records:
        if record.kind != "code":
            continue
        for symbol in record.symbols:
            symbol_to_paths.setdefault(symbol, []).append(record.path)
    path_refs = scan_doc_references(repo_root, docs)
    missing_path_refs = [item for item in path_refs if not item["exists"] and not item["reference"].startswith("output/")]
    doc_code_refs = [item for item in path_refs if item["reference"] in code_paths]
    symbol_refs: list[dict[str, Any]] = []
    candidates = sorted(symbol_to_paths.keys(), key=len, reverse=True)[:1200]
    for doc in docs:
        text, _truncated, error = read_text(doc, max_chars=220_000)
        if error:
            continue
        doc_rel = doc.relative_to(repo_root).as_posix()
        for symbol in candidates:
            if len(symbol) >= 4 and symbol in text:
                symbol_refs.append({"doc": doc_rel, "symbol": symbol, "code_paths": symbol_to_paths[symbol][:8]})
    return {"code_path_count": len(code_paths), "doc_path_reference_count": len(path_refs), "doc_code_reference_count": len(doc_code_refs), "missing_path_reference_count": len(missing_path_refs), "missing_path_references": missing_path_refs[:160], "symbol_reference_count": len(symbol_refs), "symbol_references_sample": symbol_refs[:160]}


def compare_docs_to_docs(repo_root: Path, records: list[FileRecord]) -> dict[str, Any]:
    canonical_results = []
    for rel in CANONICAL_DOCS:
        path = repo_root / rel
        text, _truncated, error = read_text(path, max_chars=220_000) if path.exists() else ("", False, "missing")
        missing_terms = [term for term in CONTRACT_TERMS if term not in text]
        canonical_results.append({"path": rel, "exists": path.exists(), "missing_terms": missing_terms, "error": error or ""})
    heading_index: dict[str, list[str]] = {}
    for record in records:
        if record.kind != "doc":
            continue
        for heading in record.headings:
            normalized = heading.strip().lower()
            if len(normalized) >= 6:
                heading_index.setdefault(normalized, []).append(record.path)
    duplicates = [{"heading": heading, "docs": paths[:12], "count": len(paths)} for heading, paths in sorted(heading_index.items()) if len(paths) > 4][:80]
    return {"canonical_doc_count": len(CANONICAL_DOCS), "canonical_docs": canonical_results, "canonical_missing_count": sum(1 for item in canonical_results if item["missing_terms"] or not item["exists"]), "duplicate_heading_count": len(duplicates), "duplicate_headings": duplicates}


def compare_code_to_code(records: list[FileRecord]) -> dict[str, Any]:
    symbol_index: dict[str, list[str]] = {}
    for record in records:
        if record.kind != "code":
            continue
        for symbol in record.symbols:
            symbol_index.setdefault(symbol, []).append(record.path)
    duplicates = [{"symbol": symbol, "paths": paths[:16], "count": len(paths)} for symbol, paths in sorted(symbol_index.items()) if len(paths) > 1 and symbol not in COMMON_DUPLICATE_SYMBOLS][:160]
    return {"symbol_count": len(symbol_index), "duplicate_symbol_count": len(duplicates), "duplicate_symbols": duplicates, "provider_functions": discover_provider_functions(records)}


def deterministic_findings(reports: list[dict[str, Any]], doc_code: dict[str, Any], doc_doc: dict[str, Any], code_code: dict[str, Any], sqlite_memory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    failed_reports = [r for r in reports if r.get("passed") is False]
    missing_reports = [r for r in reports if not r.get("exists")]
    if failed_reports:
        findings.append({"severity": "high", "area": "validation_reports", "title": "Some validation reports are failing", "details": [f"{r['path']}: {r.get('errors')}" for r in failed_reports[:10]]})
    if missing_reports:
        findings.append({"severity": "medium", "area": "validation_reports", "title": "Some expected validation reports are missing", "details": [r["path"] for r in missing_reports[:16]]})
    if doc_code.get("missing_path_reference_count", 0):
        findings.append({"severity": "medium", "area": "doc_code", "title": "Markdown references missing repository paths", "details": [f"{item['doc']} -> {item['reference']}" for item in doc_code["missing_path_references"][:30]]})
    if doc_doc.get("canonical_missing_count", 0):
        findings.append({"severity": "medium", "area": "doc_doc", "title": "Canonical docs are missing expected contract terms", "details": [f"{item['path']}: {item['missing_terms']}" for item in doc_doc["canonical_docs"] if item.get("missing_terms") or not item.get("exists")]})
    if code_code.get("duplicate_symbol_count", 0):
        findings.append({"severity": "low", "area": "code_code", "title": "Duplicate code symbols may deserve consolidation review", "details": [f"{item['symbol']} -> {item['paths']}" for item in code_code["duplicate_symbols"][:30]]})
    sqlite_errors = [item for item in sqlite_memory if item.get("error")]
    if sqlite_errors:
        findings.append({"severity": "low", "area": "sqlite_memory", "title": "Some SQLite memory databases could not be read in read-only mode", "details": [f"{item['path']}: {item['error']}" for item in sqlite_errors[:12]]})
    if not findings:
        findings.append({"severity": "info", "area": "baseline", "title": "No deterministic blocking discrepancy found", "details": ["Use --use-ollama for semantic review across collected all-resource summary."]})
    return findings


def compact_records(records: list[FileRecord], *, limit: int) -> list[dict[str, Any]]:
    return [{"path": r.path, "kind": r.kind, "extension": r.extension, "lines": r.lines, "chars": r.chars, "symbols": list(r.symbols[:30]), "headings": list(r.headings[:16])} for r in records[:limit]]


def build_ollama_prompt(review: dict[str, Any], *, objective: str) -> str:
    compact = {"objective": objective, "repo_root": review["repo_root"], "resource_lanes": review["resource_lanes"], "summary": review["summary"], "reports": review["validation_reports"], "doc_code_consistency": review["doc_code_consistency"], "doc_doc_consistency": review["doc_doc_consistency"], "code_code_consistency": review["code_code_consistency"], "raw_artifacts_sample": review["raw_artifacts"][:80], "sqlite_memory": review["sqlite_memory"], "deterministic_findings": review["deterministic_findings"], "provider_function_inventory": review["provider_function_inventory"], "guardrails": review["guardrails"]}
    return "You are an IA-Carmine all-resources repository reviewer. Review doc/code, doc/doc, code/code, RAW artifacts, SQLite memory metadata, and provider tool inventories.\nReturn JSON only with keys: verdict, mismatches, patch_proposals, doc_review, code_review, stop_conditions.\nDo not propose destructive operations. Do not propose Blender runtime execution. Do not commit output or SQLite DB files.\nDo not promote NPU/OpenVINO to primary advisory. Do not apply patches. Patch proposals must be manual-review-only and small.\n\nInput JSON:\n" + json.dumps(compact, indent=2, ensure_ascii=False)


def maybe_run_ollama(repo_root: Path, prompt: str, *, model: str | None, max_new_tokens: int) -> dict[str, Any]:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from Tools.npu.ollama_runtime import OllamaSession
    try:
        with OllamaSession(model=model, shutdown_server=False, unload_model=True) as session:
            text = session.generate(prompt, max_new_tokens=max_new_tokens, temperature=0.1)
        parsed: Any = None
        try:
            from Tools.ai.model_json import parse_model_json_object
            parsed = parse_model_json_object(text)
        except Exception:
            parsed = None
        return {"used": True, "provider": "ollama", "compute_lane": "gpu_cuda", "model": model, "response_text": text, "response_json": parsed, "error": ""}
    except Exception as exc:
        return {"used": False, "provider": "ollama", "compute_lane": "gpu_cuda", "model": model, "response_text": "", "response_json": None, "error": f"{type(exc).__name__}: {exc}"}


def build_proposals(review: dict[str, Any]) -> dict[str, Any]:
    proposals: list[dict[str, Any]] = []
    for finding in review.get("deterministic_findings", []):
        if finding.get("severity") in {"high", "medium", "low"}:
            proposals.append({"id": f"MEGA-{len(proposals)+1:03d}", "title": finding.get("title"), "area": finding.get("area"), "apply_mode": "manual_review_only", "content_status": "proposal_only", "details": finding.get("details", [])})
    ollama_json = review.get("ollama_review", {}).get("response_json")
    if isinstance(ollama_json, dict):
        for item in ollama_json.get("patch_proposals", []) or []:
            if isinstance(item, dict):
                proposal = dict(item)
                proposal.setdefault("id", f"OLLAMA-MEGA-{len(proposals)+1:03d}")
                proposal.setdefault("apply_mode", "manual_review_only")
                proposal.setdefault("content_status", "proposal_only")
                proposals.append(proposal)
    return {"schema_version": 1, "kind": "megalithic_repo_review_proposals", "repo_root": review["repo_root"], "passed": True, "errors": [], "warnings": [], "provider_execution_performed": review["provider_execution_performed"], "patch_application_performed": False, "apply_mode": "manual_review_only", "proposal_count": len(proposals), "proposals": proposals}


def render_markdown(review: dict[str, Any], proposals: dict[str, Any]) -> str:
    lines = ["# Megalithic Repository Review", ""]
    lines.append(f"- Generated at: `{review['generated_at']}`")
    lines.append(f"- Provider execution performed: `{review['provider_execution_performed']}`")
    lines.append(f"- Ollama used: `{review['ollama_review']['used']}`")
    lines.append(f"- Docs scanned: `{review['summary']['doc_count']}`")
    lines.append(f"- Code files scanned: `{review['summary']['code_count']}`")
    lines.append(f"- RAW artifacts scanned: `{review['summary']['raw_artifact_count']}`")
    lines.append(f"- SQLite memory DBs scanned: `{review['summary']['sqlite_memory_count']}`")
    lines.append(f"- Proposal count: `{proposals['proposal_count']}`")
    lines.append("")
    lines.append("## Resource lanes")
    lines.append("")
    for lane, details in review["resource_lanes"].items():
        lines.append(f"- `{lane}`: {details}")
    lines.append("")
    lines.append("## Deterministic findings")
    lines.append("")
    for finding in review["deterministic_findings"]:
        lines.append(f"### {finding['severity']} — {finding['title']}")
        lines.append(f"- Area: `{finding['area']}`")
        for detail in finding.get("details", [])[:30]:
            lines.append(f"- {detail}")
        lines.append("")
    if review["ollama_review"].get("response_text"):
        lines.append("## Ollama semantic review")
        lines.append("")
        lines.append("```text")
        lines.append(review["ollama_review"]["response_text"][:16000])
        lines.append("```")
        lines.append("")
    lines.append("## Proposals")
    lines.append("")
    for proposal in proposals["proposals"]:
        lines.append(f"- `{proposal.get('id')}` {proposal.get('title')} ({proposal.get('apply_mode')})")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in review["guardrails"].items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def run_review(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_root = Path(args.repo_root).resolve()
    report_files = list(DEFAULT_REPORTS) + split_path_values(args.report_file or [])
    docs, code, raw_files, sqlite_files = iter_files(repo_root, include_all_docs=args.include_all_docs, include_all_code=args.include_all_code, include_output=args.include_output, include_index=args.include_index, include_raw=args.include_raw, include_sqlite_memory=args.include_sqlite_memory, max_files=args.max_files)
    records = build_file_records(repo_root, [*docs, *code], max_chars_per_file=args.max_chars_per_file)
    reports = collect_reports(repo_root, report_files)
    raw_artifacts = collect_raw_artifacts(repo_root, raw_files, max_raw_files=args.max_raw_files) if args.include_raw else []
    sqlite_memory = inspect_sqlite_memory(repo_root, sqlite_files, max_tables=args.max_sqlite_tables) if args.include_sqlite_memory else []
    doc_code = compare_docs_to_code(repo_root, docs, records)
    doc_doc = compare_docs_to_docs(repo_root, records)
    code_code = compare_code_to_code(records)
    findings = deterministic_findings(reports, doc_code, doc_doc, code_code, sqlite_memory)
    review: dict[str, Any] = {"schema_version": 1, "kind": "megalithic_repo_review", "generated_at": now_iso(), "repo_root": str(repo_root), "passed": True, "errors": [], "warnings": [], "objective": args.objective, "provider_execution_performed": False, "patch_application_performed": False, "source_writes_performed": False, "apply_mode": "report_only_manual_review_only", "resource_lanes": {"cpu": "deterministic indexing, validation report ingestion, doc/code/doc-doc/code-code scans, RAW and SQLite read-only metadata", "gpu_cuda": "optional live Ollama semantic review when --use-ollama is passed; GPU/Ollama functions are inventoried from project code", "npu": "NPU/OpenVINO functions are inventoried from project code; live NPU execution remains separate and explicit; existing NPU reports are ingested"}, "summary": {"doc_count": len(docs), "code_count": len(code), "record_count": len(records), "raw_artifact_count": len(raw_artifacts), "sqlite_memory_count": len(sqlite_memory), "validation_report_count": len(reports)}, "validation_reports": reports, "raw_artifacts": raw_artifacts, "sqlite_memory": sqlite_memory, "doc_code_consistency": doc_code, "doc_doc_consistency": doc_doc, "code_code_consistency": code_code, "provider_function_inventory": code_code.get("provider_functions", {}), "deterministic_findings": findings, "files_sample": compact_records(records, limit=args.file_sample_limit), "ollama_review": {"used": False, "provider": "ollama", "compute_lane": "gpu_cuda", "model": args.ollama_model, "response_text": "", "response_json": None, "error": ""}, "guardrails": {"report_only": True, "provider_execution_explicit_only": True, "patch_application_performed": False, "blender_runtime_touched": False, "full_analysis_json_touched": False, "sqlite_db_touched": False, "sqlite_memory_read_only": True, "npu_promoted_to_advisory": False, "openvino_gpu_primary_lane": False}}
    if args.use_ollama:
        prompt = build_ollama_prompt(review, objective=args.objective)
        review["ollama_review"] = maybe_run_ollama(repo_root, prompt, model=args.ollama_model, max_new_tokens=args.ollama_max_new_tokens)
        review["provider_execution_performed"] = bool(review["ollama_review"].get("used"))
        if review["ollama_review"].get("error"):
            review["warnings"].append(review["ollama_review"]["error"])
    proposals = build_proposals(review)
    return review, proposals


def write_outputs(review: dict[str, Any], proposals: dict[str, Any], args: argparse.Namespace) -> None:
    output = Path(args.output)
    markdown_output = Path(args.markdown_output)
    proposal_output = Path(args.proposal_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    proposal_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    proposal_output.write_text(json.dumps(proposals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(review, proposals), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", default="Review Markdown documentation, code, RAW artifacts, SQLite memory metadata and provider tool inventories, then propose manual-review-only follow-up patches or docs updates.")
    parser.add_argument("--include-all-docs", action="store_true")
    parser.add_argument("--include-all-code", action="store_true")
    parser.add_argument("--include-output", action="store_true")
    parser.add_argument("--include-index", action="store_true")
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--include-sqlite-memory", action="store_true")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-chars-per-file", type=int, default=80_000)
    parser.add_argument("--max-raw-files", type=int, default=500)
    parser.add_argument("--max-sqlite-tables", type=int, default=30)
    parser.add_argument("--file-sample-limit", type=int, default=240)
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--use-ollama", action="store_true", help="Explicitly run live Ollama/GPU semantic review.")
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-max-new-tokens", type=int, default=1600)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--markdown-output", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--proposal-output", default=DEFAULT_PROPOSALS_JSON)
    args = parser.parse_args()
    review, proposals = run_review(args)
    write_outputs(review, proposals, args)
    print(json.dumps({"passed": review["passed"], "output": args.output, "markdown": args.markdown_output, "proposals": args.proposal_output, "provider_execution_performed": review["provider_execution_performed"], "proposal_count": proposals["proposal_count"]}, indent=2))
    return 0 if review["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
