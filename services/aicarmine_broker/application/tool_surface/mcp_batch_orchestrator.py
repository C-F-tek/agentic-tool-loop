"""MCP Batch Orchestrator — Apply broker batch patterns to existing MCP servers.

This module demonstrates how to compose existing read-only MCP tools into
parallel batch operations using the broker's batch architecture patterns:
- Canonical key deduplication
- Batch window pagination (offset/max_chars)
- Micro-batch contract with guard policies
- Read-only enforcement
- Failure tracking via failure_counter

Usage:
    from services.aicarmine_broker.application.tool_surface.mcp_batch_orchestrator import MCPBatchOrchestrator
    
    orchestrator = MCPBatchOrchestrator()
    results = await orchestrator.execute_batch(batch_operations)
"""
from __future__ import annotations
 
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple
from pathlib import Path

# Import broker batch patterns
from ..shared.diagnostics import diagnostic_row, safe_json_text, safe_text


# ============================================================================
# Canonical Key Deduplication (from batch_contract.py pattern)
# ============================================================================

def _canonical_value(value: Any, *, _depth: int = 0) -> Any:
    """Recursively canonicalize nested structures for deterministic serialization."""
    if _depth > 8:
        return safe_text(value, limit=300)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        try:
            pairs = sorted(value.items(), key=lambda pair: safe_text(pair[0], limit=120))
        except Exception:
            return diagnostic_row("canonical_mapping_failed", exc=value)
        for key, item in pairs:
            try:
                canonical = _canonical_value(item, _depth=_depth + 1)
                if canonical not in (None, "", [], {}):
                    out[safe_text(key, limit=120)] = canonical
            except Exception:
                out[safe_text(key, limit=120)] = diagnostic_row("canonical_value_failed", exc=item)
        return out
    if isinstance(value, (list, tuple)):
        out: list[Any] = []
        for index, item in enumerate(value):
            try:
                canonical = _canonical_value(item, _depth=_depth + 1)
                if canonical not in (None, "", [], {}):
                    out.append(canonical)
            except Exception:
                out.append(diagnostic_row("canonical_list_item_failed", exc=item))
        return out
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        return text
    return value


