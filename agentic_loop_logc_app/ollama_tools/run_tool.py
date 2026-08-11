"""
Data RAG Agent - Ollama Tool Integration CLI

This script exposes the Data RAG Agent as an Ollama-compatible tool.
It can be called by Ollama models or used standalone.

Usage:
    python run_tool.py --action query --question "What is in this project?"
    python run_tool.py --action file --query "Apri la cartella agents"
    python run_tool.py --action search --pattern "*.py"
    python run_tool.py --action list --path agents
    python run_tool.py --action read --path agents/file_agent.py --line-range "1-10"
    python run_tool.py --action build --source-path .
    python run_tool.py --action status
    python run_tool.py --tool-def  # Print tool definition
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)


def main() -> int:
    """Main entry point for the Ollama tool integration."""
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
    
    from ollama_tools.data_rag_tool import OllamaDataRAGTool
    
    tool = OllamaDataRAGTool()
    
    if args.tool_def:
        print(json.dumps(tool.get_tool_definition(), indent=2))
        return 0
    
    result = tool.execute(args.action, **vars(args))
    print(json.dumps(result, indent=2))
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())