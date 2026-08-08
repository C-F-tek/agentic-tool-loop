#!/usr/bin/env python3
"""MCP server for security audit analysis.

Scans Python code for security vulnerabilities, detects secrets,
analyzes dependency risks, and checks permission patterns.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

# Add codex_bridge to sys.path for repo_mcp_common import
try:
    _codex_bridge_dir = Path(__file__).resolve().parent
except NameError:
    _codex_bridge_dir = Path("services/codex_bridge").resolve()
if str(_codex_bridge_dir) not in sys.path:
    sys.path.insert(0, str(_codex_bridge_dir))

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-security-audit-mcp"
SERVER_VERSION = "1.0.0"


class SecurityAuditScanner:
    """Scans Python code for security vulnerabilities."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Security patterns
    # ------------------------------------------------------------------

    SECURITY_PATTERNS: list[tuple[str, str, str]] = [
        (
            "sql_injection",
            r"(?i)(execute|executemany|cursor\s*\(\)\s*\.execute)\s*\(\s*(f['\"]|format\s*\(|%\s*[\w\d_]+|\+\s*[\w\d_]+)",
            "Potential SQL injection: dynamic query construction",
        ),
        (
            "os_system_call",
            r"os\.system\s*\(|subprocess\.call\s*\(\s*.*shell\s*=\s*True",
            "os.system/subprocess with shell=True detected",
        ),
        (
            "eval_usage",
            r"\beval\s*\(|exec\s*\(",
            "eval()/exec() usage detected",
        ),
        (
            "pickle_load",
            r"pickle\.loads?\s*\(|yaml\.load\s*\((?:(?!SafeLoader).)*\)",
            "Unsafe pickle/yaml loading detected",
        ),
        (
            "hardcoded_password",
            r'(?i)(password|passwd|pwd|secret|api_key|token)\s*=\s*["\']',
            "Hardcoded credential detected",
        ),
        (
            "insecure_random",
            r"(?i)(random\.random\s*\(|random\.randint\s*\(|random\.choice\s*\()",
            "Use of insecure random (should use secrets module)",
        ),
        (
            "file_read_unvalidated",
            r"(?i)(open\s*\(|pathlib\.Path\s*\(\s*).*read\s*\(",
            "File read without validation",
        ),
        (
            "http_get_no_verify",
            r"(?:requests\.get|urllib\.request\.urlopen)\s*\(\s*['\"]https://",
            "HTTP GET without certificate verification",
        ),
        (
            "dynamic_import",
            r"\b__import__\s*\(|importlib\.import_module\s*\(\s*.*\+\s*",
            "Dynamic module import with string concatenation",
        ),
        (
            "weak_hash",
            r"(?i)(md5|sha1)\s*\(\s*|hashlib\.(md5|sha1)\s*\(",
            "Weak hash algorithm (MD5/SHA1) detected",
        ),
    ]

    SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
        ("api_key", re.compile(r'(?i)(api[_-]?key|apikey)\s*=\s*["\'][^"\']{8,}["\']')),
        ("token", re.compile(r'(?i)(token|bearer)\s*=\s*["\'][^"\']{8,}["\']')),
        ("password", re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']')),
        ("private_key", re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----')),
    ]

    def _find_python_files(self, path: str | None = None) -> list[Path]:
        """Find all Python files."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        return sorted(target.rglob("*.py"), key=lambda p: p.relative_to(self.repo_root))

    def security_scan(self, path: str = ".", severity_filter: str | None = None) -> dict[str, Any]:
        """Scan code for security vulnerabilities."""
        py_files = self._find_python_files(path)
        findings: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                lines = source.split('\n')
            except Exception:
                continue

            for pattern_name, regex, description in self.SECURITY_PATTERNS:
                matches = list(re.finditer(regex, source))
                for m in matches:
                    line_num = source[:m.start()].count('\n') + 1
                    severity = "high" if pattern_name in ("hardcoded_password", "sql_injection") else "medium"
                    if severity_filter and severity != severity_filter:
                        continue
                    findings.append({
                        "file": str(pf.relative_to(self.repo_root)),
                        "line": line_num,
                        "pattern": pattern_name,
                        "severity": severity,
                        "description": description,
                        "snippet": lines[line_num - 1].strip() if line_num <= len(lines) else ""
                    })

        return {
            "ok": True,
            "path": path,
            "files_scanned": len(py_files),
            "findings_count": len(findings),
            "high_severity": len([f for f in findings if f["severity"] == "high"]),
            "medium_severity": len([f for f in findings if f["severity"] == "medium"]),
            "low_severity": len([f for f in findings if f["severity"] == "low"]),
            "findings": findings[:200]
        }

    def secret_detector(self, path: str = ".") -> dict[str, Any]:
        """Detect hardcoded secrets in code."""
        py_files = self._find_python_files(path)
        secrets_found: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
                lines = source.split('\n')
            except Exception:
                continue

            for secret_name, pattern in self.SECRET_PATTERNS:
                matches = list(pattern.finditer(source))
                for m in matches:
                    line_num = source[:m.start()].count('\n') + 1
                    secrets_found.append({
                        "file": str(pf.relative_to(self.repo_root)),
                        "line": line_num,
                        "type": secret_name,
                        "snippet": lines[line_num - 1].strip()[:100] if line_num <= len(lines) else ""
                    })

        return {
            "ok": True,
            "path": path,
            "files_scanned": len(py_files),
            "secrets_found": len(secrets_found),
            "secrets": secrets_found[:100]
        }

    def dependency_audit(self, path: str = ".") -> dict[str, Any]:
        """Audit dependencies for known risks."""
        requirements_files = []
        pyproject_files = []

        target = self.repo_root / path if path else self.repo_root
        for pf in target.rglob("requirements*.txt"):
            requirements_files.append(pf)
        for pf in target.rglob("pyproject.toml"):
            pyproject_files.append(pf)

        deps: dict[str, list[str]] = {"pypi_packages": [], "version_specs": [], "local_packages": []}
        risks: list[dict[str, Any]] = []

        for rf in requirements_files[:5]:
            try:
                content = rf.read_text(encoding='utf-8')
                for line in content.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    match = re.match(r'([a-zA-Z0-9_-]+)\s*(?:==|>=|<=|~=|!=)\s*(.+)', line)
                    if match:
                        pkg, ver = match.group(1), match.group(2)
                        deps["pypi_packages"].append(pkg)
                        deps["version_specs"].append(f"{pkg}:{ver}")
            except Exception:
                continue

        for ppf in pyproject_files[:5]:
            try:
                content = ppf.read_text(encoding='utf-8')
                deps_match = re.findall(r'([a-zA-Z0-9_-]+)\s*[:=]\s*["\'][^"\']+', content)
                for dm in deps_match:
                    if dm not in deps["pypi_packages"]:
                        deps["pypi_packages"].append(dm)
            except Exception:
                continue

        # Check for known risky patterns
        risky_patterns = ["requests", "flask", "django", "sqlalchemy", "numpy", "pandas"]
        for pkg in deps["pypi_packages"]:
            if pkg.lower() in risky_patterns:
                risks.append({
                    "package": pkg,
                    "risk": "common attack target",
                    "recommendation": f"Pin exact version for {pkg}"
                })

        return {
            "ok": True,
            "path": path,
            "requirements_files": len(requirements_files),
            "pyproject_files": len(pyproject_files),
            "total_dependencies": len(deps["pypi_packages"]),
            "dependencies": deps,
            "risks": risks,
            "risk_count": len(risks)
        }

    def permission_analysis(self, path: str = ".") -> dict[str, Any]:
        """Analyze file permissions and access patterns."""
        py_files = self._find_python_files(path)
        issues: list[dict[str, Any]] = []

        for pf in py_files:
            try:
                source = pf.read_text(encoding='utf-8')
            except Exception:
                continue

            # Check for world-writable file creation
            if re.search(r'chmod\s*\(\s*.*0o?777', source):
                issues.append({
                    "file": str(pf.relative_to(self.repo_root)),
                    "issue": "world-writable permissions (0777)",
                    "severity": "high"
                })

            # Check for os.chmod with permissive modes
            if re.search(r'os\.chmod\s*\([^)]*0o?644|0o?666', source):
                issues.append({
                    "file": str(pf.relative_to(self.repo_root)),
                    "issue": "permissive file mode",
                    "severity": "medium"
                })

            # Check for writable temp directories
            if re.search(r'tempfile\.NamedTemporaryFile\s*\([^)]*delete\s*=\s*False', source):
                issues.append({
                    "file": str(pf.relative_to(self.repo_root)),
                    "issue": "temporary file with delete=False",
                    "severity": "medium"
                })

        return {
            "ok": True,
            "path": path,
            "files_analyzed": len(py_files),
            "issues_count": len(issues),
            "issues": issues[:100]
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_scanner: SecurityAuditScanner | None = None

def _get_scanner(repo_root: str) -> SecurityAuditScanner:
    global _scanner
    if _scanner is None:
        _scanner = SecurityAuditScanner(repo_root)
    return _scanner


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_security_scan"] = ToolSpec(
        name="aicarmine_security_scan",
        description="Scan code for security vulnerabilities",
        input_schema=object_schema({
            "path": {"type": "string"},
            "severity_filter": {"type": "string", "enum": ["high", "medium", "low"]}
        }),
        handler=lambda args, root: _get_scanner(str(root)).security_scan(
            path=args.get("path", "."),
            severity_filter=args.get("severity_filter")
        ),
    )

    tools["aicarmine_secret_detector"] = ToolSpec(
        name="aicarmine_secret_detector",
        description="Detect hardcoded secrets in code",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).secret_detector(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_dependency_audit"] = ToolSpec(
        name="aicarmine_dependency_audit",
        description="Audit dependencies for known risks",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).dependency_audit(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_permission_analysis"] = ToolSpec(
        name="aicarmine_permission_analysis",
        description="Analyze file permissions and access patterns",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_scanner(str(root)).permission_analysis(
            path=args.get("path", ".")
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())