#!/usr/bin/env python3
"""MCP adapter for code lifecycle management tools.

Provides read-only analysis of deprecation traces, dependency compatibility,
technical-debt ledger, and migration planning across the repository.

Tools:
- aicarmine_lifecycle_deprecation_scan
- aicarmine_lifecycle_dependency_matrix
- aicarmine_lifecycle_tech_debt_ledger
- aicarmine_lifecycle_migration_plan
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-lifecycle"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


# ─────────────── helpers ───────────────

def _list_py_files(root: Path) -> list[Path]:
    """Return all .py files under root (bounded to avoid excessive scans)."""
    found: list[Path] = []
    for p in root.rglob("*.py"):
        if p.is_file():
            found.append(p)
    # Cap at 2000 files to keep bounded
    return found[:2000]


def _read_file_safe(path: Path) -> str | None:
    """Read a file with errors='replace', return None on failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string like '3.10.2' into (3, 10, 2)."""
    parts = v.strip().split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result)


def _version_str(t: tuple[int, ...]) -> str:
    return ".".join(str(x) for x in t)


# ─────────────── tool: deprecation_scan ───────────────

def _scan_deprecations(root: Path) -> dict[str, Any]:
    """Scan all Python files for deprecated API usage patterns."""
    # Patterns mapping: regex -> (api_name, introduced_in, removed_in, severity)
    deprecation_patterns: list[tuple[str, str, str, str]] = [
        # Python stdlib deprecations
        (r'\bssl\.wrap_socket\b', 'ssl.wrap_socket', '3.7', 'removed', 'critical'),
        (r'\bthreading\.Thread\.setDaemon\b', 'Thread.setDaemon', '3.9', 'deprecated', 'warning'),
        (r'\bconfigparser\.SafeConfigParser\b', 'configparser.SafeConfigParser', '0.x', 'deprecated', 'warning'),
        (r'\bxml\.rpc\.xmlrpc_server\.XmlRPCServer\b', 'XmlRPCServer', '3.5', 'deprecated', 'info'),
        (r'\bdistutils\.version\.LocalVersion\b', 'distutils.version.LocalVersion', '3.12', 'removed', 'critical'),
        (r'\bdistutils\.core\b', 'distutils.core', '3.12', 'removed', 'critical'),
        (r'\b__future__\.import_annotations\b', '__future__.annotations import timing', '3.11', 'deprecated', 'info'),
        # Common third-party deprecations
        (r'\bpandas\.lib\.unwrap_inferer\b', 'pandas.lib.unwrap_inferer', '0.x', 'removed', 'critical'),
        (r'\bnumpy\.float\b', 'numpy.float (alias for numpy.float64)', '2.0', 'deprecated', 'warning'),
        (r'\bnumpy\.int\b', 'numpy.int (alias for numpy.int64)', '2.0', 'deprecated', 'warning'),
        (r'\bnumpy\.bool\b', 'numpy.bool (alias for numpy.bool_)', '2.0', 'deprecated', 'warning'),
        (r'\bnumpy\.complex\b', 'numpy.complex (alias for numpy.complex128)', '2.0', 'deprecated', 'warning'),
        (r'\bnumpy\.object\b', 'numpy.object (alias for numpy.object_)', '2.0', 'deprecated', 'warning'),
        (r'\bnumpy\.str\b', 'numpy.str (alias for numpy.str_)', '2.0', 'deprecated', 'warning'),
        # asyncio deprecations
        (r'\basyncio\.get_event_loop\.get_child_scheduler\b', 'asyncio.get_event_loop().get_child_scheduler', '3.12', 'removed', 'critical'),
        (r'\basyncio\.BaseEventLoop\.set_child_scheduler\b', 'asyncio.BaseEventLoop.set_child_scheduler', '3.12', 'removed', 'critical'),
    ]

    findings: list[dict[str, Any]] = []
    files_scanned = 0

    for pyfile in _list_py_files(root):
        content = _read_file_safe(pyfile)
        if content is None:
            continue
        files_scanned += 1

        rel_path = str(pyfile.relative_to(root))
        lines = content.split("\n")

        for pattern, api_name, introduced, removed, severity in deprecation_patterns:
            matches = list(re.finditer(pattern, content))
            if matches:
                for m in matches:
                    line_num = content[:m.start()].count("\n") + 1
                    findings.append({
                        "file": rel_path,
                        "line": line_num,
                        "api": api_name,
                        "introduced_in": introduced,
                        "removed_in": removed,
                        "severity": severity,
                        "match_text": m.group(0)[:80],
                    })

    # Summary by severity
    critical_count = sum(1 for f in findings if f["severity"] == "critical")
    warning_count = sum(1 for f in findings if f["severity"] == "warning")
    info_count = sum(1 for f in findings if f["severity"] == "info")

    return {
        "ok": True,
        "files_scanned": files_scanned,
        "total_findings": len(findings),
        "critical": critical_count,
        "warnings": warning_count,
        "info": info_count,
        "findings": findings,
        "summary": {
            "breaking_changes": critical_count,
            "deprecation_warnings": warning_count,
            "informational": info_count,
        },
    }


def _deprecation_scan(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Scan codebase for deprecated API calls."""
    return _scan_deprecations(root)


