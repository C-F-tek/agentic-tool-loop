#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "output",
    "renders",
}
EXCLUDE_PREFIXES = (
    "docs/LOCAL_VALIDATION_EVIDENCE/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
    "Tools/npu/npu_blender_manual_chunks/",
)
ACTIVE_MD_ROOTS = (
    "README.md",
    "AGENTS.md",
    "CHATGPT.md",
    "WORKFLOW.md",
    "FULL_RUN_UNICA_TUTTO_SU_TUTTO.md",
    "docs/",
    "CHATGPT/",
    "Tools/",
)
PATH_RE = re.compile(
    r"(?P<path>(?:\.\\|\./)?(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:md|py|ps1|json|csv|txt|yaml|yml))"
)
INLINE_PATH_RE = re.compile(r"`([^`]+\.(?:md|py|ps1|json|csv|txt|yaml|yml))`")
PY_COMMAND_RE = re.compile(
    r"(?:^|\s)(?:python|py|python3|&\s*\$PythonExe)\s+(?P<script>[^\s`'\"]+\.py)",
    re.IGNORECASE,
)
PS_COMMAND_RE = re.compile(
    r"(?:powershell(?:\.exe)?[^\n]*-File\s+|^\s*&\s+|^\s*)"
    r"(?P<script>(?:\.\\|\./|Tools[\\/])[^\s`'\"]+\.ps1)",
    re.IGNORECASE | re.MULTILINE,
)
LONG_FLAG_RE = re.compile(r"(?<![\w-])--[A-Za-z0-9][A-Za-z0-9_-]*")
PS_FLAG_RE = re.compile(r"(?<![\w-])-[A-Z][A-Za-z0-9_]*")
PS_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class Finding:
    severity: str
    kind: str
    path: str
    target: str
    detail: str
    classification: str


def repo_root_from(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"[FAIL] Repository root not found from {start}")


