"""
Loop Orchestrator - Agentic loop coordination for Data RAG Agent.

This module orchestrates the flow between different agents and tools in a loop,
similar to the main broker system. It manages:
1. Query understanding and intent detection
2. Tool selection and execution
3. Result aggregation and verification
4. Loop continuation based on confidence and completeness

Usage:
    python orchestrator/main_loop.py --query "What files are in this project?"
    python orchestrator/main_loop.py --auto --max-steps 10
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.rag_agent import DataRAGAgent, QueryResult
from agents.file_agent import FileAgent
from ollama_tools.data_rag_tool import OllamaDataRAGTool


logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of a single step in the loop."""
    step_number: int
    action: str
    success: bool
    result: dict[str, Any]
    confidence: float
    execution_time_ms: int
    next_action: str | None = None
    error: str | None = None


@dataclass
class OrchestratorConfig:
    """Configuration for the loop orchestrator."""
    max_steps: int = 10
    min_confidence: float = 0.7
    verbose: bool = False
    auto_mode: bool = False
    source_path: str = "."
    tools: dict[str, bool] = field(default_factory=dict)


class LoopOrchestrator:
    """Orchestrates the agentic loop for data query tasks."""
    
    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        """Initialize the orchestrator."""
        self.config = config or OrchestratorConfig()
        
        # Initialize agents
        self.rag_agent = DataRAGAgent()
        self.file_agent = FileAgent()
        self.ollama_tool = OllamaDataRAGTool()
        
        # Loop state
        self.steps: list[StepResult] = []
        self.current_step = 0
        self.loop_running = False
        
        # Tool priority order
        self.tool_priority = ["query", "file", "search", "list", "read", "build", "status"]
    
    def analyze_query(self, query: str) -> dict[str, Any]:
        """Analyze the query and determine best action."""
        start_time = time.time()
        
        # Check if query is about database/data
        is_data_query = any(kw in query.lower() for kw in ["database", "data", "query", "question", "who", "what", "when", "where"])
        
        # Check if query is about files/folders
        is_file_query = any(kw in query.lower() for kw in ["file", "folder", "directory", "cartella", "agents", "config", "test"])
        
        # Determine intent
        if is_data_query and not is_file_query:
            intent = "query"
            action = "query"
        elif is_file_query:
            intent = "file_analysis"
            action = "file"
        else:
            intent = "unknown"
            action = "query"
        
        result = {
            "intent": intent,
            "action": action,
            "is_data_query": is_data_query,
            "is_file_query": is_file_query,
            "execution_time_ms": int((time.time() - start_time) * 1000),
        }
        
        logger.debug(f"Query analysis: {result}")
        return result
    
    def execute_step(self, step_number: int, action: str, **kwargs) -> StepResult:
        """Execute a single step in the loop."""
        start_time = time.time()
        
        try:
            if action == "query":
                question = kwargs.get("question", kwargs.get("query", ""))
                if not question:
                    return StepResult(
                        step_number=step_number,
                        action=action,
                        success=False,
                        result={},
                        confidence=0.0,
                        execution_time_ms=0,
                        error="Question required for query action",
                    )
                
                result = self.rag_agent.query(question)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result={
                        "answer": result.answer,
                        "confidence": result.confidence,
                        "sources": result.sources,
                    },
                    confidence=result.confidence,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "file":
                query_text = kwargs.get("query", "")
                if not query_text:
                    return StepResult(
                        step_number=step_number,
                        action=action,
                        success=False,
                        result={},
                        confidence=0.0,
                        execution_time_ms=0,
                        error="Query required for file action",
                    )
                
                nl_result = self.file_agent.natural_language_query(query_text)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result=nl_result,
                    confidence=0.8,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "search":
                pattern = kwargs.get("pattern", "")
                path = kwargs.get("path", ".")
                extension = kwargs.get("extension")
                files = self.file_agent.search_files(pattern, path=path, extension=extension, max_results=50)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result={"files": files, "count": len(files)},
                    confidence=0.9,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "list":
                path = kwargs.get("path", ".")
                listing = self.file_agent.navigate(path)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result={
                        "path": listing.path,
                        "files": listing.files,
                        "directories": listing.directories,
                        "total_files": listing.total_files,
                        "total_dirs": listing.total_dirs,
                    },
                    confidence=0.95,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "read":
                file_path = kwargs.get("path", "")
                line_range = kwargs.get("line_range")
                if not file_path:
                    return StepResult(
                        step_number=step_number,
                        action=action,
                        success=False,
                        result={},
                        confidence=0.0,
                        execution_time_ms=0,
                        error="Path required for read action",
                    )
                
                content = self.file_agent.read_file(file_path, line_range=line_range)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result={"content": content},
                    confidence=1.0,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "build":
                source_path = kwargs.get("source_path", ".")
                build_result = self.rag_agent.build_index(source_path=source_path)
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=True,
                    result=build_result,
                    confidence=0.9,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
                
            elif action == "status":
                index_db = Path(self.rag_agent.index_db)
                import sqlite3
                conn = sqlite3.connect(f"file:{index_db.as_posix()}?mode=ro", uri=True)
                try:
                    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                    types = conn.execute("SELECT kind, COUNT(*) FROM chunks GROUP BY kind").fetchall()
                    step_result = StepResult(
                        step_number=step_number,
                        action=action,
                        success=True,
                        result={
                            "chunk_count": count,
                            "chunks_by_type": dict(types),
                            "index_path": str(index_db),
                        },
                        confidence=1.0,
                        execution_time_ms=int((time.time() - start_time) * 1000),
                    )
                finally:
                    conn.close()
                    
            else:
                step_result = StepResult(
                    step_number=step_number,
                    action=action,
                    success=False,
                    result={},
                    confidence=0.0,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    error=f"Unknown action: {action}",
                )
                
        except Exception as e:
            logger.error(f"Step {step_number} failed: {e}")
            step_result = StepResult(
                step_number=step_number,
                action=action,
                success=False,
                result={},
                confidence=0.0,
                execution_time_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
        
        self.steps.append(step_result)
        self.current_step += 1
        return step_result
    
    def determine_next_action(self, query: str, last_result: StepResult | None) -> str | None:
        """Determine the next action based on current state."""
        if self.current_step >= self.config.max_steps:
            return None
        
        if last_result and last_result.confidence >= self.config.min_confidence:
            return None
        
        # Analyze query for next action
        analysis = self.analyze_query(query)
        
        if last_result is None:
            # First step
            return analysis["action"]
        
        # If confidence is low, try alternative action
        if last_result.confidence < self.config.min_confidence:
            if analysis["action"] == "query":
                return "file"
            elif analysis["action"] == "file":
                return "query"
        
        return None
    
    def run_loop(self, query: str) -> dict[str, Any]:
        """Run the agentic loop for a given query."""
        logger.info(f"Starting agentic loop for query: {query}")
        
        self.loop_running = True
        start_time = time.time()
        
        result = {
            "success": False,
            "steps": [],
            "final_answer": "",
            "total_steps": 0,
            "total_time_ms": 0,
            "confidence": 0.0,
        }
        
        try:
            # Initial analysis
            analysis = self.analyze_query(query)
            next_action = analysis["action"]
            
            while self.loop_running and self.current_step < self.config.max_steps:
                logger.debug(f"Step {self.current_step + 1}: Executing action '{next_action}'")
                
                # Execute step
                step_result = self.execute_step(
                    step_number=self.current_step + 1,
                    action=next_action,
                    query=query,
                )
                
                result["steps"].append({
                    "step": self.current_step + 1,
                    "action": next_action,
                    "success": step_result.success,
                    "confidence": step_result.confidence,
                })
                
                # Check if we should continue
                if step_result.success and step_result.confidence >= self.config.min_confidence:
                    result["success"] = True
                    result["final_answer"] = json.dumps(step_result.result, indent=2)
                    result["confidence"] = step_result.confidence
                    break
                
                # Determine next action
                next_action = self.determine_next_action(query, step_result)
                if next_action is None:
                    break
            
            result["total_steps"] = self.current_step
            result["total_time_ms"] = int((time.time() - start_time) * 1000)
            
        except Exception as e:
            logger.error(f"Loop failed: {e}")
            result["error"] = str(e)
        
        self.loop_running = False
        return result
    
    def run_auto_loop(self, query: str) -> dict[str, Any]:
        """Run the loop in auto mode with iterative refinement."""
        logger.info(f"Starting auto loop for query: {query}")
        
        self.loop_running = True
        start_time = time.time()
        
        result = {
            "success": False,
            "steps": [],
            "final_answer": "",
            "total_steps": 0,
            "total_time_ms": 0,
            "confidence": 0.0,
        }
        
        try:
            # Step 1: Build index if needed
            status_result = self.execute_step(1, "status")
            result["steps"].append({"step": 1, "action": "status", "result": status_result.result})
            
            if status_result.success and status_result.result.get("chunk_count", 0) == 0:
                build_result = self.execute_step(2, "build", source_path=self.config.source_path)
                result["steps"].append({"step": 2, "action": "build", "result": build_result.result})
            
            # Step 2: Execute query
            query_result = self.execute_step(
                len(result["steps"]) + 1,
                "query",
                question=query,
            )
            result["steps"].append({"step": len(result["steps"]) + 1, "action": "query", "result": query_result.result})
            
            if query_result.success and query_result.confidence >= self.config.min_confidence:
                result["success"] = True
                result["final_answer"] = query_result.result.get("answer", "")
                result["confidence"] = query_result.confidence
            
            # Step 3: If confidence low, try file analysis
            if not result["success"] or result["confidence"] < self.config.min_confidence:
                file_result = self.execute_step(
                    len(result["steps"]) + 1,
                    "file",
                    query=query,
                )
                result["steps"].append({"step": len(result["steps"]) + 1, "action": "file", "result": file_result.result})
                
                if file_result.success:
                    result["final_answer"] = json.dumps(file_result.result, indent=2)
                    result["confidence"] = file_result.confidence
                    if file_result.confidence >= self.config.min_confidence:
                        result["success"] = True
            
            result["total_steps"] = self.current_step
            result["total_time_ms"] = int((time.time() - start_time) * 1000)
            
        except Exception as e:
            logger.error(f"Auto loop failed: {e}")
            result["error"] = str(e)
        
        self.loop_running = False
        return result
    
    def get_loop_state(self) -> dict[str, Any]:
        """Return current loop state."""
        return {
            "current_step": self.current_step,
            "max_steps": self.config.max_steps,
            "loop_running": self.loop_running,
            "steps": [
                {
                    "step": s.step_number,
                    "action": s.action,
                    "success": s.success,
                    "confidence": s.confidence,
                }
                for s in self.steps
            ],
        }


def main() -> int:
    """Main entry point for the orchestrator CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data RAG Agent - Loop Orchestrator")
    parser.add_argument("--query", type=str, help="Query to execute")
    parser.add_argument("--question", type=str, help="Question to query")
    parser.add_argument("--auto", action="store_true", help="Run in auto mode")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum number of steps")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence threshold")
    parser.add_argument("--source-path", type=str, default=".", help="Source path for indexing")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
    
    config = OrchestratorConfig(
        max_steps=args.max_steps,
        min_confidence=args.min_confidence,
        verbose=args.verbose,
        auto_mode=args.auto,
        source_path=args.source_path,
    )
    
    orchestrator = LoopOrchestrator(config)
    
    # Get query from args
    query = args.query or args.question or ""
    if not query:
        print("Error: --query or --question is required", file=sys.stderr)
        return 1
    
    try:
        if args.auto:
            result = orchestrator.run_auto_loop(query)
        else:
            result = orchestrator.run_loop(query)
        
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1
    
    except Exception as e:
        logger.error(f"Orchestrator failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())