# ─────────────── tool: dependency_matrix ───────────────

def _analyze_dependencies(root: Path) -> dict[str, Any]:
    """Analyze pyproject.toml / requirements.txt and generate compatibility matrix."""
    results: dict[str, Any] = {}
    deps: list[dict[str, Any]] = []
    files_checked: list[str] = []

    # Check pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        files_checked.append("pyproject.toml")
        content = _read_file_safe(pyproject)
        if content:
            # Extract dependencies from [project.dependencies]
            dep_section = re.search(r'\[project\.dependencies\](.*?)(?=\n\[|\Z)', content, re.DOTALL)
            if dep_section:
                section_text = dep_section.group(1)
                for line in section_text.split("\n"):
                    line = line.strip().strip(',')
                    if not line or line.startswith('#'):
                        continue
                    match = re.match(r'["\']([^\"]+)["\']', line)
                    if match:
                        dep_str = match.group(1)
                        dep_parts = re.split(r'[<>=!~]', dep_str)
                        if len(dep_parts) >= 1:
                            name = dep_parts[0].strip()
                            version_constraint = dep_str[len(name):].strip() if len(dep_str) > len(name) else ""
                            deps.append({
                                "package": name,
                                "constraint": version_constraint,
                                "source": "pyproject.toml",
                            })

    # Check requirements.txt
    req_file = root / "requirements.txt"
    if req_file.exists():
        files_checked.append("requirements.txt")
        content = _read_file_safe(req_file)
        if content:
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                match = re.match(r'["\']([^\"]+)["\']', line)
                if match:
                    dep_str = match.group(1)
                    dep_parts = re.split(r'[<>=!~]', dep_str)
                    if len(dep_parts) >= 1:
                        name = dep_parts[0].strip()
                        version_constraint = dep_str[len(name):].strip() if len(dep_str) > len(name) else ""
                        deps.append({
                            "package": name,
                            "constraint": version_constraint,
                            "source": "requirements.txt",
                        })

    # Build compatibility matrix
    matrix: dict[str, Any] = {}
    for dep in deps:
        name = dep["package"]
        constraint = dep.get("constraint", "")
        parsed_version = None
        if constraint:
            ver_match = re.search(r'[><=!~]=?\s*([\d.]+)', constraint)
            if ver_match:
                parsed_version = _parse_version(ver_match.group(1))

        matrix[name] = {
            "constraint": constraint,
            "parsed_version": _version_str(parsed_version) if parsed_version else None,
            "operator": re.search(r'([<>=!~]+)', constraint).group(1) if constraint and re.search(r'[<>=!~]', constraint) else None,
            "compatible_versions": f"See constraint: {constraint}" if constraint else "Any version",
            "status": "pinned" if constraint and "=" in str(constraint) else "flexible",
        }

    # Check for potential conflicts
    conflicts: list[dict[str, Any]] = []
    pkg_names = [d["package"] for d in deps]
    for i, d1 in enumerate(deps):
        for j, d2 in enumerate(deps):
            if i >= j:
                continue
            # Simple conflict check: same package with different constraints
            if d1["package"] == d2["package"]:
                if d1.get("constraint") != d2.get("constraint"):
                    conflicts.append({
                        "packages": [d1["package"], d2["package"]],
                        "conflicting_constraints": [d1.get("constraint"), d2.get("constraint")],
                        "sources": [d1.get("source"), d2.get("source")],
                    })

    return {
        "ok": True,
        "files_checked": files_checked,
        "dependencies_count": len(deps),
        "dependencies": deps,
        "compatibility_matrix": matrix,
        "potential_conflicts": conflicts,
        "conflict_count": len(conflicts),
    }


