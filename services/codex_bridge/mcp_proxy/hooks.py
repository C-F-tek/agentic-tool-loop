"""
AICarmine MCP Proxy - Hooks System

Provides hook callbacks for intercepting, modifying, and logging tool calls.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Support both relative and absolute imports
try:
    from .config import DEFAULT_MAX_CALLS_PER_MINUTE
except ImportError:
    _script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(_script_dir))
    from config import DEFAULT_MAX_CALLS_PER_MINUTE

logger = logging.getLogger(__name__)


class HookContext:
    """Context passed to hooks for tool call interception."""

    def __init__(
        self,
        tool_name: str,
        args: Dict[str, Any],
        server_name: str,
        timestamp: Optional[datetime] = None,
        user_id: Optional[str] = None,
        step: Optional[int] = None,
        job_id: Optional[str] = None,
    ):
        self.tool_name = tool_name
        self.args = args
        self.server_name = server_name
        self.timestamp = timestamp or datetime.now()
        self.user_id = user_id
        self.step = step
        self.job_id = job_id

    def __repr__(self) -> str:
        return f"HookContext(tool={self.tool_name}, server={self.server_name})"


class MCPHooks:
    """
    Hook system for MCP proxy.

    Provides three lifecycle hooks:
    - before_tool_call: Executed BEFORE calling the target tool.
      Can return a dict to short-circuit (provide response without calling tool).
    - after_tool_call: Executed AFTER the tool call completes.
      Can modify the returned result.
    - on_error: Executed when a tool call raises an exception.
    """

    def __init__(self):
        self.call_counter: Dict[str, List[datetime]] = {}
        self.max_calls_per_minute: int = 30
        self._enabled: bool = True
        self._after_hooks: List[Any] = []

    def set_rate_limit(self, max_calls: int) -> None:
        """Set the maximum number of calls per minute."""
        self.max_calls_per_minute = max_calls
        logger.info(f"Rate limit set to {max_calls} calls/minute")

    def enable(self) -> None:
        """Enable hooks."""
        self._enabled = True
        logger.info("MCP hooks enabled")

    def disable(self) -> None:
        """Disable hooks."""
        self._enabled = False
        logger.info("MCP hooks disabled")

    def register_after(self, hook_func: Any) -> None:
        """Register an additional after_tool_call hook function."""
        self._after_hooks.append(hook_func)
        logger.info(f"Registered additional after hook: {hook_func.__name__ if hasattr(hook_func, '__name__') else hook_func}")

    async def before_tool_call(self, context: HookContext) -> Optional[Dict[str, Any]]:
        """
        Hook executed BEFORE calling the target tool.

        Returns:
            A dict to short-circuit (provide response without calling tool),
            or None to proceed with normal execution.
        """
        if not self._enabled:
            return None

        # Rate limiting
        user_key = context.user_id or "default"
        if user_key not in self.call_counter:
            self.call_counter[user_key] = []

        # Remove calls older than 60 seconds
        now = datetime.now()
        self.call_counter[user_key] = [
            t for t in self.call_counter[user_key]
            if (now - t).total_seconds() < 60
        ]

        if len(self.call_counter[user_key]) >= self.max_calls_per_minute:
            result = {
                "error": "Rate limit exceeded",
                "message": f"Max {self.max_calls_per_minute} calls per minute",
                "timestamp": now.isoformat(),
            }
            logger.warning(f"Rate limit hit for '{user_key}' on tool '{context.tool_name}'")
            return result

        self.call_counter[user_key].append(now)

        # Log the call
        logger.info(f"🔧 Tool: {context.tool_name} -> Server: {context.server_name}")
        if context.args:
            logger.debug(f"Args keys: {list(context.args.keys())}")

        # Log job context if available
        if context.job_id:
            logger.info(f"Job context: job_id={context.job_id}, step={context.step}")

        return None  # Proceed with execution

    async def after_tool_call(
        self, context: HookContext, result: Any
    ) -> Any:
        """
        Hook executed AFTER the tool call completes.

        Can modify the returned result.
        """
        if not self._enabled:
            return result

        # Add metadata to dict results
        if isinstance(result, dict):
            result["_proxy_meta"] = {
                "tool": context.tool_name,
                "server": context.server_name,
                "timestamp": context.timestamp.isoformat(),
                "duration_ms": (datetime.now() - context.timestamp).total_seconds() * 1000,
            }

        logger.info(f"✅ Tool completed: {context.tool_name}")

        # Run registered additional after hooks
        for hook in self._after_hooks:
            try:
                result = await hook(context, result)
            except Exception as e:
                logger.error(f"After hook error: {e}")

        return result

    async def on_error(
        self, context: HookContext, error: Exception
    ) -> Dict[str, Any]:
        """Hook executed when a tool call raises an exception."""
        if not self._enabled:
            return {
                "error": str(error),
                "tool": context.tool_name,
                "server": context.server_name,
            }

        logger.error(f"❌ Error on {context.tool_name}: {error}")

        error_result = {
            "error": str(error),
            "tool": context.tool_name,
            "server": context.server_name,
            "timestamp": datetime.now().isoformat(),
        }

        # Log traceback details if available
        if hasattr(error, "__traceback__"):
            logger.debug(f"Full error type: {type(error).__name__}")

        return error_result

    def get_call_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get call statistics for rate limiting monitoring."""
        user_key = user_id or "default"
        now = datetime.now()
        recent_calls = [
            t for t in self.call_counter.get(user_key, [])
            if (now - t).total_seconds() < 60
        ]
        return {
            "user_id": user_key,
            "calls_last_minute": len(recent_calls),
            "max_per_minute": self.max_calls_per_minute,
            "remaining": max(0, self.max_calls_per_minute - len(recent_calls)),
        }

    def reset_counters(self) -> None:
        """Reset all call counters."""
        self.call_counter.clear()
        logger.info("Call counters reset")


class TelemetryHook:
    """Telemetry hook for tracking tool usage analytics."""

    def __init__(self, log_file: str = "state/proxy_telemetry.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"TelemetryHook initialized with log file: {self.log_file}")

    async def __call__(self, context: HookContext, result: Dict[str, Any]) -> Dict[str, Any]:
        """Track tool usage and write to telemetry log."""
        try:
            log_entry = {
                "tool": context.tool_name,
                "server": context.server_name,
                "timestamp": context.timestamp.isoformat(),
                "duration_ms": result.get("_proxy_meta", {}).get("duration_ms", 0),
                "success": not result.get("error"),
            }

            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.debug(f"Telemetry logged: {log_entry}")
        except Exception as e:
            logger.error(f"Telemetry write error: {e}")

        return result