def repo_relative(path: Path, repo: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def normalize_ref(raw: str) -> str:
    value = raw.strip().strip("'\"`.,:;()[]{}<>")
    value = value.replace("\\", "/")

    # Inline code often contains a command, not only a path:
    # `python -m py_compile ./Tools/x.py` -> `Tools/x.py`.
    command_path_match = re.search(
        r"(?P<path>(?:\.\/|\.\\|\/)?(?:[A-Za-z0-9_.-]+[\\\/])+[A-Za-z0-9_.-]+\.(?:md|py|ps1|json|csv|txt|yaml|yml))",
        value,
    )
    if command_path_match:
        value = command_path_match.group("path").replace("\\", "/")

    # Treat repo-root-like absolute paths in documentation as repository-relative.
    # Examples: `/Tools/x.py` -> `Tools/x.py`, `/docs/y.md` -> `docs/y.md`.
    root_like_prefixes = (
        "/AGENTS.md",
        "/CHATGPT.md",
        "/README.md",
        "/WORKFLOW.md",
        "/FULL_RUN_UNICA_TUTTO_SU_TUTTO.md",
        "/CHATGPT/",
        "/Tools/",
        "/docs/",
        "/Scripting/",
        "/indexAI/",
        "/output/",
        "/renders/",
    )
    if any(value == prefix[1:] or value.startswith(prefix) for prefix in root_like_prefixes):
        value = value.lstrip("/")

    while value.startswith("./"):
        value = value[2:]
    while value.startswith("../"):
        value = value[3:]
    while value.startswith(".//"):
        value = value[3:]
    return value

def is_excluded_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if any(rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return True
    parts = rel.split("/")
    return any(part in EXCLUDE_DIR_NAMES for part in parts)


def is_active_md(rel: str) -> bool:
    return rel.endswith(".md") and any(rel == root or rel.startswith(root) for root in ACTIVE_MD_ROOTS)


def iter_repo_files(repo: Path, suffixes: tuple[str, ...]) -> Iterable[Path]:
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = repo_relative(path, repo)
        if is_excluded_rel(rel):
            continue
        if path.suffix.lower() in suffixes:
            yield path


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def extract_python_args(path: Path) -> list[str]:
    text = safe_read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    args: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value.startswith("-"):
                        args.add(arg.value)
    return sorted(args)


def extract_python_symbols(path: Path) -> dict[str, int]:
    text = safe_read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"functions": 0, "classes": 0}
    functions = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
    classes = sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
    return {"functions": functions, "classes": classes}


def extract_ps_params(text: str) -> list[str]:
    start = text.lower().find("param(")
    if start < 0:
        return []
    depth = 0
    end = start
    for idx, char in enumerate(text[start:], start=start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    block = text[start:end]
    return sorted({f"-{name}" for name in PS_PARAM_RE.findall(block)})


def build_script_maps(repo: Path) -> dict[str, Any]:
    python_scripts: dict[str, Any] = {}
    powershell_scripts: dict[str, Any] = {}
    for path in iter_repo_files(repo, (".py",)):
        rel = repo_relative(path, repo)
        text = safe_read(path)
        python_scripts[rel] = {
            "path": rel,
            "line_count": line_count(text),
            "args": extract_python_args(path),
            **extract_python_symbols(path),
        }
    for path in iter_repo_files(repo, (".ps1",)):
        rel = repo_relative(path, repo)
        text = safe_read(path)
        powershell_scripts[rel] = {
            "path": rel,
            "line_count": line_count(text),
            "params": extract_ps_params(text),
        }
    return {"python": python_scripts, "powershell": powershell_scripts}


def build_existing_file_index(repo: Path) -> dict[str, Any]:
    suffixes = (".md", ".py", ".ps1", ".json", ".csv", ".txt", ".yaml", ".yml")
    paths = sorted(repo_relative(path, repo) for path in iter_repo_files(repo, suffixes))
    basename_counts = Counter(Path(rel).name for rel in paths)
    return {
        "paths": set(paths),
        "basename_counts": basename_counts,
    }


def reference_exists(repo: Path, source_path: Path, ref: str, file_index: dict[str, Any]) -> bool:
    check_ref = ref.lstrip("/") if ref.startswith("/") else ref

    if (repo / check_ref).exists():
        return True
    if (source_path.parent / check_ref).exists():
        return True

    if "/" not in check_ref and "\\" not in check_ref:
        return file_index["basename_counts"].get(Path(check_ref).name, 0) == 1

    return False


def collect_md_refs(text: str) -> set[str]:
    refs = {normalize_ref(m.group("path")) for m in PATH_RE.finditer(text)}
    refs.update(normalize_ref(m.group(1)) for m in INLINE_PATH_RE.finditer(text))
    return {r for r in refs if r and not r.startswith("http")}


def collect_doc_command_refs(text: str) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
    py_refs: list[tuple[str, list[str]]] = []
    ps_refs: list[tuple[str, list[str]]] = []
    lines = text.splitlines()
    for line in lines:
        for match in PY_COMMAND_RE.finditer(line):
            script = normalize_ref(match.group("script"))
            py_refs.append((script, sorted(set(LONG_FLAG_RE.findall(line)))))
        for match in PS_COMMAND_RE.finditer(line):
            script = normalize_ref(match.group("script"))
            ps_refs.append((script, sorted(set(PS_FLAG_RE.findall(line)))))
    return py_refs, ps_refs


def classify_missing_ref(ref: str, source_doc: str = "") -> tuple[str, str]:
    source = source_doc.replace("\\", "/")
    target = ref.replace("\\", "/")
    lower_source = source.lower()
    lower_target = target.lower()

    if target.startswith("output/") or "/output/" in target:
        return "low", "evidence-only"
    if target.startswith("docs/LOCAL_VALIDATION_EVIDENCE/"):
        return "low", "evidence-only"
    if source.startswith("CHATGPT/") or "next-chat" in lower_source or "handoff" in lower_source:
        return "low", "chatgpt-advisory-or-handoff"
    if target.startswith("patches/") or "patch_bundles/" in lower_target:
        return "low", "patch-bundle-template"
    if "*" in target or "<" in target or ">" in target:
        return "low", "placeholder-template"
    if "/some_" in lower_target or target.startswith("some_") or "your_app_" in lower_target:
        return "low", "placeholder-template"
    if "check_example_contract.py" in lower_target:
        return "low", "placeholder-template"
    historical_sources = (
        "macro-local-validation-prototype",
        "open-pr-triage",
        "pr109-prelocal",
        "local_runs_testing_and_evidence",
        "full-run-tutto-su-tutto/14-markdown-line-budget-download-bundles",
    )
    if any(token in lower_source for token in historical_sources):
        return "medium", "historical-or-handoff"
    if "next-chat" in lower_target or "handoff" in lower_target:
        return "medium", "historical-or-handoff"
    if lower_target.startswith("users/") or "/users/" in lower_target:
        return "low", "local-absolute-path"
    if "/" not in target and "\\" not in target and target.endswith((".py", ".ps1")):
        return "medium", "ambiguous-basename-reference"
    if target.endswith((".py", ".ps1")):
        return "high", "active-current"
    if target.endswith(".md"):
        return "medium", "stale-or-historical"
    return "low", "unknown"

def analyze_markdown(repo: Path, scripts: dict[str, Any], max_lines: int) -> dict[str, Any]:
    findings: list[Finding] = []
    docs: dict[str, Any] = {}
    python_scripts = scripts["python"]
    powershell_scripts = scripts["powershell"]
    file_index = build_existing_file_index(repo)
    for path in iter_repo_files(repo, (".md",)):
        rel = repo_relative(path, repo)
        text = safe_read(path)
        lines = line_count(text)
        refs = sorted(collect_md_refs(text))
        py_cmds, ps_cmds = collect_doc_command_refs(text)
        docs[rel] = {
            "path": rel,
            "line_count": lines,
            "active": is_active_md(rel),
            "reference_count": len(refs),
            "python_command_count": len(py_cmds),
            "powershell_command_count": len(ps_cmds),
        }
        if is_active_md(rel) and lines > max_lines:
            findings.append(Finding(
                "high",
                "active_markdown_over_line_budget",
                rel,
                rel,
                f"{lines} lines > {max_lines}; split into stub + directory parts.",
                "active-current",
            ))
        for ref in refs:
            if is_excluded_rel(ref):
                continue
            if not reference_exists(repo, path, ref, file_index):
                severity, classification = classify_missing_ref(ref, rel)
                findings.append(Finding(
                    severity,
                    "markdown_reference_missing",
                    rel,
                    ref,
                    "Referenced path does not exist in current working tree.",
                    classification,
                ))
        for script, flags in py_cmds:
            if script not in python_scripts:
                severity, classification = classify_missing_ref(script, rel)
                findings.append(Finding(
                    severity,
                    "markdown_python_command_missing_script",
                    rel,
                    script,
                    "Documented Python command points to a missing script.",
                    classification,
                ))
                continue
            known = set(python_scripts[script].get("args") or [])
            for flag in flags:
                if known and flag not in known:
                    findings.append(Finding(
                        "medium",
                        "markdown_python_flag_not_in_argparse",
                        rel,
                        f"{script} {flag}",
                        "Documented long flag is not present in argparse.add_argument().",
                        "stale-or-future",
                    ))
        for script, flags in ps_cmds:
            if script not in powershell_scripts:
                severity, classification = classify_missing_ref(script, rel)
                findings.append(Finding(
                    severity,
                    "markdown_powershell_command_missing_script",
                    rel,
                    script,
                    "Documented PowerShell command points to a missing script.",
                    classification,
                ))
                continue
            known = set(powershell_scripts[script].get("params") or [])
            for flag in flags:
                if known and flag not in known and flag not in {"-NoProfile", "-ExecutionPolicy", "-File"}:
                    findings.append(Finding(
                        "medium",
                        "markdown_powershell_flag_not_in_param_block",
                        rel,
                        f"{script} {flag}",
                        "Documented PowerShell parameter is not visible in param() block.",
                        "stale-or-future",
                    ))
    return {"documents": docs, "findings": [asdict(f) for f in findings]}


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    findings = report["findings"]
    by_severity = Counter(f["severity"] for f in findings)
    by_kind = Counter(f["kind"] for f in findings)
    by_classification = Counter(f["classification"] for f in findings)
    return {
        "finding_count": len(findings),
        "by_severity": dict(sorted(by_severity.items())),
        "by_kind": dict(by_kind.most_common()),
        "by_classification": dict(by_classification.most_common()),
    }


def render_markdown(report: dict[str, Any], max_rows: int = 120) -> str:
    summary = report["summary"]
    lines = [
        "# MD/code coherence report",
        "",
        "## Summary",
        "",
        f"- Markdown files scanned: `{report['inventory']['markdown_file_count']}`",
        f"- Python scripts scanned: `{report['inventory']['python_script_count']}`",
        f"- PowerShell scripts scanned: `{report['inventory']['powershell_script_count']}`",
        f"- Finding count: `{summary['finding_count']}`",
        f"- By severity: `{json.dumps(summary['by_severity'], ensure_ascii=False)}`",
        f"- By kind: `{json.dumps(summary['by_kind'], ensure_ascii=False)}`",
        "",
        "## Top findings",
        "",
        "| Severity | Kind | Document | Target | Classification |",
        "|---|---|---|---|---|",
    ]
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    findings = sorted(
        report["findings"],
        key=lambda f: (severity_rank.get(f["severity"], 9), f["kind"], f["path"], f["target"]),
    )
    for item in findings[:max_rows]:
        lines.append(
            f"| {item['severity']} | {item['kind']} | `{item['path']}` | `{item['target']}` | {item['classification']} |"
        )
    if len(findings) > max_rows:
        lines.extend(["", f"_Truncated: {len(findings) - max_rows} more findings in JSON report._"])
    lines.extend([
        "",
        "## Policy",
        "",
        "Use this report to rewrite active Markdown from current code, not from historical evidence.",
        "Raw reports under `output/**` are local artifacts and must not be committed.",
    ])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a code-aware Markdown coherence report.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--max-lines", type=int, default=400)
    parser.add_argument("--output", default="output/validation/md_code_coherence_report.json")
    parser.add_argument("--markdown-output", default="output/validation/md_code_coherence_report.md")
    parser.add_argument("--max-markdown-finding-rows", type=int, default=120)
    args = parser.parse_args()

    repo = repo_root_from(Path(args.repo_root))
    scripts = build_script_maps(repo)
    md = analyze_markdown(repo, scripts, args.max_lines)
    report: dict[str, Any] = {
        "kind": "md_code_coherence_report",
        "passed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "repo_root": str(repo),
        "max_lines": args.max_lines,
        "inventory": {
            "markdown_file_count": len(md["documents"]),
            "python_script_count": len(scripts["python"]),
            "powershell_script_count": len(scripts["powershell"]),
        },
        "scripts": scripts,
        "documents": md["documents"],
        "findings": md["findings"],
    }
    report["summary"] = summarize(report)

    out = repo / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_out = repo / args.markdown_output
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(report, args.max_markdown_finding_rows), encoding="utf-8")
    print(f"[OK] Wrote {out.relative_to(repo)}")
    print(f"[OK] Wrote {md_out.relative_to(repo)}")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
