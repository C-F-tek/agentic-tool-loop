"""
aicarmine_broker.config
=======================
Centralised runtime configuration loaded once from environment variables.
All other modules import from here; no module should read os.environ directly.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from .tool_registry import (
    HELPER_PUBLIC_ALIASES,
    VALID_INTERNAL_TOOLS,
    VALID_INTERNAL_TOOLS_LIST,
    VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN,
    VALID_INTERNAL_TOOLS_PROMPT,
    VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN,
)


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if not text:
        return default
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(value)


def env_bool(name: str, default: bool) -> bool:
    return parse_bool(os.environ.get(name), default)


def _parse_int_env(name: str, value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer; got {value!r}") from exc


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return _parse_int_env(name, value)


def env_int_any(names: tuple[str, ...], default: int) -> int:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return _parse_int_env(name, value)
    return default


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a float; got {value!r}") from exc



# ---------------------------------------------------------------------------
# FastAPI surface metadata / paths
# ---------------------------------------------------------------------------

SERVICE_NAME: str = os.environ.get(
    "AICARMINE_BROKER_SERVICE_NAME", "aicarmine-vulkan-tool-broker"
)
APP_TITLE: str = os.environ.get(
    "AICARMINE_BROKER_APP_TITLE", "AI-Carmine Vulkan Tool Broker"
)
APP_VERSION: str = os.environ.get("AICARMINE_BROKER_APP_VERSION", "2.0.0")
APP_DESCRIPTION: str = os.environ.get(
    "AICARMINE_BROKER_APP_DESCRIPTION",
    "Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan "
    "to select one internal tool L, executes L, then deterministically wraps "
    "the dispatcher result as public X.",
)
VULKAN_AGENT_PATH: str = os.environ.get(
    "AICARMINE_BROKER_VULKAN_AGENT_PATH", "/vulkan/agent"
)
JOBS_INDEX_PATH: str = os.environ.get("AICARMINE_BROKER_JOBS_PATH", "/jobs")
JOBS_JSON_PATH: str = os.environ.get("AICARMINE_BROKER_JOBS_JSON_PATH", "/jobs.json")
HEALTH_PATH: str = os.environ.get("AICARMINE_BROKER_HEALTH_PATH", "/health")
JOBS_REFRESH_SECONDS: int = env_int("AICARMINE_BROKER_JOBS_REFRESH_SECONDS", 10)
OPENAPI_CONTRACT: str = os.environ.get(
    "AICARMINE_BROKER_OPENAPI_CONTRACT",
    "3572: public X from 3571 -> 11435 selects internal L -> "
    "3572 dispatcher executes L -> 3572 deterministic field mapping wraps L "
    "result as public X -> 3572 returns wrapper.",
)
AGENT_APPROVAL_MODE: str = os.environ.get(
    "AICARMINE_AGENT_APPROVAL_MODE", "safe_write_lab"
)
VULKAN_INTERPRETER_NUM_PREDICT: int = env_int(
    "AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT", 1024
)

# ---------------------------------------------------------------------------
# Ollama / model endpoints
# ---------------------------------------------------------------------------

OLLAMA_TASK_URL: str = (
    os.environ.get("AICARMINE_OLLAMA_TASK_URL")
    or os.environ.get("AICARMINE_VULKAN_BROKER_OLLAMA_URL")
    or "http://127.0.0.1:11435/api/chat"
)
OLLAMA_TASK_MODEL: str = (
    os.environ.get("AICARMINE_OLLAMA_TASK_MODEL")
    or os.environ.get("AICARMINE_VULKAN_BROKER_MODEL")
    or "qwen3-task-8k"
)
OLLAMA_KEEP_ALIVE: str = (
    os.environ.get("AICARMINE_OLLAMA_KEEP_ALIVE")
    or os.environ.get("AICARMINE_VULKAN_KEEP_ALIVE")
    or "24h"
)
PLANNER_URL: str = (
    os.environ.get("AICARMINE_AGENT_PLANNER_URL")
    or os.environ.get("AICARMINE_PLANNER_URL")
    or "http://127.0.0.1:11434/api/chat"
)
PLANNER_MODEL: str = (
    os.environ.get("AICARMINE_AGENT_PLANNER_MODEL")
    or os.environ.get("AICARMINE_PLANNER_MODEL")
    or os.environ.get("AICARMINE_OLLAMA_PLANNER_MODEL")
    or "qwen3-coder:30b"
)

# ---------------------------------------------------------------------------
# Agentic planner tuning
# ---------------------------------------------------------------------------

AGENTIC_PLANNER_ENABLED: bool = env_bool("AICARMINE_AGENTIC_PLANNER_ENABLED", True)
AGENTIC_FALLBACK_ONESHOT: bool = env_bool("AICARMINE_AGENTIC_FALLBACK_ONESHOT", False)
AGENTIC_RESULT_COMPACT_CHARS: int = env_int(
    "AICARMINE_AGENTIC_RESULT_COMPACT_CHARS", 12000
)
AGENTIC_PLANNER_NUM_CTX_REQUESTED: int = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX", 14336)
AGENTIC_PLANNER_NUM_CTX_CAP: int = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP", 14336)
AGENTIC_PLANNER_NUM_CTX: int = (
    min(AGENTIC_PLANNER_NUM_CTX_REQUESTED, AGENTIC_PLANNER_NUM_CTX_CAP)
    if AGENTIC_PLANNER_NUM_CTX_CAP > 0
    else AGENTIC_PLANNER_NUM_CTX_REQUESTED
)
AGENTIC_PLANNER_PROMPT_CHAR_BUDGET: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET", 56000
)
AGENTIC_PLANNER_PROMPT_COMPACT_RATIO: float = env_float(
    "AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO", 0.5
)
AGENTIC_PLANNER_HISTORY_PROMPT_TAIL: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_HISTORY_PROMPT_TAIL", 8
)
AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS", 360
)
AGENTIC_PLANNER_NUM_PREDICT: int = env_int("AICARMINE_AGENTIC_PLANNER_NUM_PREDICT", -1)
AGENTIC_PLANNER_STEP_TIMEOUT: int = env_int("AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT", 60)
AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT", 75
)
AGENTIC_PLANNER_TEMPERATURE: float = env_float(
    "AICARMINE_AGENTIC_PLANNER_TEMPERATURE", 0.3
)
AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 3
)
AGENTIC_PLANNER_NATIVE_TOOLS: bool = env_bool(
    "AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS", True
)
AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS: bool = env_bool(
    "AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS", True
)
AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY: int = env_int(
    "AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY", 4
)

# ---------------------------------------------------------------------------
# Agent job runtime
# ---------------------------------------------------------------------------

AGENT_DEFAULT_MAX_STEPS: int = env_int("AICARMINE_AGENT_DEFAULT_MAX_STEPS", 20)
AGENT_MAX_STEPS: int = env_int("AICARMINE_AGENT_MAX_STEPS", 60)
AGENT_RETURN_WAIT_SECONDS: int = env_int("AICARMINE_AGENT_RETURN_WAIT_SECONDS", 900)
AGENT_WAIT_POLL_SECONDS: float = env_float("AICARMINE_AGENT_WAIT_POLL_SECONDS", 1.0)
AGENT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "completed",
        "blocked_needs_attention",
        "blocked_needs_consent",
        "failed",
        "failed_tool_error",
        "failed_planner_error",
        "max_steps_reached",
        "cancelled",
    }
)
AGENT_JOB_MAX_INLINE_EVENTS: int = env_int("AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS", 20)
AGENT_PUBLIC_SUMMARY_CHARS: int = env_int("AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS", 4000)
AGENT_PUBLIC_ANSWER_CHARS: int = env_int("AICARMINE_AGENT_PUBLIC_ANSWER_CHARS", 0)
AGENT_PUBLIC_RESULT_INLINE_CHARS: int = env_int(
    "AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS", 12000
)

# ---------------------------------------------------------------------------
# Repository / workspace paths
# ---------------------------------------------------------------------------

LAB_REPO: Path = Path(
    os.environ.get(
        "AICARMINE_LAB_REPO",
        r"C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab",
    )
).resolve(strict=False)

REAL_REPO: Path = Path(
    os.environ.get(
        "AICARMINE_REAL_REPO",
        r"C:\Users\carmi\ProjectsDir\blender-audio-project",
    )
).resolve(strict=False)

WORKSPACE: Path = Path(
    os.environ.get(
        "AICARMINE_VULKAN_WORKSPACE",
        r"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker",
    )
).resolve(strict=False)

AGENT_JOB_ROOT: Path = Path(
    os.environ.get("AICARMINE_AGENT_JOB_ROOT", str(WORKSPACE / "agent-jobs"))
).resolve(strict=False)

AGENT_JOB_DB: Path = Path(
    os.environ.get(
        "AICARMINE_AGENT_JOB_DB", str(AGENT_JOB_ROOT / "agent_jobs.sqlite3")
    )
).resolve(strict=False)

PLANNER_MEMORY_DB: Path = Path(
    os.environ.get(
        "AICARMINE_PLANNER_MEMORY_DB",
        os.environ.get(
            "AICARMINE_PERSISTENT_MEMORY_DB",
            str(REAL_REPO / "indexAI" / "agent_memory" / "agent_memory.sqlite"),
        ),
    )
).resolve(strict=False)
PLANNER_MEMORY_RETENTION_DAYS: int = env_int(
    "AICARMINE_PLANNER_MEMORY_RETENTION_DAYS", 2
)
PLANNER_RAG_DB: Path = Path(
    os.environ.get(
        "AICARMINE_PLANNER_RAG_DB",
        str(REAL_REPO / "output" / "ai_runtime_memory" / "rag" / "rag.sqlite"),
    )
).resolve(strict=False)
PLANNER_INTRINSIC_CONTEXT_MAX_CHARS: int = env_int(
    "AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS", 5000
)
PLANNER_INTRINSIC_RAG_TOP_K: int = env_int("AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K", 3)
PLANNER_INTRINSIC_RAG_CHAR_BUDGET: int = env_int(
    "AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET", 900
)
PLANNER_RAG_RERANKING_ENGINE: str = os.environ.get("RAG_RERANKING_ENGINE", "").strip()
PLANNER_RAG_EXTERNAL_RERANKER_URL: str = os.environ.get("RAG_EXTERNAL_RERANKER_URL", "").strip()
PLANNER_RAG_RERANKING_MODEL: str = os.environ.get(
    "RAG_RERANKING_MODEL", "BAAI/bge-reranker-v2-m3"
).strip()
PLANNER_RAG_RERANK_TIMEOUT_SECONDS: float = env_float(
    "AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS", 2.0
)
PLANNER_RAG_EMBEDDING_BATCH_SIZE: int = env_int("RAG_EMBEDDING_BATCH_SIZE", 4)

AGENT_PUBLIC_BASE_URL: str = os.environ.get(
    "AICARMINE_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:3572"
)

# ---------------------------------------------------------------------------
# Tool limits / markers
# ---------------------------------------------------------------------------

COMMAND_TIMEOUT_SECONDS: int = env_int("AICARMINE_CODEX_COMMAND_TIMEOUT", 600)
MAX_TOOL_RESULT_CHARS: int = env_int_any(
    ("AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS", "AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS"),
    12000,
)
V6_MARKER: str = (
    "public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap"
)

# Tool registry is owned by aicarmine_broker.tool_registry. Config re-exports
# the derived constants for existing imports.

# ---------------------------------------------------------------------------
# Shared mutable state (background job threads)
# ---------------------------------------------------------------------------

AGENT_JOB_BACKGROUND_THREADS: dict[str, object] = {}  # value: threading.Thread
AGENT_JOB_LOCK: threading.RLock = threading.RLock()


# ---------------------------------------------------------------------------
# Helpers (pure, depend only on config constants)
# ---------------------------------------------------------------------------


def internal_tools_list(exclude_vulkan: bool = False) -> list[str]:
    return (
        VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN
        if exclude_vulkan
        else VALID_INTERNAL_TOOLS_LIST
    )


def internal_tool_prompt(exclude_vulkan: bool = False) -> str:
    return (
        VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN
        if exclude_vulkan
        else VALID_INTERNAL_TOOLS_PROMPT
    )


def ollama_options(num_predict: int | None = None) -> dict:
    options: dict = {
        "temperature": env_float("AICARMINE_VULKAN_TEMPERATURE", 0.1),
        "num_ctx": env_int("AICARMINE_VULKAN_NUM_CTX", 2048),
    }
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    return options
