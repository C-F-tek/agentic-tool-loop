#!/usr/bin/env python3
"""MCP server for knowledge graph construction and querying.

Builds structured knowledge graphs from repository code, extracting
concepts, relationships, and concept clusters for AI-assisted navigation.
"""
from __future__ import annotations

import ast
import json
import os
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

SERVER_NAME = "aicarmine-knowledge-graph-mcp"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Knowledge Graph Builder
# ---------------------------------------------------------------------------

class KnowledgeGraphBuilder:
    """Builds structured knowledge graphs from repository code."""

    def __init__(self, repo_root: str, db_path: str | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.db_path = Path(db_path) if db_path else self.repo_root / "indexAI" / "knowledge_graph.sqlite"
        self._lock = threading.Lock()
        self._graphs: dict[str, dict[str, Any]] = {}
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database for knowledge graph storage."""
        import sqlite3
        db_dir = self.db_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_graphs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                node_count INTEGER DEFAULT 0,
                edge_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                label TEXT NOT NULL,
                file_path TEXT,
                FOREIGN KEY (graph_id) REFERENCES knowledge_graphs(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                relation TEXT NOT NULL,
                FOREIGN KEY (graph_id) REFERENCES knowledge_graphs(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS concept_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                cluster_name TEXT NOT NULL,
                modules TEXT NOT NULL,
                FOREIGN KEY (graph_id) REFERENCES knowledge_graphs(id)
            )
        """)
        conn.commit()
        conn.close()

    def build_graph(self, repo_path: str = ".", graph_id: str = "default", 
                    include_imports: bool = True, include_classes: bool = True,
                    include_functions: bool = True) -> dict[str, Any]:
        """Build knowledge graph from repository."""
        target = self.repo_root / repo_path
        if not target.exists():
            return {"ok": False, "error": f"Path not found: {target}"}

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        clusters: list[dict[str, Any]] = []

        # Collect all Python files
        py_files = list(target.rglob("*.py")) if target.is_dir() else []
        if target.suffix == ".py":
            py_files = [target]

        # Build module map
        module_map: dict[str, Path] = {}
        for pf in py_files[:200]:  # Limit to 200 files
            try:
                rel = pf.relative_to(self.repo_root)
                module_map[str(rel)] = pf
            except ValueError:
                continue

        # Extract nodes and edges
        if include_classes or include_functions:
            for mod_path, mod_file in module_map.items():
                try:
                    content = mod_file.read_text(encoding="utf-8")
                    tree = ast.parse(content)
                    module_name = mod_path.replace("/", ".").replace(".py", "")

                    # Module node
                    nodes.append({
                        "id": f"module:{module_name}",
                        "type": "module",
                        "label": module_name,
                        "file_path": str(mod_path)
                    })

                    # Class nodes
                    if include_classes:
                        for node in tree.body:
                            if isinstance(node, ast.ClassDef):
                                nodes.append({
                                    "id": f"class:{module_name}.{node.name}",
                                    "type": "class",
                                    "label": f"{module_name}.{node.name}",
                                    "file_path": str(mod_path)
                                })
                                edges.append({
                                    "from": f"module:{module_name}",
                                    "to": f"class:{module_name}.{node.name}",
                                    "relation": "contains"
                                })

                    # Function nodes
                    if include_functions:
                        for node in tree.body:
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                nodes.append({
                                    "id": f"func:{module_name}.{node.name}",
                                    "type": "function",
                                    "label": f"{module_name}.{node.name}",
                                    "file_path": str(mod_path)
                                })
                                edges.append({
                                    "from": f"module:{module_name}",
                                    "to": f"func:{module_name}.{node.name}",
                                    "relation": "contains"
                                })
                except Exception:
                    continue

        # Import edges
        if include_imports:
            for mod_path, mod_file in module_map.items():
                try:
                    content = mod_file.read_text(encoding="utf-8")
                    tree = ast.parse(content)
                    module_name = mod_path.replace("/", ".").replace(".py", "")

                    for node in tree.body:
                        if isinstance(node, ast.ImportFrom):
                            if node.module:
                                target_module = node.module.replace("/", ".").replace(".py", "")
                                edges.append({
                                    "from": f"module:{module_name}",
                                    "to": f"module:{target_module}",
                                    "relation": "imports"
                                })
                except Exception:
                    continue

        # Build concept clusters
        clusters = self._build_concept_clusters(nodes, edges)

        graph_data = {
            "nodes": nodes,
            "edges": edges,
            "concept_clusters": clusters
        }

        # Store in database
        with self._lock:
            import sqlite3
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO knowledge_graphs (id, name, node_count, edge_count)
                VALUES (?, ?, ?, ?)
            """, (graph_id, graph_id, len(nodes), len(edges)))
            cursor.execute("DELETE FROM graph_nodes WHERE graph_id = ?", (graph_id,))
            for n in nodes:
                cursor.execute("""
                    INSERT INTO graph_nodes (graph_id, node_id, node_type, label, file_path)
                    VALUES (?, ?, ?, ?, ?)
                """, (graph_id, n["id"], n["type"], n["label"], n.get("file_path", "")))
            cursor.execute("DELETE FROM graph_edges WHERE graph_id = ?", (graph_id,))
            for e in edges:
                cursor.execute("""
                    INSERT INTO graph_edges (graph_id, from_node, to_node, relation)
                    VALUES (?, ?, ?, ?)
                """, (graph_id, e["from"], e["to"], e["relation"]))
            cursor.execute("DELETE FROM concept_clusters WHERE graph_id = ?", (graph_id,))
            for c in clusters:
                cursor.execute("""
                    INSERT INTO concept_clusters (graph_id, cluster_name, modules)
                    VALUES (?, ?, ?)
                """, (graph_id, c["cluster"], json.dumps(c["modules"])))
            conn.commit()
            conn.close()

        self._graphs[graph_id] = graph_data

        return {
            "ok": True,
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "nodes": nodes[:100],  # Return top 100 nodes
            "edges": edges[:200],  # Return top 200 edges
            "clusters": clusters
        }

    def _build_concept_clusters(self, nodes: list[dict], edges: list[dict]) -> list[dict]:
        """Build concept clusters from nodes and edges."""
        clusters: list[dict] = []
        
        # Group by relation type
        relation_groups: dict[str, list[str]] = {}
        for e in edges:
            rel = e.get("relation", "unknown")
            from_mod = e.get("from", "").replace("module:", "").replace("class:", "").replace("func:", "")
            to_mod = e.get("to", "").replace("module:", "").replace("class:", "").replace("func:", "")
            relation_groups.setdefault(rel, []).append(f"{from_mod} → {to_mod}")

        for rel, items in relation_groups.items():
            if len(items) >= 3:
                clusters.append({
                    "cluster": rel,
                    "items": items[:20]
                })

        return clusters

    def query_graph(self, graph_id: str, query: str, 
                    node_type: str | None = None, max_results: int = 50) -> dict[str, Any]:
        """Query knowledge graph."""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if graph exists
        cursor.execute("SELECT id FROM knowledge_graphs WHERE id = ?", (graph_id,))
        if not cursor.fetchone():
            conn.close()
            return {"ok": False, "error": f"Graph not found: {graph_id}"}

        results: list[dict[str, Any]] = []

        # Query nodes
        if node_type:
            cursor.execute("""
                SELECT node_id, node_type, label, file_path FROM graph_nodes
                WHERE graph_id = ? AND node_type = ? AND label LIKE ?
                LIMIT ?
            """, (graph_id, node_type, f"%{query}%", max_results))
        else:
            cursor.execute("""
                SELECT node_id, node_type, label, file_path FROM graph_nodes
                WHERE graph_id = ? AND (label LIKE ? OR file_path LIKE ?)
                LIMIT ?
            """, (graph_id, f"%{query}%", f"%{query}%", max_results))

        for row in cursor.fetchall():
            results.append({
                "type": "node",
                "id": row["node_id"],
                "node_type": row["node_type"],
                "label": row["label"],
                "file_path": row["file_path"]
            })

        # Query edges
        cursor.execute("""
            SELECT from_node, to_node, relation FROM graph_edges
            WHERE graph_id = ? AND (from_node LIKE ? OR to_node LIKE ? OR relation LIKE ?)
            LIMIT ?
        """, (graph_id, f"%{query}%", f"%{query}%", f"%{query}%", max_results))

        for row in cursor.fetchall():
            results.append({
                "type": "edge",
                "from": row["from_node"],
                "to": row["to_node"],
                "relation": row["relation"]
            })

        conn.close()
        return {
            "ok": True,
            "graph_id": graph_id,
            "query": query,
            "results": results[:max_results],
            "result_count": len(results)
        }

    def concept_map(self, module: str, depth: int = 2) -> dict[str, Any]:
        """Map concepts for a module."""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT node_id, node_type, label, file_path FROM graph_nodes
            WHERE graph_id = 'default' AND label LIKE ?
        """, (f"%{module}%",))

        nodes = []
        for row in cursor.fetchall():
            nodes.append({
                "id": row["node_id"],
                "type": row["node_type"],
                "label": row["label"],
                "file_path": row["file_path"]
            })

        # Find related nodes
        related: list[dict] = []
        for n in nodes:
            cursor.execute("""
                SELECT from_node, to_node, relation FROM graph_edges
                WHERE graph_id = 'default' AND (from_node = ? OR to_node = ?)
            """, (n["id"], n["id"]))
            for row in cursor.fetchall():
                related.append({
                    "relation": row["relation"],
                    "connected_to": row["to_node"] if row["from_node"] == n["id"] else row["from_node"]
                })

        conn.close()
        return {
            "ok": True,
            "module": module,
            "nodes": nodes,
            "related": related[:50]
        }

    def relationship_finder(self, module: str, depth: int = 2) -> dict[str, Any]:
        """Find relationships between modules."""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT from_node, to_node, relation FROM graph_edges
            WHERE graph_id = 'default' AND from_node LIKE ?
        """, (f"%{module}%",))

        relationships = []
        for row in cursor.fetchall():
            relationships.append({
                "from": row["from_node"],
                "to": row["to_node"],
                "relation": row["relation"]
            })

        conn.close()
        return {
            "ok": True,
            "module": module,
            "relationships": relationships[:100],
            "relationship_count": len(relationships)
        }

    def knowledge_summary(self) -> dict[str, Any]:
        """Generate summary of knowledge graph."""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, created_at, node_count, edge_count FROM knowledge_graphs")
        graphs = []
        for row in cursor.fetchall():
            graphs.append({
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "node_count": row["node_count"],
                "edge_count": row["edge_count"]
            })

        cursor.execute("SELECT DISTINCT node_type FROM graph_nodes WHERE graph_id = 'default'")
        types = [row["node_type"] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT relation FROM graph_edges WHERE graph_id = 'default'")
        relations = [row["relation"] for row in cursor.fetchall()]

        conn.close()
        return {
            "ok": True,
            "graphs": graphs,
            "node_types": types,
            "relations": relations,
            "total_nodes": sum(g["node_count"] for g in graphs),
            "total_edges": sum(g["edge_count"] for g in graphs)
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_kg_builder: KnowledgeGraphBuilder | None = None

def _get_builder(repo_root: str) -> KnowledgeGraphBuilder:
    global _kg_builder
    if _kg_builder is None:
        _kg_builder = KnowledgeGraphBuilder(repo_root)
    return _kg_builder


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_knowledge_graph_build"] = ToolSpec(
        name="aicarmine_knowledge_graph_build",
        description="Build knowledge graph from repository",
        input_schema=object_schema({
            "graph_id": {"type": "string"},
            "repo_path": {"type": "string"},
            "include_imports": {"type": "boolean"},
            "include_classes": {"type": "boolean"},
            "include_functions": {"type": "boolean"}
        }),
        handler=lambda args, root: _get_builder(str(root)).build_graph(
            repo_path=args.get("repo_path", "."),
            graph_id=args.get("graph_id", "default"),
            include_imports=args.get("include_imports", True),
            include_classes=args.get("include_classes", True),
            include_functions=args.get("include_functions", True)
        ),
    )

    tools["aicarmine_knowledge_graph_query"] = ToolSpec(
        name="aicarmine_knowledge_graph_query",
        description="Query knowledge graph",
        input_schema=object_schema({
            "graph_id": {"type": "string"},
            "query": {"type": "string"},
            "node_type": {"type": "string"},
            "max_results": {"type": "integer"}
        }),
        handler=lambda args, root: _get_builder(str(root)).query_graph(
            graph_id=args.get("graph_id", "default"),
            query=args.get("query", ""),
            node_type=args.get("node_type"),
            max_results=args.get("max_results", 50)
        ),
    )

    tools["aicarmine_concept_map"] = ToolSpec(
        name="aicarmine_concept_map",
        description="Map concepts for a module",
        input_schema=object_schema({
            "module": {"type": "string"},
            "depth": {"type": "integer"}
        }),
        handler=lambda args, root: _get_builder(str(root)).concept_map(
            module=args.get("module", "."),
            depth=args.get("depth", 2)
        ),
    )

    tools["aicarmine_relationship_finder"] = ToolSpec(
        name="aicarmine_relationship_finder",
        description="Find relationships between modules",
        input_schema=object_schema({
            "module": {"type": "string"},
            "depth": {"type": "integer"}
        }),
        handler=lambda args, root: _get_builder(str(root)).relationship_finder(
            module=args.get("module", "."),
            depth=args.get("depth", 2)
        ),
    )

    tools["aicarmine_knowledge_summary"] = ToolSpec(
        name="aicarmine_knowledge_summary",
        description="Generate summary of knowledge graph",
        input_schema=object_schema(),
        handler=lambda args, root: _get_builder(str(root)).knowledge_summary(),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())