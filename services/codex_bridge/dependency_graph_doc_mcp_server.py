#!/usr/bin/env python3
"""
MCP adapter for Dependency Graph Documentation generation tools.

Generates structured documentation from dependency graph analysis,
producing markdown reports with module-level dependency maps,
import clustering analysis, and coupling metrics.
"""

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

SERVER_NAME = "aicarmine-dependency-graph-doc"
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

    def generate_dependency_map(args: dict[str, Any], root):
        """Generate dependency map documentation for a module or path."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path

        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}

        # Build dependency graph using AST-based import analysis
        import ast
        from collections import defaultdict

        dependencies = defaultdict(list)
        files_analyzed = 0

        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))

        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                tree = ast.parse(content, filename=str(pyfile))

                # Extract imports
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            dependencies[rel].append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            dependencies[rel].append(f"from {node.module}")
                        files_analyzed += 1
            except Exception as e:
                dependencies[rel] = [f"PARSE_ERROR: {str(e)}"]

        # Calculate metrics
        total_deps = sum(len(deps) for deps in dependencies.values())
        avg_deps = total_deps / max(len(dependencies), 1)

        # Identify high-coupling modules
        high_coupling = [(mod, len(deps)) for mod, deps in dependencies.items() if len(deps) > 10]
        high_coupling.sort(key=lambda x: x[1], reverse=True)

        # Identify import clusters
        clusters = defaultdict(list)
        for mod, deps in dependencies.items():
            for dep in deps:
                top_level = dep.split('.')[0] if '.' in dep else dep
                clusters[top_level].append(mod)

        return {
            "ok": True,
            "tool": "aicarmine_dependency_graph_doc_dependency_map",
            "path": target_path,
            "files_analyzed": len(candidates),
            "total_dependencies": total_deps,
            "average_dependencies_per_file": round(avg_deps, 2),
            "high_coupling_modules": high_coupling[:20],
            "import_clusters": dict(clusters),
            "dependency_sample": dict(list(dependencies.items())[:50])
        }

    def generate_module_boundary_docs(args: dict[str, Any], root):
        """Generate module boundary documentation based on import clustering."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path

        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}

        import ast
        from collections import defaultdict

        # Analyze internal vs external imports
        module_imports = defaultdict(set)
        external_imports = defaultdict(set)

        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))

        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                tree = ast.parse(content, filename=str(pyfile))

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module.split('.')[0] if node.module else ''
                        if module in [c.parent.name for c in candidates]:
                            module_imports[rel].add(module)
                        else:
                            external_imports[rel].add(module)
            except Exception as e:
                external_imports[rel].add(f"ERROR: {str(e)}")

        # Suggest module boundaries
        boundary_suggestions = []
        for mod, internal in module_imports.items():
            external = external_imports.get(mod, set())
            if len(internal) > 5 and len(external) > 3:
                boundary_suggestions.append({
                    "module": mod,
                    "internal_dependencies": list(internal)[:10],
                    "external_dependencies": list(external)[:10],
                    "suggestion": f"Consider extracting {mod} into a dedicated module"
                })

        return {
            "ok": True,
            "tool": "aicarmine_dependency_graph_doc_module_boundaries",
            "path": target_path,
            "files_analyzed": len(candidates),
            "boundary_suggestions": boundary_suggestions[:20],
            "module_import_summary": {mod: len(imps) for mod, imps in module_imports.items()}[:50],
            "external_import_summary": {mod: len(imps) for mod, imps in external_imports.items()}[:50]
        }

    def generate_dependency_visualization(args: dict[str, Any], root):
        """Generate text-based dependency visualization for a module."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path

        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}

        import ast
        from collections import defaultdict, deque

        dependencies = defaultdict(list)
        reverse_deps = defaultdict(list)

        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))

        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                tree = ast.parse(content, filename=str(pyfile))

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            dependencies[rel].append(alias.name)
                            reverse_deps[alias.name].append(rel)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            dependencies[rel].append(f"from {node.module}")
                            reverse_deps[node.module].append(rel)
            except Exception as e:
                dependencies[rel].append(f"ERROR: {str(e)}")

        # Generate text visualization
        visualization_lines = ["# Dependency Graph Visualization", ""]
        visualization_lines.append(f"## Path: {target_path}")
        visualization_lines.append(f"## Files analyzed: {len(candidates)}")
        visualization_lines.append("")

        # Top-level modules and their dependencies
        top_level = defaultdict(list)
        for mod, deps in dependencies.items():
            top_level[mod.split('/')[0] if '/' in mod else mod].append(mod)

        for module, submodules in sorted(top_level.items()):
            visualization_lines.append(f"### {module}")
            for sub in submodules[:20]:
                deps_str = ', '.join(dependencies[sub][:10]) if dependencies[sub] else 'no external deps'
                visualization_lines.append(f"- `{sub}` → {deps_str}")
            visualization_lines.append("")

        return {
            "ok": True,
            "tool": "aicarmine_dependency_graph_doc_visualization",
            "path": target_path,
            "visualization": '\n'.join(visualization_lines),
            "total_edges": sum(len(deps) for deps in dependencies.values())
        }

    def dependency_documentation_quality(args: dict[str, Any], root):
        """Calculate dependency documentation quality score."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path

        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}

        import ast
        from collections import defaultdict

        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))

        total_files = 0
        documented_files = 0
        has_readme_files = 0
        high_coupling_files = 0

        dependencies = defaultdict(list)

        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Check for module docstring
                total_files += 1
                if '"""' in content[:500] or "'''" in content[:500]:
                    documented_files += 1

                # Check for __all__
                if '__all__' in content:
                    has_readme_files += 1

                # Parse imports
                tree = ast.parse(content, filename=str(pyfile))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            dependencies[rel].append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            dependencies[rel].append(f"from {node.module}")

                if len(dependencies[rel]) > 10:
                    high_coupling_files += 1
            except Exception as e:
                pass

        # Calculate score
        doc_score = documented_files / max(total_files, 1) * 40
        export_score = has_readme_files / max(total_files, 1) * 30
        coupling_penalty = min(high_coupling_files / max(total_files, 1) * 30, 30)

        overall = doc_score + export_score + (30 - coupling_penalty)

        return {
            "ok": True,
            "tool": "aicarmine_dependency_graph_doc_quality",
            "path": target_path,
            "score": round(overall, 2),
            "documentation_coverage": round(documented_files / max(total_files, 1) * 100, 2),
            "export_coverage": round(has_readme_files / max(total_files, 1) * 100, 2),
            "high_coupling_ratio": round(high_coupling_files / max(total_files, 1) * 100, 2),
            "rating": "excellent" if overall > 80 else "good" if overall > 60 else "needs_improvement"
        }

    tools: dict[str, ToolSpec] = {}

    tools["aicarmine_dependency_graph_doc_health"] = ToolSpec(
        name="aicarmine_dependency_graph_doc_health",
        description="Report dependency graph documentation server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_dependency_graph_doc_dependency_map"] = ToolSpec(
        name="aicarmine_dependency_graph_doc_dependency_map",
        description="Generate dependency map documentation for a module or path.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_dependency_map,
    )

    tools["aicarmine_dependency_graph_doc_module_boundaries"] = ToolSpec(
        name="aicarmine_dependency_graph_doc_module_boundaries",
        description="Generate module boundary documentation based on import clustering.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_module_boundary_docs,
    )

    tools["aicarmine_dependency_graph_doc_visualization"] = ToolSpec(
        name="aicarmine_dependency_graph_doc_visualization",
        description="Generate text-based dependency visualization for a module.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_dependency_visualization,
    )

    tools["aicarmine_dependency_graph_doc_quality"] = ToolSpec(
        name="aicarmine_dependency_graph_doc_quality",
        description="Calculate dependency documentation quality score.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=dependency_documentation_quality,
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
            health_tool="aicarmine_dependency_graph_doc_health",
            real_tool="aicarmine_dependency_graph_doc_dependency_map",
            real_args={"path": "services/codex_bridge/repo_mcp_common.py"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())