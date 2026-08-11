"""
Data Query Agent - CLI entry point for RAG-based data querying and filesystem navigation.

Usage:
    python agents/data_query.py --action build --source-path .
    python agents/data_query.py --action query --question "Who bought laptops?"
    python agents/data_query.py --action status
    python agents/data_query.py --action file --query "Apri la cartella agents e dimmi il file più pertinente a RAG"
    python agents/data_query.py --action search --pattern "*.py" --path .
    python agents/data_query.py --action list --path agents
    python agents/data_query.py --action read --path agents/file_agent.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.rag_agent import DataRAGAgent, QueryResult
from agents.file_agent import FileAgent


def run_query(agent: DataRAGAgent, question: str) -> QueryResult:
    """Run a query against the RAG index."""
    return agent.query(question)


def build_index(agent: DataRAGAgent, source_path: str = ".", source_type: str = "filesystem") -> dict:
    """Build the RAG index."""
    return agent.build_index(source_path=source_path, source_type=source_type)


def run_file_agent(file_agent: FileAgent, query: str) -> dict[str, Any]:
    """Run a natural language query through the FileAgent."""
    return file_agent.natural_language_query(query)


def search_files(file_agent: FileAgent, pattern: str, path: str = ".", extension: str | None = None) -> list[dict]:
    """Search for files by pattern."""
    return file_agent.search_files(pattern, path=path, extension=extension, max_results=50)


def list_directory(file_agent: FileAgent, path: str = ".") -> dict:
    """List directory contents."""
    listing = file_agent.navigate(path)
    return {
        "path": listing.path,
        "files": listing.files,
        "directories": listing.directories,
        "total_files": listing.total_files,
        "total_dirs": listing.total_dirs,
    }


def read_file(file_agent: FileAgent, file_path: str, line_range: tuple[int, int] | None = None) -> str:
    """Read a file's contents."""
    return file_agent.read_file(file_path, line_range=line_range)


