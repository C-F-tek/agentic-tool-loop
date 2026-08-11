"""
Ollama Tool Integration - Data RAG Agent as an Ollama tool.

This module exposes the Data RAG Agent and File Agent as Ollama tools,
allowing them to be used directly within Ollama models.

Usage:
    # Register the tool with Ollama
    ollama add data-rag-tool < data_rag_tool.modelfile
    
    # Use the tool
    ollama run data-rag-tool "Apri la cartella agents e dimmi il file più pertinente a RAG"
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.rag_agent import DataRAGAgent, QueryResult
from agents.file_agent import FileAgent

logger = logging.getLogger(__name__)


class OllamaDataRAGTool:
    """Ollama tool wrapper for the Data RAG Agent."""
    
    def __init__(self) -> None:
        """Initialize the tool."""
        self.rag_agent = DataRAGAgent()
        self.file_agent = FileAgent()
        
        # Tool definition for Ollama
        self.tool_def = {
            "name": "data_rag_query",
            "description": "Query databases and navigate filesystem using RAG and file analysis. Supports natural language queries in Italian and English.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["query", "file", "search", "list", "read", "build", "status"],
                        "description": "Action to perform"
                    },
                    "question": {
                        "type": "string",
                        "description": "Question to query (for 'query' action)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language query (for 'file' action)"
                    },
                    "path": {
                        "type": "string",
                        "description": "Path for file operations"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (for 'search' action)"
                    },
                    "extension": {
                        "type": "string",
                        "description": "File extension filter (for 'search' action)"
                    },
                    "line_range": {
                        "type": "string",
                        "description": "Line range for read action (e.g., '10-20')"
                    },
                    "source_path": {
                        "type": "string",
                        "description": "Source path for indexing (for 'build' action)"
                    }
                },
                "required": ["action"]
            }
        }
    
    def get_tool_definition(self) -> dict[str, Any]:
        """Return the tool definition for Ollama."""
        return self.tool_def
    
    def execute(self, action: str, **kwargs) -> dict[str, Any]:
        """Execute an action through the appropriate agent."""
        result = {"success": False, "result": None, "error": None}
        
        try:
            if action == "query":
                question = kwargs.get("question", "")
                if not question:
                    result["error"] = "Question is required for 'query' action"
                    return result
                
                query_result = self.rag_agent.query(question)
                result["success"] = True
                result["result"] = {
                    "answer": query_result.answer,
                    "confidence": query_result.confidence,
                    "execution_time_ms": query_result.execution_time_ms,
                    "sources": query_result.sources,
                }
                
            elif action == "file":
                query_text = kwargs.get("query", "")
                if not query_text:
                    result["error"] = "Query is required for 'file' action"
                    return result
                
                nl_result = self.file_agent.natural_language_query(query_text)
                result["success"] = True
                result["result"] = nl_result
                
            elif action == "search":
                pattern = kwargs.get("pattern", "")
                if not pattern:
                    result["error"] = "Pattern is required for 'search' action"
                    return result
                
                path = kwargs.get("path", ".")
                extension = kwargs.get("extension")
                files = self.file_agent.search_files(pattern, path=path, extension=extension, max_results=50)
                result["success"] = True
                result["result"] = {"files": files, "count": len(files)}
                
            elif action == "list":
                path = kwargs.get("path", ".")
                listing = self.file_agent.navigate(path)
                result["success"] = True
                result["result"] = {
                    "path": listing.path,
                    "files": listing.files,
                    "directories": listing.directories,
                    "total_files": listing.total_files,
                    "total_dirs": listing.total_dirs,
                }
                
            elif action == "read":
                file_path = kwargs.get("path", "")
                if not file_path:
                    result["error"] = "Path is required for 'read' action"
                    return result
                
                line_range = None
                if kwargs.get("line_range"):
                    parts = kwargs.get("line_range", "").split("-")
                    if len(parts) == 2:
                        line_range = (int(parts[0]), int(parts[1]))
                
                content = self.file_agent.read_file(file_path, line_range=line_range)
                result["success"] = True
                result["result"] = {"content": content}
                
            elif action == "build":
                source_path = kwargs.get("source_path", ".")
                build_result = self.rag_agent.build_index(source_path=source_path)
                result["success"] = True
                result["result"] = build_result
                
            elif action == "status":
                index_db = Path(self.rag_agent.index_db)
                import sqlite3
                conn = sqlite3.connect(f"file:{index_db.as_posix()}?mode=ro", uri=True)
                try:
                    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                    types = conn.execute("SELECT kind, COUNT(*) FROM chunks GROUP BY kind").fetchall()
                    result["success"] = True
                    result["result"] = {
                        "chunk_count": count,
                        "chunks_by_type": dict(types),
                        "index_path": str(index_db),
                    }
                finally:
                    conn.close()
                    
            else:
                result["error"] = f"Unknown action: {action}"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            result["error"] = str(e)
        
        return result


def create_ollama_tool_script() -> str:
    """Create a script that can be used as an Ollama tool."""
    return '''#!/usr/bin/env python3
"""
Data RAG Agent - Ollama Tool Integration