def _canonical_args(args: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize tool arguments for deduplication."""
    out: dict[str, Any] = {}
    source = dict(args) if isinstance(args, dict) else {}
    for key, value in source.items():
        canonical = _canonical_value(value)
        if canonical not in (None, "", [], {}):
            out[str(key)] = canonical
    return out


def mcp_call_key(server: str, tool: str, args: dict[str, Any]) -> str:
    """Generate unique identifier for an MCP tool call (server+tool+canonical_args)."""
    canonical_args = _canonical_args(args)
    payload = {
        "server": safe_text(server, limit=160).strip(),
        "tool": safe_text(tool, limit=160).strip(),
        "arguments": canonical_args,
    }
    text, _ = safe_json_text(payload, reason="mcp_call_key_json_failed", separators=(",", ":"))
    return text


# ============================================================================
# Batch Window Pagination (from candidate_actions.py pattern)
# ============================================================================

@dataclass
class BatchWindow:
    """Pagination window for streaming large results."""
    offset: int = 0
    max_chars: int = 3000
    full_chars: int = 0
    max_batch_actions: int = 8
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BatchWindow":
        if not isinstance(d, dict):
            return cls()
        try:
            offset = max(0, int(d.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        try:
            max_chars = max(500, int(d.get("max_chars") or 3000))
        except (TypeError, ValueError):
            max_chars = 3000
        try:
            full_chars = max(0, int(d.get("full_chars") or 0))
        except (TypeError, ValueError):
            full_chars = 0
        try:
            max_actions = max(1, min(8, int(d.get("max_batch_actions") or 8)))
        except (TypeError, ValueError):
            max_actions = 8
        return cls(offset=offset, max_chars=max_chars, full_chars=full_chars, max_batch_actions=max_actions)


def _generate_batch_offsets(batch_window: BatchWindow) -> List[int]:
    """Generate offset values for batch pagination."""
    offsets = [batch_window.offset]
    if batch_window.full_chars > batch_window.offset and batch_window.max_chars > 0:
        current = batch_window.offset + batch_window.max_chars
        while current < batch_window.full_chars and len(offsets) < batch_window.max_batch_actions:
            offsets.append(current)
            current += batch_window.max_chars
    return offsets


# ============================================================================
# Micro-Batch Contract (from candidate_actions.py pattern)
# ============================================================================

@dataclass
class MicroBatchContract:
    """Schema-enforced allowed operations with guard policies."""
    schema: str = "mcp_batch_contract.v1"
    allowed: bool = True
    mode: str = "read_only_parallel"
    max_batch_size: int = 8
    allowed_servers: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    writes_allowed: bool = False
    validation_tools_allowed: bool = False
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MicroBatchContract":
        if not isinstance(d, dict):
            return cls()
        return cls(
            schema=d.get("schema", cls.schema),
            allowed=bool(d.get("allowed", True)),
            mode=safe_text(d.get("mode", cls.mode), limit=160),
            max_batch_size=max(1, min(cls.max_batch_size, int(d.get("max_batch_size", 8)))),
            allowed_tools=list(d.get("allowed_tools", [])),
            writes_allowed=bool(d.get("writes_allowed", False)),
            validation_tools_allowed=bool(d.get("validation_tools_allowed", False)),
        )


# ============================================================================
# Failure Tracking (from loop.py pattern)
# ============================================================================

class SimpleFailureCounter:
    """Simple failure counter for batch operation tracking."""
    
    def __init__(self):
        self._counts: Dict[str, int] = {}
    
    def increment(self, operation_id: str, guard_type: str) -> None:
        key = f"{operation_id}:{guard_type}"
        self._counts[key] = self._counts.get(key, 0) + 1
    
    def get_counts(self) -> Dict[str, int]:
        return dict(self._counts)


# ============================================================================
# MCP Batch Orchestrator
# ============================================================================

@dataclass
class MCPBatchOperation:
    """Single batch operation definition."""
    server: str
    tool: str
    args: dict[str, Any]
    operation_id: str = ""
    priority: int = 0


@dataclass
class MCPBatchResult:
    """Result of a batch operation."""
    operation: MCPBatchOperation
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: float = 0.0
    cache_hit: bool = False


class MCPBatchOrchestrator:
    """Execute parallel read-only MCP tool calls with deduplication and failure tracking.
    
    This orchestrator applies the broker's batch architecture patterns to existing
    MCP servers, enabling efficient parallel execution of read-only operations.
    
    Example usage:
        orchestrator = MCPBatchOrchestrator()
        
        # Define batch operations
        operations = [
            MCPBatchOperation(
                server="aicarmine_repo_search_det",
                tool="repo_search_rg",
                args={"path": ".", "pattern": "def \\w+", "max_results": 50},
            ),
            MCPBatchOperation(
                server="aicarmine_repo_symbol_index",
                tool="repo_search_ctags",
                args={"path": ".", "limit": 100},
            ),
        ]
        
        # Execute batch
        results = orchestrator.execute_batch_sync(operations)
    """
    
    def __init__(self, max_concurrent: int = 4, timeout_seconds: float = 60.0):
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
        self.failure_counter = SimpleFailureCounter()
        self._cache: Dict[str, Any] = {}
        self._cache_stats = {"hits": 0, "misses": 0}
    
    def execute_batch_sync(
        self,
        operations: List[MCPBatchOperation],
        contract: Optional[MicroBatchContract] = None,
        batch_window: Optional[BatchWindow] = None,
    ) -> List[MCPBatchResult]:
        """Execute MCP batch operations synchronously with deduplication."""
        if not operations:
            return []
        
        # Apply micro-batch contract guards
        if contract and not contract.allowed:
            return [
                MCPBatchResult(
                    operation=op,
                    error="Batch not allowed by contract",
                    error_type="batch_contract_denied",
                )
                for op in operations
            ]
        
        # Enforce read-only policy
        if not contract or not contract.writes_allowed:
            write_tools = {"write_to_file", "replace_in_file", "execute_command"}
            operations = [
                op for op in operations
                if op.tool not in write_tools
            ]
        
        # Deduplicate by canonical key
        seen_keys: Set[str] = set()
        deduplicated: List[MCPBatchOperation] = []
        for op in operations:
            key = mcp_call_key(op.server, op.tool, op.args)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduplicated.append(op)
        
        # Apply batch window pagination if specified
        if batch_window and len(deduplicated) > batch_window.max_batch_actions:
            deduplicated = deduplicated[:batch_window.max_batch_actions]
        
        # Execute with concurrency limit
        results = self._execute_with_concurrency(deduplicated)
        
        # Track failures
        for result in results:
            if result.error:
                self.failure_counter.increment(
                    result.operation.operation_id or f"{result.operation.server}:{result.operation.tool}",
                    result.error_type or "execution_error",
                )
        
        return results
    
    def _execute_with_concurrency(self, operations: List[MCPBatchOperation]) -> List[MCPBatchResult]:
        """Execute operations with concurrency limiting and caching."""
        import concurrent.futures
        
        results: List[MCPBatchResult] = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_to_op = {}
            for op in operations:
                future = executor.submit(self._execute_single, op)
                future_to_op[future] = op
            
            for future in concurrent.futures.as_completed(future_to_op, timeout=self.timeout_seconds):
                op = future_to_op[future]
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    results.append(
                        MCPBatchResult(
                            operation=op,
                            error=f"Timeout after {self.timeout_seconds}s",
                            error_type="timeout",
                        )
                    )
                except Exception as exc:
                    results.append(
                        MCPBatchResult(
                            operation=op,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )
                    )
        
        return results
    
    def _execute_single(self, operation: MCPBatchOperation) -> MCPBatchResult:
        """Execute a single MCP operation with caching."""
        key = mcp_call_key(operation.server, operation.tool, operation.args)
        
        # Check cache
        if key in self._cache:
            self._cache_stats["hits"] += 1
            return MCPBatchResult(
                operation=operation,
                result=self._cache[key],
                cache_hit=True,
            )
        self._cache_stats["misses"] += 1
        
        # Execute via MCP
        start_time = time.time()
        try:
            # Use the appropriate MCP tool (actual implementation requires MCP stdio connection)
            result = self._call_mcp_tool(operation.server, operation.tool, operation.args)
            duration_ms = (time.time() - start_time) * 1000
            
            # Cache result
            self._cache[key] = result
            
            return MCPBatchResult(
                operation=operation,
                result=result,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            return MCPBatchResult(
                operation=operation,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=duration_ms,
            )
    
    def _call_mcp_tool(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool via the use_mcp_tool pattern."""
        # This is a placeholder — actual implementation would use subprocess/stdio
        # to communicate with the MCP server.
        # For now, return a structured error.
        raise NotImplementedError(
            f"MCP tool call not implemented: {server}:{tool}. "
            "Use the MCPBatchOrchestrator with actual MCP server connections."
        )
    
    def get_stats(self) -> dict[str, Any]:
        """Get batch execution statistics."""
        return {
            "cache": self._cache_stats,
            "failures": self.failure_counter.get_counts(),
            "cache_size": len(self._cache),
        }


# ============================================================================
# Predefined Batch Operations for Common Use Cases
# ============================================================================

def create_code_search_batch(
    patterns: List[str],
    search_server: str = "aicarmine_repo_search_det",
    max_results_per_pattern: int = 50,
) -> List[MCPBatchOperation]:
    """Create parallel ripgrep search operations for multiple patterns.
    
    Example:
        batch = create_code_search_batch(["def \\w+\\(", "class \\w+:", "import \\w+"])
    """
    operations = []
    for idx, pattern in enumerate(patterns):
        operations.append(MCPBatchOperation(
            server=search_server,
            tool="repo_search_rg",
            args={"path": ".", "pattern": pattern, "max_results": max_results_per_pattern},
            operation_id=f"search_{idx}",
        ))
    return operations


def create_symbol_index_batch(
    paths: List[str],
    symbol_server: str = "aicarmine_repo_symbol_index",
) -> List[MCPBatchOperation]:
    """Create parallel symbol index queries for multiple paths.
    
    Example:
        batch = create_symbol_index_batch(["src/module1.py", "src/module2.py"])
    """
    operations = []
    for idx, path in enumerate(paths):
        operations.append(MCPBatchOperation(
            server=symbol_server,
            tool="repo_search_ctags",
            args={"path": path, "limit": 100},
            operation_id=f"symbol_{idx}",
        ))
    return operations


def create_validation_batch(
    paths: List[str],
    validate_server: str = "aicarmine_repo_validate",
) -> List[MCPBatchOperation]:
    """Create parallel linting/type-checking operations.
    
    Example:
        batch = create_validation_batch(["src/module1.py", "tests/test_module1.py"])
    """
    operations = []
    for idx, path in enumerate(paths):
        operations.append(MCPBatchOperation(
            server=validate_server,
            tool="repo_validate_ruff",
            args={"path": path},
            operation_id=f"ruff_{idx}",
        ))
        operations.append(MCPBatchOperation(
            server=validate_server,
            tool="repo_validate_pyright",
            args={"path": path},
            operation_id=f"pyright_{idx}",
        ))
    return operations


def create_git_history_batch(
    revs: List[str],
    git_server: str = "aicarmine_git_readonly",
) -> List[MCPBatchOperation]:
    """Create parallel Git log operations for multiple revisions.
    
    Example:
        batch = create_git_history_batch(["HEAD", "HEAD~1", "main"])
    """
    operations = []
    for idx, rev in enumerate(revs):
        operations.append(MCPBatchOperation(
            server=git_server,
            tool="git_readonly_log",
            args={"rev": rev, "max_count": 20},
            operation_id=f"log_{idx}",
        ))
        operations.append(MCPBatchOperation(
            server=git_server,
            tool="git_readonly_show",
            args={"rev": rev, "include_patch": False},
            operation_id=f"show_{idx}",
        ))
    return operations


# ============================================================================
# Batch Result Aggregation & Reporting
# ============================================================================

def summarize_batch_results(results: List[MCPBatchResult]) -> dict[str, Any]:
    """Summarize batch execution results."""
    total = len(results)
    success = sum(1 for r in results if r.result and not r.error)
    errors = sum(1 for r in results if r.error)
    cache_hits = sum(1 for r in results if r.cache_hit)
    
    avg_duration = (
        sum(r.duration_ms for r in results if r.duration_ms > 0) / max(1, success)
    )
    
    return {
        "total_operations": total,
        "successful": success,
        "errors": errors,
        "cache_hits": cache_hits,
        "error_rate": round(errors / max(1, total), 3),
        "avg_duration_ms": round(avg_duration, 2),
        "results_by_server": _group_by_server(results),
        "results_by_error": _group_by_error(results),
    }


def _group_by_server(results: List[MCPBatchResult]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for r in results:
        server = r.operation.server
        groups[server] = groups.get(server, 0) + 1
    return groups


def _group_by_error(results: List[MCPBatchResult]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for r in results:
        error_type = r.error_type or "none"
        groups[error_type] = groups.get(error_type, 0) + 1
    return groups