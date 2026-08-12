#!/usr/bin/env python3
"""MCP adapter for test coverage analysis tools."""

from __future__ import annotations

import json
import sys
from typing import Any
from pathlib import Path

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-test-coverage"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _tools() -> dict[str, ToolSpec]:
    from repo_mcp_common import selected_repo_root
    
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))
    
    def file_coverage(args: dict[str, Any], root):
        """Analyze test coverage for a specific file."""
        target_file = args.get("path", "")
        full_path = Path(root) / target_file
        
        if not full_path.exists():
            return {"ok": False, "error": f"path_not_found: {target_file}"}
        
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # Analyze code structure
            import re
            lines = content.split("\n")
            total_lines = len(lines)
            
            # Count executable lines (non-empty, non-comment, non-string)
            executable_lines = 0
            in_docstring = False
            
            for line in lines:
                stripped = line.strip()
                
                # Track docstrings
                if '"""' in stripped or "'''" in stripped:
                    count = stripped.count('"""') + stripped.count("'''")
                    if in_docstring:
                        in_docstring = False
                        continue
                    if count >= 2:
                        continue
                    in_docstring = True
                    continue
                
                if in_docstring:
                    continue
                
                # Skip empty lines, comments, decorators, imports, blanks
                if not stripped or stripped.startswith("#") or stripped.startswith("@"):
                    continue
                if stripped.startswith("import ") or stripped.startswith("from "):
                    continue
                
                executable_lines += 1
            
            # Detect test coverage markers
            has_tests = False
            test_references = []
            
            # Check for pytest/unittest patterns
            if re.search(r'def\s+test_', content):
                has_tests = True
            
            # Count assertions
            assertions = len(re.findall(r'\bassert\b', content))
            
            # Detect decorators
            decorators = len(re.findall(r'@\w+', content))
            
            return {
                "ok": True,
                "tool": "aicarmine_test_coverage_file",
                "file": target_file,
                "total_lines": total_lines,
                "executable_lines": executable_lines,
                "has_tests": has_tests,
                "assertions": assertions,
                "decorators": decorators,
                "coverage_estimate": round(assertions / max(executable_lines, 1) * 100, 2)
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def module_coverage(args: dict[str, Any], root):
        """Analyze test coverage for a module/directory."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        files_analysis = []
        total_executable = 0
        total_assertions = 0
        total_functions = 0
        tested_functions = 0
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Count executable lines
                lines = content.split("\n")
                exec_lines = 0
                in_docstring = False
                
                for line in lines:
                    stripped = line.strip()
                    if '"""' in stripped or "'''" in stripped:
                        count = stripped.count('"""') + stripped.count("'''")
                        if in_docstring:
                            in_docstring = False
                            continue
                        if count >= 2:
                            continue
                        in_docstring = True
                        continue
                    if in_docstring:
                        continue
                    if not stripped or stripped.startswith("#") or stripped.startswith("@"):
                        continue
                    if stripped.startswith("import ") or stripped.startswith("from "):
                        continue
                    exec_lines += 1
                
                # Count functions and tests
                functions = re.findall(r'def\s+(\w+)', content)
                test_funcs = [f for f in functions if f.startswith("test_")]
                
                assertions = len(re.findall(r'\bassert\b', content))
                
                # Estimate coverage per function
                func_coverage = {}
                for func in functions:
                    # Simple heuristic: check if test exists for this function
                    func_test = f"def test_{func}"
                    if func_test in content or f"test_{func}" in content:
                        tested_functions += 1
                    total_functions += 1
                
                files_analysis.append({
                    "file": rel,
                    "executable_lines": exec_lines,
                    "functions": len(functions),
                    "test_functions": len(test_funcs),
                    "assertions": assertions,
                    "coverage_pct": round(assertions / max(exec_lines, 1) * 100, 2)
                })
                
                total_executable += exec_lines
                total_assertions += assertions
            except Exception as e:
                files_analysis.append({"file": rel, "error": str(e)})
        
        overall_coverage = round(total_assertions / max(total_executable, 1) * 100, 2)
        function_coverage = round(tested_functions / max(total_functions, 1) * 100, 2)
        
        return {
            "ok": True,
            "path": target_path,
            "total_files": len(files_analysis),
            "overall_line_coverage": overall_coverage,
            "overall_function_coverage": function_coverage,
            "total_functions": total_functions,
            "tested_functions": tested_functions,
            "sample": files_analysis[:20]
        }
    
    def coverage_gaps(args: dict[str, Any], root):
        """Identify uncovered code regions."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        gaps = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                lines = content.split("\n")
                
                # Identify functions without tests
                functions = re.finditer(r'def\s+(\w+)\s*\([^)]*\)\s*:(.*?)(?=\ndef\s+\w+|$)', content, re.DOTALL)
                
                for func_match in functions:
                    func_name = func_match.group(1)
                    func_body = func_match.group(0)
                    
                    # Check if test exists
                    test_pattern = f"def test_{func_name}"
                    if test_pattern not in content:
                        # Find line number
                        line_num = content[:func_match.start()].count('\n') + 1
                        
                        gaps.append({
                            "file": rel,
                            "function": func_name,
                            "line": line_num,
                            "reason": "no_test_found"
                        })
                        
            except Exception as e:
                gaps.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "path": target_path,
            "total_gaps": len(gaps),
            "gaps": gaps[:50],
            "files_with_gaps": len(set(g.get("file") for g in gaps))
        }
    
    def pytest_report(args: dict[str, Any], root):
        """Generate a pytest-style coverage report."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        # Collect all Python files
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        test_files = []
        source_files = []
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            if "test_" in rel.lower() or "_test.py" in rel.lower():
                test_files.append(rel)
            else:
                source_files.append(rel)
        
        # Analyze each source file
        reports = []
        total_tests = 0
        total_sources = len(source_files)
        
        for src_file in source_files:
            full_src = Path(root) / src_file
            
            try:
                with open(full_src, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Count test references
                test_refs = len(re.findall(r'from\s+.*test_|import.*test|pytest|unittest', content))
                
                # Count assertions
                assertions = len(re.findall(r'\bassert\b', content))
                
                # Count test functions in this file
                test_funcs = len(re.findall(r'def\s+test_', content))
                
                reports.append({
                    "file": src_file,
                    "test_references": test_refs,
                    "assertions": assertions,
                    "test_functions": test_funcs,
                    "status": "tested" if test_refs > 0 or test_funcs > 0 else "untested"
                })
                
                total_tests += test_funcs
            except Exception as e:
                reports.append({"file": src_file, "error": str(e)})
        
        return {
            "ok": True,
            "path": target_path,
            "total_source_files": total_sources,
            "total_test_files": len(test_files),
            "total_test_functions": total_tests,
            "reports": reports[:50]
        }
    
    def coverage_summary(args: dict[str, Any], root):
        """Generate overall coverage summary."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        # Collect all Python files
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        total_lines = 0
        total_executable = 0
        total_assertions = 0
        total_functions = 0
        total_tests = 0
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                lines = content.split("\n")
                exec_lines = 0
                in_docstring = False
                
                for line in lines:
                    stripped = line.strip()
                    if '"""' in stripped or "'''" in stripped:
                        count = stripped.count('"""') + stripped.count("'''")
                        if in_docstring:
                            in_docstring = False
                            continue
                        if count >= 2:
                            continue
                        in_docstring = True
                        continue
                    if in_docstring:
                        continue
                    if not stripped or stripped.startswith("#") or stripped.startswith("@"):
                        continue
                    if stripped.startswith("import ") or stripped.startswith("from "):
                        continue
                    exec_lines += 1
                
                functions = len(re.findall(r'def\s+\w+', content))
                assertions = len(re.findall(r'\bassert\b', content))
                tests = len(re.findall(r'def\s+test_', content))
                
                total_lines += len(lines)
                total_executable += exec_lines
                total_assertions += assertions
                total_functions += functions
                total_tests += tests
            except Exception as e:
                pass
        
        line_coverage = round(total_assertions / max(total_executable, 1) * 100, 2)
        func_coverage = round(total_tests / max(total_functions, 1) * 100, 2)
        
        return {
            "ok": True,
            "path": target_path,
            "total_lines": total_lines,
            "executable_lines": total_executable,
            "total_functions": total_functions,
            "total_tests": total_tests,
            "total_assertions": total_assertions,
            "line_coverage_pct": line_coverage,
            "function_coverage_pct": func_coverage
        }
    
    tools: dict[str, ToolSpec] = {}
    
    tools["aicarmine_test_coverage_health"] = ToolSpec(
        name="aicarmine_test_coverage_health",
        description="Report test coverage server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["aicarmine_test_coverage_file"] = ToolSpec(
        name="aicarmine_test_coverage_file",
        description="Analyze test coverage for a specific file.",
        input_schema=object_schema({
            "path": string_prop(""),
        }),
        handler=file_coverage,
    )
    
    tools["aicarmine_test_coverage_module"] = ToolSpec(
        name="aicarmine_test_coverage_module",
        description="Analyze test coverage for a module/directory.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=module_coverage,
    )
    
    tools["aicarmine_test_coverage_gaps"] = ToolSpec(
        name="aicarmine_test_coverage_gaps",
        description="Identify uncovered code regions.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=coverage_gaps,
    )
    
    tools["aicarmine_test_coverage_pytest_report"] = ToolSpec(
        name="aicarmine_test_coverage_pytest_report",
        description="Generate a pytest-style coverage report.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=pytest_report,
    )
    
    tools["aicarmine_test_coverage_summary"] = ToolSpec(
        name="aicarmine_test_coverage_summary",
        description="Generate overall coverage summary.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=coverage_summary,
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
            health_tool="aicarmine_test_coverage_health",
            real_tool="aicarmine_test_coverage_file",
            real_args={"path": "services/codex_bridge/repo_mcp_common.py"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())