This script exposes the Data RAG Agent as an Ollama tool.
It can be called by Ollama models to query databases and navigate filesystems.

Usage:
    python data_rag_tool.py --action query --question "What is in this project?"
    python data_rag_tool.py --action file --query "Apri la cartella agents"
    python data_rag_tool.py --action search --pattern "*.py"
    python data_rag_tool.py --action list --path agents
    python data_rag_tool.py --action read --path agents/file_agent.py --line-range "1-10"
    python data_rag_tool.py --action build --source-path .
    python data_rag_tool.py --action status
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ollama_tools.data_rag_tool import OllamaDataRAGTool


def main() -> int:
    parser = argparse.ArgumentParser(description="Data RAG Agent - Ollama Tool")
    parser.add_argument("--action", required=True, choices=["query", "file", "search", "list", "read", "build", "status"])
    parser.add_argument("--question", type=str, help="Question for query action")
    parser.add_argument("--query", type=str, help="Natural language query for file action")
    parser.add_argument("--path", type=str, default=".", help="Path for file operations")
    parser.add_argument("--pattern", type=str, help="Search pattern")
    parser.add_argument("--extension", type=str, help="File extension filter")
    parser.add_argument("--line-range", type=str, help="Line range for read")
    parser.add_argument("--source-path", type=str, default=".", help="Source path for build")
    parser.add_argument("--tool-def", action="store_true", help="Print tool definition and exit")
    
    args = parser.parse_args()
    
    tool = OllamaDataRAGTool()
    
    if args.tool_def:
        print(json.dumps(tool.get_tool_definition(), indent=2))
        return 0
    
    result = tool.execute(args.action, **vars(args))
    print(json.dumps(result, indent=2))
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def create_modelfile() -> str:
    """Create a Modelfile for Ollama tool registration."""
    return '''FROM llama3.2

SYSTEM """You have access to the data_rag_query tool. Use it to query databases and navigate filesystems.

Tool definition:
{
  "name": "data_rag_query",
  "description": "Query databases and navigate filesystem using RAG and file analysis.",
  "parameters": {...}
}

When the user asks about database contents or file relevance, use the data_rag_query tool with the appropriate action."""

PARAMETER temperature 0.3
PARAMETER top_p 0.9
'''


def main() -> int:
    """Main entry point for the Ollama tool integration script."""
    parser = argparse.ArgumentParser(description="Data RAG Agent - Ollama Tool Integration")
    parser.add_argument("--action", choices=["query", "file", "search", "list", "read", "build", "status"], required=True)
    parser.add_argument("--question", type=str, help="Question for query action")
    parser.add_argument("--query", type=str, help="Natural language query for file action")
    parser.add_argument("--path", type=str, default=".", help="Path for file operations")
    parser.add_argument("--pattern", type=str, help="Search pattern")
    parser.add_argument("--extension", type=str, help="File extension filter")
    parser.add_argument("--line-range", type=str, help="Line range for read")
    parser.add_argument("--source-path", type=str, default=".", help="Source path for build")
    parser.add_argument("--tool-def", action="store_true", help="Print tool definition and exit")
    
    args = parser.parse_args()
    
    tool = OllamaDataRAGTool()
    
    if args.tool_def:
        print(json.dumps(tool.get_tool_definition(), indent=2))
        return 0
    
    result = tool.execute(args.action, **vars(args))
    print(json.dumps(result, indent=2))
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())