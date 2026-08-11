"""
MCP Server - Data RAG Agent MCP server implementation.

This server exposes RAG-based data querying tools via MCP protocol.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from agents.rag_agent import DataRAGAgent, QueryResult
from mcp.tools import TOOL_SCHEMAS, TOOL_HANDLERS

SERVER_NAME = "aicarmine-data-rag"
SERVER_VERSION = "1.0.0"
INSTRUCTIONS = "AI-Carmine Data RAG MCP. Use aicarmine_data_rag_query for data queries, aicarmine_data_rag_build_index to build the index, and aicarmine_data_rag_index_status to check index status."

logger = logging.getLogger(__name__)

# Global agent instance
_agent: DataRAGAgent | None = None


def _init_agent() -> DataRAGAgent:
    """Initialize the RAG agent."""
    global _agent
    if _agent is None:
        _agent = DataRAGAgent()
    return _agent


def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _tool_content(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json_dumps(value)}], "isError": is_error}


def _handle_query(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle the query tool."""
    question = arguments.get("question", "").strip()
    if not question:
        return {"ok": False, "error": "missing question"}
    
    agent = _init_agent()
    try:
        result: QueryResult = agent.query(question)
        return {
            "ok": True,
            "tool": "aicarmine_data_rag_query",
            "operation": "query",
            "question": question,
            "answer": result.answer,
            "sources": result.sources,
            "confidence": result.confidence,
        }
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return {"ok": False, "error": type(e).__name__, "detail": str(e)}


def _handle_build_index(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle the build_index tool."""
    source_path = arguments.get("source_path", ".")
    source_type = arguments.get("source_type", "filesystem")
    
    agent = _init_agent()
    try:
        result = agent.build_index(source_path=source_path, source_type=source_type)
        return {
            "ok": True,
            "tool": "aicarmine_data_rag_build_index",
            "operation": "build_index",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Build index failed: {e}")
        return {"ok": False, "error": type(e).__name__, "detail": str(e)}


def _handle_index_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle the index_status tool."""
    agent = _init_agent()
    # Check if index exists
    index_db = Path(agent.index_db)
    status = {
        "exists": index_db.exists(),
        "path": str(index_db),
    }
    if index_db.exists():
        import sqlite3
        conn = sqlite3.connect(f"file:{index_db.as_posix()}?mode=ro", uri=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            status["chunk_count"] = count
        finally:
            conn.close()
    
    return {
        "ok": True,
        "tool": "aicarmine_data_rag_index_status",
        "operation": "status",
        "status": status,
    }


def _handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle RPC message."""
    msg_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    
    if msg_id is None and method.startswith("notifications/"):
        return None
    
    try:
        if method == "initialize":
            return _ok(
                msg_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": INSTRUCTIONS,
                },
            )
        
        if method == "ping":
            return _ok(msg_id, {})
        
        if method == "tools/list":
            return _ok(msg_id, {"tools": TOOL_SCHEMAS})
        
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            
            handlers = {
                "aicarmine_data_rag_query": _handle_query,
                "aicarmine_data_rag_build_index": _handle_build_index,
                "aicarmine_data_rag_index_status": _handle_index_status,
            }
            
            handler = handlers.get(name)
            if handler is None:
                return _ok(msg_id, _tool_content({"ok": False, "error": f"unknown tool: {name}"}, is_error=True))
            return _ok(msg_id, handler(arguments))
        
        return _err(msg_id, -32601, f"method not found: {method}")
    
    except Exception as e:
        logger.error(f"RPC handling failed: {e}")
        return _ok(msg_id, _tool_content({"ok": False, "error": type(e).__name__, "detail": str(e)}, is_error=True))


def main() -> int:
    """Main entry point for the MCP server."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                return 0
            
            decoded = line.decode("utf-8-sig", errors="replace").strip()
            if not decoded:
                continue
            
            if decoded.startswith("{"):
                message = json.loads(decoded)
                response = _handle_rpc(message)
                if response is not None:
                    raw = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    sys.stdout.buffer.write(raw + b"\n")
                    sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            logger.error(f"Server error: {e}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())