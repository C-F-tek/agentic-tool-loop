#!/usr/bin/env python3
"""MCP adapter for code architecture analysis tools."""

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

SERVER_NAME = "aicarmine-code-architect"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _count_lines(filepath: str, root) -> int:
    """Count lines in a file."""
    full_path = Path(root) / filepath
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _tools() -> dict[str, ToolSpec]:
    from repo_mcp_common import selected_repo_root
    
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))
    
    def dependency_graph(args: dict[str, Any], root):
        """Build dependency graph for a module/path."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        # Collect all Python files and their imports
        files_imports = {}
        all_files = []
        
        if full_target.is_file():
            candidates = [full_target]
        else:
            candidates = list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = pyfile.relative_to(root)
            all_files.append(str(rel))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Parse imports
                imports = []
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        if line.startswith("from "):
                            parts = line.split()
                            if len(parts) >= 2:
                                module = parts[1].split(".")[0]
                                imports.append(module)
                        elif line.startswith("import "):
                            parts = line.split(",")
                            for p in parts:
                                mod = p.strip().split()[0] if p.strip() else ""
                                if mod:
                                    imports.append(mod.split(".")[0])
                
                files_imports[str(rel)] = imports
            except Exception as e:
                files_imports[str(rel)] = [f"error: {str(e)}"]
        
        # Build adjacency list
        edges = []
        for file, imports in files_imports.items():
            for imp in imports:
                edges.append({"from": file, "to": imp})
        
        # Calculate metrics
        total_files = len(all_files)
        total_edges = len(edges)
        avg_deps = total_edges / max(total_files, 1)
        
        return {
            "ok": True,
            "path": target_path,
            "total_files": total_files,
            "total_dependencies": total_edges,
            "average_dependencies_per_file": round(avg_deps, 2),
            "edges": edges[:100],  # Limit output
            "files": all_files[:100],  # Limit output
            "graph_format": "adjacency_list"
        }
    
    def architecture_analysis(args: dict[str, Any], root):
        """Analyze architecture patterns in codebase."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        # Collect module info
        modules = []
        if full_target.is_file() and full_target.suffix == ".py":
            candidates = [full_target]
        else:
            candidates = list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = pyfile.relative_to(root)
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Detect classes and functions
                import re
                classes = re.findall(r'class\s+(\w+)', content)
                functions = re.findall(r'def\s+(\w+)', content)
                
                # Detect docstrings
                has_docstring = '"""' in content or "'''" in content
                
                # Detect type hints
                has_type_hints = ":" in content and "->" in content
                
                modules.append({
                    "file": str(rel),
                    "classes": classes[:10],
                    "functions": functions[:20],
                    "has_docstring": has_docstring,
                    "has_type_hints": has_type_hints,
                    "line_count": content.count("\n") + 1
                })
            except Exception as e:
                modules.append({"file": str(rel), "error": str(e)})
        
        # Pattern detection
        patterns_detected = []
        
        # Check for singleton pattern
        singleton_files = [m for m in modules if any("singleton" in str(m.get("classes", [])) or "Singleton" in str(m.get("classes", [])) for _ in [1])]
        if singleton_files:
            patterns_detected.append({"pattern": "singleton", "files": len(singleton_files)})
        
        # Check for factory pattern
        factory_files = [m for m in modules if any("factory" in str(m.get("functions", [])) or "Factory" in str(m.get("functions", [])) for _ in [1])]
        if factory_files:
            patterns_detected.append({"pattern": "factory", "files": len(factory_files)})
        
        # Check for observer pattern
        observer_files = [m for m in modules if any("observer" in str(m.get("classes", [])) or "Observer" in str(m.get("classes", [])) for _ in [1])]
        if observer_files:
            patterns_detected.append({"pattern": "observer", "files": len(observer_files)})
        
        return {
            "ok": True,
            "path": target_path,
            "modules_analyzed": len(modules),
            "total_classes": len([c for m in modules for c in m.get("classes", [])]),
            "total_functions": len([f for m in modules for f in m.get("functions", [])]),
            "modules_with_docstrings": len([m for m in modules if m.get("has_docstring")]),
            "modules_with_type_hints": len([m for m in modules if m.get("has_type_hints")]),
            "patterns_detected": patterns_detected,
            "sample_modules": modules[:20]
        }
    
    def coupling_metrics(args: dict[str, Any], root):
        """Calculate coupling and cohesion metrics."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        # Collect imports for all files
        file_imports = {}
        file_exports = {}
        all_files = []
        
        if full_target.is_file():
            candidates = [full_target]
        else:
            candidates = list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            all_files.append(rel)
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Parse imports (coupling in)
                imports = []
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        if line.startswith("from "):
                            parts = line.split()
                            if len(parts) >= 2:
                                module = parts[1].split(".")[0]
                                imports.append(module)
                        elif line.startswith("import "):
                            parts = line.split(",")
                            for p in parts:
                                mod = p.strip().split()[0] if p.strip() else ""
                                if mod:
                                    imports.append(mod.split(".")[0])
                
                file_imports[rel] = imports
                
                # Parse exports (from __all__ or visible definitions)
                all_match = re.findall(r'__all__\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if all_match:
                    exports = [x.strip().strip("'\"") for x in all_match[0].split(",")]
                    file_exports[rel] = exports
                else:
                    exports = re.findall(r'(?:class|def)\s+(\w+)', content)
                    file_exports[rel] = exports[:10]
            except Exception as e:
                file_imports[rel] = []
                file_exports[rel] = []
        
        import re
        
        # Calculate metrics
        total_files = len(all_files)
        total_imports = sum(len(v) for v in file_imports.values())
        total_exports = sum(len(v) for v in file_exports.values())
        
        # Average coupling (imports per file)
        avg_coupling_in = total_imports / max(total_files, 1)
        avg_coupling_out = total_exports / max(total_files, 1)
        
        # Find most coupled files
        sorted_by_imports = sorted(file_imports.items(), key=lambda x: len(x[1]), reverse=True)
        most_coupled = [(f, len(ims)) for f, ims in sorted_by_imports[:10]]
        
        # Find most cohesive modules (many exports)
        sorted_by_exports = sorted(file_exports.items(), key=lambda x: len(x[1]), reverse=True)
        most_exported = [(f, len(exp)) for f, exp in sorted_by_exports[:10]]
        
        return {
            "ok": True,
            "path": target_path,
            "total_files": total_files,
            "metrics": {
                "average_coupling_in": round(avg_coupling_in, 2),
                "average_coupling_out": round(avg_coupling_out, 2),
                "total_imports": total_imports,
                "total_exports": total_exports
            },
            "most_coupled_files": most_coupled,
            "most_exported_files": most_exported
        }
    
    def detect_patterns(args: dict[str, Any], root):
        """Detect design patterns in codebase."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        patterns_found = {
            "singleton": [],
            "factory": [],
            "observer": [],
            "strategy": [],
            "adapter": [],
            "decorator": [],
            "prototype": [],
            "command": []
        }
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Singleton: single instance pattern (get_instance method)
                if re.search(r'get_instance|_instance\s*=\s*None', content):
                    patterns_found["singleton"].append(rel)
                
                # Factory: factory method or abstract factory
                if re.search(r'create_|from_|make_|Factory|AbstractFactory', content):
                    patterns_found["factory"].append(rel)
                
                # Observer: subscribe/unsubscribe or observable
                if re.search(r'subscribe|unsubscribe|Observable|Observer', content):
                    patterns_found["observer"].append(rel)
                
                # Strategy: strategy pattern (context + strategy classes)
                if re.search(r'Strategy|Context\s*\(|execute_strategy', content):
                    patterns_found["strategy"].append(rel)
                
                # Adapter: adapts one interface to another
                if re.search(r'Adapter|adapt_|AdaptedInterface', content):
                    patterns_found["adapter"].append(rel)
                
                # Decorator: @decorator or wraps
                if re.search(r'@.*\(|wraps\s*=|decorate_', content):
                    patterns_found["decorator"].append(rel)
                
                # Command: command pattern (execute method in command class)
                if re.search(r'class\s+\w*Command|execute\s*\(', content):
                    patterns_found["command"].append(rel)
                    
            except Exception as e:
                patterns_found["unknown"].append({"file": rel, "error": str(e)})
        
        total_patterns = sum(len(v) for v in patterns_found.values())
        
        return {
            "ok": True,
            "path": target_path,
            "patterns_found": {k: len(v) for k, v in patterns_found.items()},
            "total_pattern_instances": total_patterns,
            "pattern_details": patterns_found
        }
    
    def module_boundaries(args: dict[str, Any], root):
        """Suggest module boundary separations."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        # Analyze file structure and cross-file references
        files_data = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Count internal vs external imports
                local_imports = 0
                external_imports = 0
                
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("from ") or line.startswith("import "):
                        if line.startswith("from "):
                            module = line.split()[1].split(".")[0] if len(line.split()) > 1 else ""
                            if module in [f.split("/")[0] for f in files_data]:
                                local_imports += 1
                            else:
                                external_imports += 1
                
                files_data.append({
                    "file": rel,
                    "lines": content.count("\n") + 1,
                    "classes": len(re.findall(r'class\s+\w+', content)),
                    "functions": len(re.findall(r'def\s+\w+', content)),
                    "local_imports": local_imports,
                    "external_imports": external_imports
                })
            except Exception as e:
                files_data.append({"file": rel, "error": str(e)})
        
        # Suggest boundaries based on import clustering
        suggestions = []
        # Group files by common import patterns
        module_groups = {}
        for fd in files_data:
            if fd.get("local_imports", 0) > 2:
                group = fd["file"].split("/")[0]
                if group not in module_groups:
                    module_groups[group] = []
                module_groups[group].append(fd["file"])
        
        for module, files in module_groups.items():
            if len(files) >= 3:
                suggestions.append({
                    "module": module,
                    "files": files,
                    "cohesion_score": "high" if len(files) > 5 else "medium",
                    "recommendation": f"Consider grouping these {len(files)} files into a package"
                })
        
        return {
            "ok": True,
            "path": target_path,
            "total_files_analyzed": len(files_data),
            "suggested_modules": suggestions,
            "boundary_quality": {
                "well_encapsulated": len([s for s in suggestions if s.get("cohesion_score") == "high"]),
                "needs_refactoring": len([s for s in suggestions if s.get("cohesion_score") == "medium"])
            }
        }
    
    def cyclomatic_complexity(args: dict[str, Any], root):
        """Analyze cyclomatic complexity of code."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        complexity_results = []
        total_functions = 0
        high_complexity_count = 0
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Calculate complexity for each function
                functions = re.finditer(r'def\s+(\w+)\s*\([^)]*\)\s*:(?:\s*.*?)(?=\ndef\s+\w+|$)', content, re.DOTALL)
                
                for func_match in functions:
                    func_name = func_match.group(1)
                    func_body = func_match.group(0)
                    
                    # Count decision points
                    decisions = 0
                    decisions += len(re.findall(r'\bif\b', func_body))
                    decisions += len(re.findall(r'\belif\b', func_body))
                    decisions += len(re.findall(r'\belse\b', func_body))
                    decisions += len(re.findall(r'\bfor\b', func_body))
                    decisions += len(re.findall(r'\bwhile\b', func_body))
                    decisions += len(re.findall(r'\btry\b', func_body))
                    decisions += len(re.findall(r'\bexcept\b', func_body))
                    decisions += len(re.findall(r'\band\b', func_body))
                    decisions += len(re.findall(r'\bor\b', func_body))
                    decisions += len(re.findall(r'\bmatch\b', func_body))
                    decisions += len(re.findall(r'\bcase\b', func_body))
                    
                    complexity = decisions + 1  # Base complexity is 1
                    
                    complexity_results.append({
                        "file": rel,
                        "function": func_name,
                        "complexity": complexity,
                        "rating": "low" if complexity <= 3 else "medium" if complexity <= 7 else "high" if complexity <= 10 else "very_high"
                    })
                    
                    total_functions += 1
                    if complexity > 7:
                        high_complexity_count += 1
                        
            except Exception as e:
                complexity_results.append({"file": rel, "error": str(e)})
        
        avg_complexity = sum(r["complexity"] for r in complexity_results) / max(len(complexity_results), 1)
        
        return {
            "ok": True,
            "path": target_path,
            "total_functions_analyzed": total_functions,
            "average_complexity": round(avg_complexity, 2),
            "high_complexity_functions": high_complexity_count,
            "results": complexity_results[:50],  # Limit output
            "complexity_distribution": {
                "low": len([r for r in complexity_results if r["complexity"] <= 3]),
                "medium": len([r for r in complexity_results if 3 < r["complexity"] <= 7]),
                "high": len([r for r in complexity_results if 7 < r["complexity"] <= 10]),
                "very_high": len([r for r in complexity_results if r["complexity"] > 10])
            }
        }
    
    tools: dict[str, ToolSpec] = {}
    
    tools["aicarmine_code_architect_health"] = ToolSpec(
        name="aicarmine_code_architect_health",
        description="Report code architect server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["aicarmine_code_architect_dependency_graph"] = ToolSpec(
        name="aicarmine_code_architect_dependency_graph",
        description="Build dependency graph for a module or path.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=dependency_graph,
    )
    
    tools["aicarmine_code_architect_analysis"] = ToolSpec(
        name="aicarmine_code_architect_analysis",
        description="Analyze architecture patterns in codebase.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=architecture_analysis,
    )
    
    tools["aicarmine_code_architect_metrics"] = ToolSpec(
        name="aicarmine_code_architect_metrics",
        description="Calculate coupling and cohesion metrics.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=coupling_metrics,
    )
    
    tools["aicarmine_code_architect_patterns"] = ToolSpec(
        name="aicarmine_code_architect_patterns",
        description="Detect design patterns in codebase.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=detect_patterns,
    )
    
    tools["aicarmine_code_architect_module_boundaries"] = ToolSpec(
        name="aicarmine_code_architect_module_boundaries",
        description="Suggest module boundary separations based on import clustering.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=module_boundaries,
    )
    
    tools["aicarmine_code_architect_complexity"] = ToolSpec(
        name="aicarmine_code_architect_complexity",
        description="Analyze cyclomatic complexity of functions.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=cyclomatic_complexity,
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
            health_tool="aicarmine_code_architect_health",
            real_tool="aicarmine_code_architect_dependency_graph",
            real_args={"path": "services/codex_bridge"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())