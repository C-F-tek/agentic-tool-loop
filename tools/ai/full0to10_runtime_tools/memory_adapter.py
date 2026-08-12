"""Runtime adapter for Full0To10 SQLite memory tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from full0to10_sqlite_memory.db import connect
from full0to10_sqlite_memory.embedding import embed_missing_chunks
from full0to10_sqlite_memory.ingest import memory_add_file, memory_add_text
from full0to10_sqlite_memory.manifest import build_memory_manifest
from full0to10_sqlite_memory.schema import init_schema
from full0to10_sqlite_memory.search import memory_search

from .constants import MEMORY_TOOL_DEFAULTS, TOOL_SAFETY_FLAGS


def merged_args(args: dict[str, Any]) -> dict[str, Any]:
    merged = dict(MEMORY_TOOL_DEFAULTS)
    merged.update(args)
    return merged


def add_safety(report: dict[str, Any]) -> dict[str, Any]:
    output = dict(TOOL_SAFETY_FLAGS)
    output.update(report)
    return output


def invoke_memory_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    params = merged_args(args)
    db_path = Path(str(params["db"]))
    namespace = str(params["namespace"])
    conn = connect(db_path)

    if tool_name == "memory_init":
        init_schema(conn)
        return add_safety({"kind": tool_name, "passed": True, "db": str(db_path)})

    if tool_name == "memory_add_text":
        text = str(params.get("text") or "")
        if not text:
            return add_safety({"kind": tool_name, "passed": False, "errors": ["text is required"]})
        return add_safety(memory_add_text(conn, namespace, text, title=params.get("title")))

    if tool_name == "memory_add_file":
        path = params.get("path")
        if not path:
            return add_safety({"kind": tool_name, "passed": False, "errors": ["path is required"]})
        return add_safety(memory_add_file(conn, namespace, Path(str(path))))

    if tool_name == "memory_search":
        query = str(params.get("query") or "")
        if not query:
            return add_safety({"kind": tool_name, "passed": False, "errors": ["query is required"]})
        return add_safety(
            memory_search(
                conn,
                namespace,
                query,
                limit=int(params.get("limit", 10)),
                mode=str(params.get("mode", "hybrid")),
                embedding_model=str(params["embedding_model"]),
                embedding_provider=str(params["embedding_provider"]),
                ollama_url=str(params["ollama_url"]),
            )
        )

    if tool_name == "memory_embed_missing":
        return add_safety(
            embed_missing_chunks(
                conn,
                namespace,
                str(params["embedding_model"]),
                str(params["embedding_provider"] or "hash"),
                str(params["ollama_url"]),
                int(params.get("limit", 100)),
            )
        )

    if tool_name == "memory_manifest":
        return add_safety(build_memory_manifest(conn, db_path))

    return add_safety({"kind": tool_name, "passed": False, "errors": [f"unknown memory tool: {tool_name}"]})
