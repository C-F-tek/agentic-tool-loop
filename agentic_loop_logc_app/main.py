"""
Main entry point for the Data RAG Agent - Agentic Loop Orchestrator.

This module serves as the central orchestrator for the agentic loop, coordinating:
1. RAG index building from database schemas and sample data
2. Query retrieval and reranking
3. Answer generation using LLM via Ollama or HTTP endpoint
4. Filesystem navigation tools
5. MCP tool integration
6. Diagnostics and error tracking

Usage:
    python main.py --query "What files are in this project?"
    python main.py --auto --max-steps 10
    python main.py --build --source-path .
    python main.py --status
    python main.py --list-tools
    python main.py --diagnostics --action summary
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.loop_orchestrator import LoopOrchestrator, OrchestratorConfig
from orchestrator.mcp_client import MCPClient, MCPClientConfig
from orchestrator.diagnostics import DiagnosticsTracker


def main() -> int:
    """Main entry point for the Data RAG Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Data RAG Agent - Agentic Loop Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --query "What files are in this project?"
  python main.py --auto --max-steps 10
  python main.py --build --source-path .
  python main.py --status
  python main.py --list-tools
  python main.py --diagnostics --action summary
        """,
    )
    
    parser.add_argument("--query", type=str, help="Natural language query")
    parser.add_argument("--question", type=str, help="Question to query (alias for --query)")
    parser.add_argument("--action", choices=["query", "build", "status", "list-tools", "diagnostics"], default=None)
    parser.add_argument("--auto", action="store_true", help="Run in auto mode with iterative refinement")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum number of steps in the loop")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence threshold")
    parser.add_argument("--source-path", type=str, default=".", help="Source path for indexing")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--diagnostics-action", choices=["log", "list", "resolve", "summary"], help="Diagnostics action")
    parser.add_argument("--diagnostics-error", type=str, help="Error message for diagnostics")
    parser.add_argument("--diagnostics-severity", type=str, default="error", help="Severity level for diagnostics")
    parser.add_argument("--diagnostics-category", type=str, default="tool", help="Category for diagnostics")
    parser.add_argument("--diagnostics-step", type=int, help="Step number for diagnostics")
    parser.add_argument("--diagnostics-id", type=str, help="Record ID for diagnostics")
    parser.add_argument("--diagnostics-resolution", type=str, help="Resolution text for diagnostics")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
    
    # Initialize components
    config = OrchestratorConfig(
        max_steps=args.max_steps,
        min_confidence=args.min_confidence,
        verbose=args.verbose,
        auto_mode=args.auto,
        source_path=args.source_path,
    )
    
    orchestrator = LoopOrchestrator(config)
    mcp_client = MCPClient()
    diagnostics = DiagnosticsTracker()
    
    try:
        # Handle diagnostics actions
        if args.action == "diagnostics" or args.diagnostics_action:
            diag_action = args.diagnostics_action or "summary"
            
            if diag_action == "log":
                if not args.diagnostics_error:
                    print("Error: --diagnostics-error is required for 'log' action", file=sys.stderr)
                    return 1
                
                record = diagnostics.log_error(
                    message=args.diagnostics_error,
                    severity=args.diagnostics_severity,
                    category=args.diagnostics_category,
                    step_number=args.diagnostics_step,
                )
                print(json.dumps(record.to_dict(), indent=2))
                return 0
            
            elif diag_action == "list":
                records = diagnostics.list_records(limit=50)
                result = {"count": len(records), "records": [r.to_dict() for r in records]}
                print(json.dumps(result, indent=2))
                return 0
            
            elif diag_action == "resolve":
                if not args.diagnostics_id or not args.diagnostics_resolution:
                    print("Error: --diagnostics-id and --diagnostics-resolution are required", file=sys.stderr)
                    return 1
                
                success = diagnostics.resolve_record(args.diagnostics_id, args.diagnostics_resolution)
                if success:
                    print(f"Record {args.diagnostics_id} resolved successfully")
                    return 0
                else:
                    print(f"Record {args.diagnostics_id} not found", file=sys.stderr)
                    return 1
            
            elif diag_action == "summary":
                summary = diagnostics.get_summary()
                print(json.dumps(summary, indent=2))
                return 0
        
        # Handle list-tools action
        if args.action == "list-tools":
            result = mcp_client.list_tools("sqlite_readonly")
            print(json.dumps(result, indent=2))
            return 0
        
        # Handle status action
        if args.action == "status":
            result = orchestrator.run_loop("status")
            print(json.dumps(result, indent=2))
            return 0
        
        # Handle build action
        if args.action == "build":
            result = orchestrator.run_loop("build")
            print(json.dumps(result, indent=2))
            return 0
        
        # Handle query action (default)
        query = args.query or args.question or ""
        if not query and args.action not in ("build", "status", "list-tools", "diagnostics"):
            print("Error: --query or --question is required", file=sys.stderr)
            return 1
        
        if query:
            try:
                if args.auto:
                    result = orchestrator.run_auto_loop(query)
                else:
                    result = orchestrator.run_loop(query)
                
                print(json.dumps(result, indent=2))
                return 0 if result["success"] else 1
            
            except Exception as e:
                logger.error(f"Orchestrator failed: {e}")
                diagnostics.log_error(
                    message=str(e),
                    severity="error",
                    category="tool",
                )
                return 1
        
        # Default: run auto loop
        result = orchestrator.run_auto_loop(query)
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Main entry point failed: {e}")
        diagnostics.log_error(
            message=str(e),
            severity="critical",
            category="tool",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())