def main() -> int:
    """Main entry point for the data query agent."""
    parser = argparse.ArgumentParser(description="Data RAG Agent - Query databases and navigate filesystem with natural language")
    parser.add_argument("--action", choices=["query", "build", "status", "file", "search", "list", "read"], default="query", help="Action to perform")
    parser.add_argument("--question", type=str, help="Question to query (for 'query' action)")
    parser.add_argument("--query", type=str, help="Natural language query (for 'file' action)")
    parser.add_argument("--source-path", type=str, default=".", help="Source path for indexing (for 'build' action)")
    parser.add_argument("--source-type", type=str, default="filesystem", help="Source type for indexing")
    parser.add_argument("--pattern", type=str, help="Search pattern (for 'search' action)")
    parser.add_argument("--path", type=str, default=".", help="Path for file operations")
    parser.add_argument("--extension", type=str, help="File extension filter (for 'search' action)")
    parser.add_argument("--line-range", type=str, help="Line range for read action (e.g., '10-20')")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
    
    # Initialize agents
    rag_agent = DataRAGAgent()
    # Only set root_path for actions that navigate directories (not read/search which use explicit paths)
    file_agent = FileAgent(args.path if args.action in ["file", "list"] else None)
    
    try:
        if args.action == "query":
            if not args.question:
                print("Error: --question is required for 'query' action", file=sys.stderr)
                return 1
            
            result = run_query(rag_agent, args.question)
            print(f"\n=== Query Result ===")
            print(f"Question: {args.question}")
            print(f"Confidence: {result.confidence:.4f}")
            print(f"Execution time: {result.execution_time_ms}ms")
            print(f"\nAnswer:\n{result.answer}")
            
            if result.sources:
                print(f"\n=== Sources ({len(result.sources)} relevant) ===")
                for i, source in enumerate(result.sources, 1):
                    path = source.get("path", "unknown")
                    start = source.get("start_line", 0)
                    end = source.get("end_line", 0)
                    score = source.get("rerank_score")
                    print(f"[{i}] Path: {path} (lines {start}-{end}, score: {score})")
            
            return 0
        
        elif args.action == "build":
            result = build_index(rag_agent, args.source_path, args.source_type)
            print(f"\n=== Index Build Result ===")
            print(f"Success: {result.get('ok', False)}")
            print(f"Source: {result.get('source', 'N/A')}")
            print(f"Type: {result.get('source_type', 'N/A')}")
            print(f"Files indexed: {result.get('files_indexed', 0)}")
            print(f"Total chunks: {result.get('total_chunks', 0)}")
            print(f"Schema tables: {result.get('schema_tables', 0)}")
            print(f"Schema columns: {result.get('schema_columns', 0)}")
            print(f"Execution time: {result.get('execution_time_ms', 0)}ms")
            
            if result.get("error"):
                print(f"Error: {result['error']}")
                return 1
            
            return 0 if result.get("ok") else 1
        
        elif args.action == "status":
            index_db = Path(rag_agent.index_db)
            print(f"\n=== RAG Index Status ===")
            print(f"Index path: {index_db}")
            print(f"Exists: {index_db.exists()}")
            
            if index_db.exists():
                import sqlite3
                conn = sqlite3.connect(f"file:{index_db.as_posix()}?mode=ro", uri=True)
                try:
                    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                    print(f"Chunk count: {count}")
                    
                    # Count by kind
                    types = conn.execute("SELECT kind, COUNT(*) FROM chunks GROUP BY kind").fetchall()
                    print(f"\nChunks by type:")
                    for kind, cnt in types:
                        print(f"  {kind}: {cnt}")
                finally:
                    conn.close()
            
            return 0
        
        elif args.action == "file":
            if not args.query:
                print("Error: --query is required for 'file' action", file=sys.stderr)
                return 1
            
            result = run_file_agent(file_agent, args.query)
            print(f"\n=== File Agent Result ===")
            print(f"Query: {args.query}")
            print(f"Intent: {result.get('intent', 'unknown')}")
            print(f"Execution time: {result.get('execution_time_ms', 0)}ms")
            print(f"\nResponse:\n{result.get('response', 'N/A')}")
            
            return 0
        
        elif args.action == "search":
            if not args.pattern:
                print("Error: --pattern is required for 'search' action", file=sys.stderr)
                return 1
            
            results = search_files(file_agent, args.pattern, args.path, args.extension)
            print(f"\n=== Search Results ===")
            print(f"Pattern: {args.pattern}")
            print(f"Path: {args.path}")
            print(f"Extension filter: {args.extension}")
            print(f"Found: {len(results)} files")
            
            for i, f in enumerate(results, 1):
                print(f"[{i}] {f['path']} ({f.get('size', 0)} bytes)")
            
            return 0
        
        elif args.action == "list":
            listing = list_directory(file_agent, args.path)
            print(f"\n=== Directory Listing ===")
            print(f"Path: {listing['path']}")
            print(f"Total files: {listing['total_files']}")
            print(f"Total directories: {listing['total_dirs']}")
            print(f"\nFiles ({len(listing['files'])}):")
            for f in listing['files'][:50]:
                print(f"  - {f}")
            if len(listing['files']) > 50:
                print(f"  ... and {len(listing['files']) - 50} more")
            print(f"\nDirectories ({len(listing['directories'])}):")
            for d in listing['directories'][:20]:
                print(f"  / {d}")
            if len(listing['directories']) > 20:
                print(f"  ... and {len(listing['directories']) - 20} more")
            
            return 0
        
        elif args.action == "read":
            line_range = None
            if args.line_range:
                parts = args.line_range.split("-")
                if len(parts) == 2:
                    line_range = (int(parts[0]), int(parts[1]))
            
            content = read_file(file_agent, args.path, line_range=line_range)
            print(f"\n=== File Content ===")
            print(f"Path: {args.path}")
            if line_range:
                print(f"Lines: {line_range[0]}-{line_range[1]}")
            print(f"\n{content}")
            
            return 0
    
    except Exception as e:
        logging.error(f"Operation failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