def _dependency_matrix(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Analyze dependencies and generate compatibility matrix."""
    return _analyze_dependencies(root)


# ─────────────── tool: tech_debt_ledger ───────────────

def _scan_tech_debt(root: Path) -> dict[str, Any]:
    """Scan for @TODO, @FIXME, @HACK, @XXX comments and generate structured ledger."""
    patterns = [
        (r'@\s*TODO\b', 'TODO', 'low'),
        (r'@\s*FIXME\b', 'FIXME', 'high'),
        (r'@\s*HACK\b', 'HACK', 'medium'),
        (r'@\s*XXX\b', 'XXX', 'high'),
        (r'#\s*TODO\b', 'TODO', 'low'),
        (r'#\s*FIXME\b', 'FIXME', 'high'),
        (r'#\s*HACK\b', 'HACK', 'medium'),
        (r'#\s*XXX\b', 'XXX', 'high'),
    ]

    findings: list[dict[str, Any]] = []
    files_scanned = 0

    for pyfile in _list_py_files(root):
        content = _read_file_safe(pyfile)
        if content is None:
            continue
        files_scanned += 1

        rel_path = str(pyfile.relative_to(root))
        lines = content.split("\n")

        for pattern, tag, priority in patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    # Extract the comment content
                    comment_match = re.search(r'(?:#|//)\s*' + pattern.replace('@ ', '').replace('\b', ''), line)
                    comment_text = line.strip().lstrip('#').lstrip('//').strip()[:120] if comment_match else line.strip()[:120]

                    findings.append({
                        "file": rel_path,
                        "line": i,
                        "tag": tag,
                        "priority": priority,
                        "comment": comment_text,
                    })

    # Priority distribution
    high_count = sum(1 for f in findings if f["priority"] == "high")
    medium_count = sum(1 for f in findings if f["priority"] == "medium")
    low_count = sum(1 for f in findings if f["priority"] == "low")

    return {
        "ok": True,
        "files_scanned": files_scanned,
        "total_entries": len(findings),
        "high_priority": high_count,
        "medium_priority": medium_count,
        "low_priority": low_count,
        "entries": findings,
        "priority_distribution": {
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
        },
    }


def _tech_debt_ledger(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Read @TODO/@FIXME/HACK/XXX comments and generate structured ledger."""
    return _scan_tech_debt(root)


# ─────────────── tool: migration_plan ───────────────

def _generate_migration_plan(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Generate step-by-step migration plan between versions."""
    package_name = args.get("package", "")
    from_version = args.get("from_version", "")
    to_version = args.get("to_version", "")

    if not package_name:
        return {"ok": False, "error": "package_name_required", "message": "Provide 'package' parameter."}

    if not from_version or not to_version:
        return {"ok": False, "error": "version_required", "message": "Provide both 'from_version' and 'to_version'."}

    # Known migration guides for common packages
    migration_guides: dict[str, list[dict[str, Any]]] = {
        "pandas": [
            {"step": 1, "action": "Update pandas version in pyproject.toml or requirements.txt", "command": f"pip install pandas=={to_version}", "risk": "low"},
            {"step": 2, "action": "Check for deprecated API usage (e.g., df.ix, df.convert)", "command": "grep -r 'df\\.ix\\|df\\.convert' --include='*.py'", "risk": "medium"},
            {"step": 3, "action": "Run test suite to verify compatibility", "command": "pytest tests/ -x", "risk": "medium"},
            {"step": 4, "action": "Review release notes for breaking changes", "command": "None (manual review required)", "risk": "high"},
        ],
        "numpy": [
            {"step": 1, "action": "Update numpy version", "command": f"pip install numpy=={to_version}", "risk": "low"},
            {"step": 2, "action": "Replace deprecated aliases (np.float -> np.float64, etc.)", "command": "grep -r 'np\\.float\\|np\\.int\\|np\\.bool' --include='*.py'", "risk": "medium"},
            {"step": 3, "action": "Run test suite", "command": "pytest tests/ -x", "risk": "medium"},
        ],
        "python": [
            {"step": 1, "action": "Check Python version compatibility", "command": f"python --version (target: {to_version})", "risk": "high"},
            {"step": 2, "action": "Remove deprecated stdlib APIs", "command": "grep -r 'ssl\\.wrap_socket\\|distutils\\.core' --include='*.py'", "risk": "high"},
            {"step": 3, "action": "Update type hint syntax for new Python version", "command": None, "risk": "medium"},
            {"step": 4, "action": "Run test suite", "command": "pytest tests/ -x", "risk": "medium"},
        ],
    }

    guide = migration_guides.get(package_name.lower())
    if not guide:
        # Generate generic plan
        guide = [
            {"step": 1, "action": f"Backup current state of {package_name}", "command": "git stash || git backup", "risk": "low"},
            {"step": 2, "action": f"Update {package_name} to version {to_version}", "command": f"pip install {package_name}=={to_version}", "risk": "medium"},
            {"step": 3, "action": "Review release notes for breaking changes", "command": f"curl https://pypi.org/project/{package_name}/{to_version}/", "risk": "high"},
            {"step": 4, "action": "Run test suite", "command": "pytest tests/ -x", "risk": "medium"},
            {"step": 5, "action": "Deploy and verify", "command": None, "risk": "high"},
        ]

    return {
        "ok": True,
        "package": package_name,
        "from_version": from_version,
        "to_version": to_version,
        "plan_steps": guide,
        "total_steps": len(guide),
        "estimated_risk": "high" if any(s["risk"] == "high" for s in guide) else "medium" if any(s["risk"] == "medium" for s in guide) else "low",
    }


# ─────────────── tool registry ───────────────

def _tools() -> dict[str, ToolSpec]:
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools: dict[str, ToolSpec] = {}

    tools["aicarmine_lifecycle_deprecation_scan"] = ToolSpec(
        name="aicarmine_lifecycle_deprecation_scan",
        description="Scan codebase for deprecated API calls, reporting introduction version, removal version, and severity.",
        input_schema=object_schema(),
        handler=_deprecation_scan,
    )

    tools["aicarmine_lifecycle_dependency_matrix"] = ToolSpec(
        name="aicarmine_lifecycle_dependency_matrix",
        description="Analyze pyproject.toml/requirements.txt and generate dependency compatibility matrix.",
        input_schema=object_schema(),
        handler=_dependency_matrix,
    )

    tools["aicarmine_lifecycle_tech_debt_ledger"] = ToolSpec(
        name="aicarmine_lifecycle_tech_debt_ledger",
        description="Read @TODO/@FIXME/HACK/XXX comments and generate structured technical debt ledger with priority levels.",
        input_schema=object_schema(),
        handler=_tech_debt_ledger,
    )

    tools["aicarmine_lifecycle_migration_plan"] = ToolSpec(
        name="aicarmine_lifecycle_migration_plan",
        description="Generate step-by-step migration plan between versions for a package.",
        input_schema=object_schema({
            "package": string_prop(),
            "from_version": string_prop(),
            "to_version": string_prop(),
        }, required=["package", "from_version", "to_version"]),
        handler=_generate_migration_plan,
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_lifecycle_deprecation_scan",
            real_tool="aicarmine_lifecycle_dependency_matrix",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())