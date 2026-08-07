#!/usr/bin/env python3
"""MCP server for code dependency graph analysis and impact assessment."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-code-dep-graph-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Dependency Graph Engine
# ---------------------------------------------------------------------------

class CodeDepGraphManager:
    """Builds and queries code dependency graphs."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()
        self._graph: dict[str, set[str]] | None = None
        self._reverse_graph: dict[str, set[str]] | None = None

    def build_dep_graph(self, path: str = ".", language: str = "python") -> dict[str, Any]:
        """Build a dependency graph for files in the repository."""
        target = self.repo_root / path
        if not target.exists():
            return {"ok": True, "error": f"Path not found: {target}"}

        ext = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "go": ".go",
            "java": ".java",
        }.get(language, f".{language}")
        files = list(target.rglob(f"*{ext}")) if ext else []
        edges = []
        nodes = set()

        for file_path in files[:2000]:
            try:
                source = file_path.read_text(encoding="utf-8")
                imports = self._extract_imports(source)
                rel_path = str(file_path.relative_to(self.repo_root))
                nodes.add(rel_path)

                for imp in imports:
                    edges.append({"from": rel_path, "to": imp})
            except Exception:
                continue

        return {
            "ok": True,
            "path": str(target),
            "file_count": len(files),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "edges": edges[:500],
        }

    def find_import_chains(self, start_module: str, max_depth: int = 3) -> dict[str, Any]:
        """Find import chains from a starting module."""
        graph = self._get_or_build_graph()
        chains = []
        visited = set()
        queue = [(start_module, [start_module], 0)]

        while queue and len(chains) < 50:
            current, chain, depth = queue.pop(0)
            if depth > max_depth or current in visited:
                continue
            visited.add(current)

            successors = graph.get(current, set())
            if not successors:
                if len(chain) > 1:
                    chains.append(chain[:])
                continue

            for succ in sorted(successors)[:5]:
                new_chain = chain + [succ]
                if succ not in visited:
                    queue.append((succ, new_chain, depth + 1))
                else:
                    if len(new_chain) > 1:
                        chains.append(new_chain)

        return {
            "ok": True,
            "start_module": start_module,
            "max_depth": max_depth,
            "chain_count": len(chains),
            "chains": chains[:50],
        }

    def detect_circular_deps(self, path: str = ".") -> dict[str, Any]:
        """Detect circular dependencies in the codebase."""
        graph = self._get_or_build_graph()
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path_list: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path_list.append(node)

            for neighbor in sorted(graph.get(node, set())):
                if neighbor in rec_stack:
                    cycle_start = path_list.index(neighbor)
                    cycle = path_list[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                elif neighbor not in visited:
                    dfs(neighbor, path_list)

            path_list.pop()
            rec_stack.discard(node)

        all_nodes = set(graph.keys())
        for targets in graph.values():
            all_nodes.update(targets)

        for node in sorted(all_nodes)[:100]:
            if node not in visited:
                dfs(node, [])

        return {
            "ok": True,
            "cycle_count": len(cycles),
            "cycles": cycles[:20],
            "recommendation": "Break cycles by introducing interfaces or dependency injection" if cycles else "No circular dependencies found",
        }

    def find_callers(self, target_module: str) -> dict[str, Any]:
        """Find all modules that import the target module."""
        reverse_graph = self._get_or_build_reverse_graph()
        callers = reverse_graph.get(target_module, set())
        return {
            "ok": True,
            "target_module": target_module,
            "caller_count": len(callers),
            "callers": sorted(callers)[:100],
        }

    def find_dependents(self, module: str) -> dict[str, Any]:
        """Find all modules that the target module depends on."""
        graph = self._get_or_build_graph()
        dependents = graph.get(module, set())
        return {
            "ok": True,
            "module": module,
            "dependency_count": len(dependents),
            "dependencies": sorted(dependents)[:100],
        }

    def estimate_breakage_risk(self, file_path: str) -> dict[str, Any]:
        """Estimate the breakage risk if a file is modified."""
        graph = self._get_or_build_graph()
        reverse_graph = self._get_or_build_reverse_graph()

        # Find all transitive callers
        callers = set()
        queue = deque([file_path])
        visited = {file_path}

        while queue:
            current = queue.popleft()
            for caller in reverse_graph.get(current, set()):
                if caller not in visited:
                    visited.add(caller)
                    callers.add(caller)
                    queue.append(caller)

        # Find direct dependencies
        deps = graph.get(file_path, set())

        # Calculate risk score (0-10)
        total_callers = len(callers)
        if total_callers > 20:
            risk_score = 9
        elif total_callers > 10:
            risk_score = 7
        elif total_callers > 5:
            risk_score = 5
        elif total_callers > 2:
            risk_score = 3
        else:
            risk_score = 1

        return {
            "ok": True,
            "file": file_path,
            "direct_callers": sorted(reverse_graph.get(file_path, set()))[:20],
            "transitive_callers_count": total_callers,
            "direct_dependencies_count": len(deps),
            "risk_score": risk_score,
            "risk_level": "critical" if risk_score >= 8 else "high" if risk_score >= 6 else "medium" if risk_score >= 4 else "low",
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _extract_imports(self, source: str) -> list[str]:
        """Extract full dotted import paths from source code."""
        try:
            tree = ast.parse(source)
            imports = []
            seen: set[str] = set()
            for node in tree.body:
                # Track `import X` (absolute imports)
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name
                        if name not in seen:
                            seen.add(name)
                            imports.append(name)
                # Track `from X import Y` (relative and absolute)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    # Absolute imports (level == 0)
                    if node.level == 0 and module:
                        if module not in seen:
                            seen.add(module)
                            imports.append(module)
                    # Relative imports (level > 0) — keep full dotted path
                    elif node.level > 0 and module:
                        if module not in seen:
                            seen.add(module)
                            imports.append(module)
            return imports
        except Exception:
            return []

    def _import_to_file_path(self, import_path: str) -> str | None:
        """Convert a dotted import path to a relative file path.

        e.g., "services.aicarmine_broker.application.planner.evidence_contract_manager"
        → "services/aicarmine_broker/application/planner/evidence_contract_manager.py"
        """
        # Try as .py file directly
        rel = import_path.replace(".", "/") + ".py"
        if rel in self._file_index:
            return rel

        # Try as __init__.py (package)
        rel_init = import_path.replace(".", "/") + "/__init__.py"
        if rel_init in self._file_index:
            return rel_init

        return None

    def _build_file_index(self) -> set[str]:
        """Build a set of all candidate file paths for quick lookup."""
        candidate_paths = self._git_candidate_paths()
        result: set[str] = set()
        for rel in candidate_paths:
            if rel.endswith(".py"):
                result.add(rel)
        return result

    def _git_candidate_paths(self) -> list[str]:
        """Get candidate files using git ls-files (same technique as RAG index)."""
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        paths: list[str] = []
        seen: set[str] = set()
        for item in result.stdout.split("\0"):
            rel = item.replace("\\", "/").strip("/")
            if not rel or rel in seen:
                continue
            seen.add(rel)
            paths.append(rel)
        return paths

    def _get_or_build_graph(self) -> dict[str, set[str]]:
        """Build graph (thread-safe). Uses git ls-files candidate selection."""
        if self._graph is not None:
            return self._graph

        with self._lock:
            if self._graph is None:
                self._graph = self._build_dependency_graph()
        return self._graph

    def _get_or_build_reverse_graph(self) -> dict[str, set[str]]:
        """Build reverse graph (thread-safe) with timeout protection."""
        if self._reverse_graph is not None:
            return self._reverse_graph

        with self._lock:
            if self._reverse_graph is None:
                self._reverse_graph = self._build_reverse_graph()
        return self._reverse_graph

    def _build_dependency_graph(self) -> dict[str, set[str]]:
        """Build dependency graph using git ls-files candidate selection.

        Uses the same strategy as RAG index and Symbol Index:
        - git ls-files --cached --others --exclude-standard to select files
        - Respects .gitignore for inclusion/exclusion
        - Only indexes .py files from the candidate surface
        - Maps dotted imports to relative file paths for proper caller resolution
        """
        graph: dict[str, set[str]] = {}
        self._file_index = self._build_file_index()
        start_time = time.time()

        for i, rel in enumerate(self._file_index):
            # Timeout check every 100 files (60 second limit)
            if i % 100 == 0 and (time.time() - start_time) > 60:
                return graph  # Partial result

            file_path = self.repo_root / rel
            try:
                source = file_path.read_text(encoding="utf-8")
                imports = self._extract_imports(source)

                # Convert dotted imports to relative file paths
                resolved_deps: set[str] = set()
                for imp in imports:
                    fp = self._import_to_file_path(imp)
                    if fp:
                        resolved_deps.add(fp)
                    else:
                        resolved_deps.add(imp)

                graph[rel] = resolved_deps | set(graph.get(rel, set()))
            except Exception:
                continue

        return graph

    def _build_reverse_graph(self) -> dict[str, set[str]]:
        """Build reverse graph from forward graph with timeout."""
        start_time = time.time()
        forward = self._get_or_build_graph()
        reverse: dict[str, set[str]] = defaultdict(set)

        for i, (source, targets) in enumerate(forward.items()):
            # Timeout check every 100 entries (30 second limit for reverse build)
            if i % 100 == 0 and (time.time() - start_time) > 30:
                return dict(reverse)

            for target in targets:
                reverse[target].add(source)

        return dict(reverse)


# Module-level singleton
_dep_manager: CodeDepGraphManager | None = None
_lock = threading.Lock()


def _get_dep_manager(repo_root: str) -> CodeDepGraphManager:
    global _dep_manager
    if _dep_manager is None:
        with _lock:
            if _dep_manager is None:
                _dep_manager = CodeDepGraphManager(repo_root)
    return _dep_manager


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["dep_graph"] = {
            "enabled": True,
            "manager": "CodeDepGraphManager",
        }
        return payload

    tools["aicarmine_code_dep_health"] = ToolSpec(
        name="aicarmine_code_dep_health",
        description="Report code dependency graph MCP health.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_code_build_dep_graph"] = ToolSpec(
        name="aicarmine_code_build_dep_graph",
        description="Build a dependency graph for files in the repository.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
            "language": {"type": "string", "default": "python"},
        }),
        handler=lambda args, root: _get_dep_manager(str(root)).build_dep_graph(
            args.get("path", "."), args.get("language", "python")
        ),
    )

    tools["aicarmine_code_find_import_chains"] = ToolSpec(
        name="aicarmine_code_find_import_chains",
        description="Find import chains from a starting module.",
        input_schema=object_schema({
            "start_module": {"type": "string"},
            "max_depth": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
        }, required=["start_module"]),
        handler=lambda args, root: _get_dep_manager(str(root)).find_import_chains(
            args["start_module"], args.get("max_depth", 3)
        ),
    )

    tools["aicarmine_code_detect_circular_deps"] = ToolSpec(
        name="aicarmine_code_detect_circular_deps",
        description="Detect circular dependencies in the codebase.",
        input_schema=object_schema({
            "path": {"type": "string", "default": "."},
        }),
        handler=lambda args, root: _get_dep_manager(str(root)).detect_circular_deps(
            args.get("path", ".")
        ),
    )

    tools["aicarmine_code_find_callers"] = ToolSpec(
        name="aicarmine_code_find_callers",
        description="Find all modules that import the target module.",
        input_schema=object_schema({
            "target_module": {"type": "string"},
        }, required=["target_module"]),
        handler=lambda args, root: _get_dep_manager(str(root)).find_callers(args["target_module"]),
    )

    tools["aicarmine_code_find_dependents"] = ToolSpec(
        name="aicarmine_code_find_dependents",
        description="Find all modules that the target module depends on.",
        input_schema=object_schema({
            "module": {"type": "string"},
        }, required=["module"]),
        handler=lambda args, root: _get_dep_manager(str(root)).find_dependents(args["module"]),
    )

    tools["aicarmine_code_estimate_breakage_risk"] = ToolSpec(
        name="aicarmine_code_estimate_breakage_risk",
        description="Estimate the breakage risk if a file is modified.",
        input_schema=object_schema({
            "file_path": {"type": "string"},
        }, required=["file_path"]),
        handler=lambda args, root: _get_dep_manager(str(root)).estimate_breakage_risk(args["file_path"]),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
