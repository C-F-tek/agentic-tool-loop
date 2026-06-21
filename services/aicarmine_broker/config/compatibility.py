from __future__ import annotations

import threading

from .env_loader import env_bool, env_float, env_int, env_int_any, env_str, parse_bool
from .models import BrokerConfig, load_broker_config_from_env, DEFAULT_GLOBAL_MODEL, DEFAULT_GLOBAL_TEMPERATURE
from ..tool_registry import (
    COMMAND_EXEC_TOOLS,
    HELPER_PUBLIC_ALIASES,
    PURE_READ_TOOLS,
    STATE_MUTATING_TOOLS,
    VALID_INTERNAL_TOOLS,
    VALID_INTERNAL_TOOLS_LIST,
    VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN,
    VALID_INTERNAL_TOOLS_PROMPT,
    VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN,
    WRITE_GUARDED_TOOLS,
)

__all__ = [
    "BROKER_CONFIG",
    "SERVICE_NAME",
    "APP_TITLE",
    "APP_VERSION",
    "APP_DESCRIPTION",
    "VULKAN_AGENT_PATH",
    "JOBS_INDEX_PATH",
    "JOBS_JSON_PATH",
    "HEALTH_PATH",
    "JOBS_REFRESH_SECONDS",
    "OPENAPI_CONTRACT",
    "AGENT_APPROVAL_MODE",
    "VULKAN_INTERPRETER_NUM_PREDICT",
    "OLLAMA_TASK_URL",
    "OLLAMA_TASK_MODEL",
    "OLLAMA_KEEP_ALIVE",
    "PLANNER_URL",
    "PLANNER_MODEL",
    "GLOBAL_MODEL",
    "GLOBAL_TEMPERATURE",
    "AGENTIC_PLANNER_ENABLED",
    "AGENTIC_FALLBACK_ONESHOT",
    "AGENTIC_RESULT_COMPACT_CHARS",
    "AGENTIC_PLANNER_NUM_CTX_REQUESTED",
    "AGENTIC_PLANNER_NUM_CTX_CAP",
    "AGENTIC_PLANNER_NUM_CTX",
    "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET",
    "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO",
    "AGENTIC_PLANNER_HISTORY_PROMPT_TAIL",
    "AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS",
    "AGENTIC_PLANNER_NUM_PREDICT",
    "AGENTIC_PLANNER_STEP_TIMEOUT",
    "AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT",
    "VULKAN_TEMPERATURE",
    "AGENTIC_PLANNER_TEMPERATURE",
    "AGENTIC_PLANNER_TOP_K",
    "AGENTIC_PLANNER_TOP_P",
    "AGENTIC_PLANNER_PRESENCE_PENALTY",
    "AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES",
    "AGENTIC_PLANNER_NATIVE_TOOLS",
    "AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS",
    "AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY",
    "AICARMINE_ORIENTATION_LANE_MODE",
    "AGENT_DEFAULT_MAX_STEPS",
    "AGENT_MAX_STEPS",
    "AGENT_RETURN_WAIT_SECONDS",
    "AGENT_WAIT_POLL_SECONDS",
    "AGENT_TERMINAL_STATUSES",
    "AGENT_JOB_MAX_INLINE_EVENTS",
    "AGENT_PUBLIC_SUMMARY_CHARS",
    "AGENT_PUBLIC_ANSWER_CHARS",
    "AGENT_PUBLIC_RESULT_INLINE_CHARS",
    "LAB_REPO",
    "REAL_REPO",
    "WORKSPACE",
    "AGENT_JOB_ROOT",
    "AGENT_JOB_DB",
    "PLANNER_MEMORY_DB",
    "PLANNER_MEMORY_RETENTION_DAYS",
    "PLANNER_RAG_DB",
    "PLANNER_INTRINSIC_CONTEXT_MAX_CHARS",
    "PLANNER_INTRINSIC_RAG_TOP_K",
    "PLANNER_INTRINSIC_RAG_CHAR_BUDGET",
    "PLANNER_RAG_RERANKING_ENGINE",
    "PLANNER_RAG_EXTERNAL_RERANKER_URL",
    "PLANNER_RAG_RERANKING_MODEL",
    "PLANNER_RAG_RERANK_TIMEOUT_SECONDS",
    "PLANNER_RAG_EMBEDDING_BATCH_SIZE",
    "AGENT_PUBLIC_BASE_URL",
    "COMMAND_TIMEOUT_SECONDS",
    "MAX_TOOL_RESULT_CHARS",
    "V6_MARKER",
    "AGENT_JOB_BACKGROUND_THREADS",
    "AGENT_JOB_LOCK",
    "internal_tools_list",
    "internal_tool_prompt",
    "ollama_options",
    "env_bool",
    "env_float",
    "env_int",
    "env_int_any",
    "env_str",
    "parse_bool",
    "BrokerConfig",
    "load_broker_config_from_env",
    "DEFAULT_GLOBAL_MODEL",
    "DEFAULT_GLOBAL_TEMPERATURE",
    "COMMAND_EXEC_TOOLS",
    "HELPER_PUBLIC_ALIASES",
    "PURE_READ_TOOLS",
    "STATE_MUTATING_TOOLS",
    "VALID_INTERNAL_TOOLS",
    "VALID_INTERNAL_TOOLS_LIST",
    "VALID_INTERNAL_TOOLS_LIST_EXCLUDING_VULKAN",
    "VALID_INTERNAL_TOOLS_PROMPT",
    "VALID_INTERNAL_TOOLS_PROMPT_EXCLUDING_VULKAN",
    "WRITE_GUARDED_TOOLS",
]


BROKER_CONFIG: BrokerConfig = load_broker_config_from_env()

SERVICE_NAME: str = BROKER_CONFIG.service_name
APP_TITLE: str = BROKER_CONFIG.app_title
APP_VERSION: str = BROKER_CONFIG.app_version
APP_DESCRIPTION: str = BROKER_CONFIG.app_description
VULKAN_AGENT_PATH: str = BROKER_CONFIG.vulkan_agent_path
JOBS_INDEX_PATH: str = BROKER_CONFIG.jobs_index_path
JOBS_JSON_PATH: str = BROKER_CONFIG.jobs_json_path
HEALTH_PATH: str = BROKER_CONFIG.health_path
JOBS_REFRESH_SECONDS: int = BROKER_CONFIG.jobs_refresh_seconds
OPENAPI_CONTRACT: str = BROKER_CONFIG.openapi_contract
AGENT_APPROVAL_MODE: str = BROKER_CONFIG.agent_approval_mode
VULKAN_INTERPRETER_NUM_PREDICT: int = BROKER_CONFIG.vulkan_interpreter_num_predict

OLLAMA_TASK_URL: str = BROKER_CONFIG.ollama_task_url
OLLAMA_TASK_MODEL: str = BROKER_CONFIG.ollama_task_model
OLLAMA_KEEP_ALIVE: str = BROKER_CONFIG.ollama_keep_alive
PLANNER_URL: str = BROKER_CONFIG.planner_url
PLANNER_MODEL: str = BROKER_CONFIG.planner_model
GLOBAL_MODEL: str = DEFAULT_GLOBAL_MODEL
GLOBAL_TEMPERATURE: float = DEFAULT_GLOBAL_TEMPERATURE

AGENTIC_PLANNER_ENABLED: bool = BROKER_CONFIG.agentic_planner_enabled
AGENTIC_FALLBACK_ONESHOT: bool = BROKER_CONFIG.agentic_fallback_oneshot
AGENTIC_RESULT_COMPACT_CHARS: int = BROKER_CONFIG.result_compact_chars
AGENTIC_PLANNER_NUM_CTX_REQUESTED: int = BROKER_CONFIG.num_ctx_requested
AGENTIC_PLANNER_NUM_CTX_CAP: int = BROKER_CONFIG.num_ctx_cap
AGENTIC_PLANNER_NUM_CTX: int = BROKER_CONFIG.num_ctx_effective
AGENTIC_PLANNER_PROMPT_CHAR_BUDGET: int = BROKER_CONFIG.prompt_char_budget
AGENTIC_PLANNER_PROMPT_COMPACT_RATIO: float = BROKER_CONFIG.prompt_compact_ratio
AGENTIC_PLANNER_HISTORY_PROMPT_TAIL: int = BROKER_CONFIG.history_prompt_tail
AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS: int = BROKER_CONFIG.prompt_preview_chars
AGENTIC_PLANNER_NUM_PREDICT: int = BROKER_CONFIG.num_predict
AGENTIC_PLANNER_STEP_TIMEOUT: int = BROKER_CONFIG.planner_step_timeout
AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT: int = BROKER_CONFIG.planner_forced_decision_timeout
VULKAN_TEMPERATURE: str = env_str("AICARMINE_VULKAN_TEMPERATURE", "0.1")

AGENTIC_PLANNER_TEMPERATURE: float = BROKER_CONFIG.planner_temperature
AGENTIC_PLANNER_TOP_K: int = BROKER_CONFIG.planner_top_k
AGENTIC_PLANNER_TOP_P: float = BROKER_CONFIG.planner_top_p
AGENTIC_PLANNER_PRESENCE_PENALTY: float = BROKER_CONFIG.planner_presence_penalty
AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES: int = (
    BROKER_CONFIG.planner_incomprehensible_retries
)
AGENTIC_PLANNER_NATIVE_TOOLS: bool = BROKER_CONFIG.native_tools
AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS: bool = BROKER_CONFIG.require_native_tools
AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY: int = (
    BROKER_CONFIG.native_max_parallel_readonly
)

AICARMINE_ORIENTATION_LANE_MODE: str = (
    BROKER_CONFIG.orientation_lane_mode
)

AGENT_DEFAULT_MAX_STEPS: int = BROKER_CONFIG.agent_default_max_steps
AGENT_MAX_STEPS: int = BROKER_CONFIG.agent_max_steps
AGENT_RETURN_WAIT_SECONDS: int = BROKER_CONFIG.agent_return_wait_seconds
AGENT_WAIT_POLL_SECONDS: float = BROKER_CONFIG.agent_wait_poll_seconds
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
AGENT_JOB_MAX_INLINE_EVENTS: int = BROKER_CONFIG.agent_job_max_inline_events
AGENT_PUBLIC_SUMMARY_CHARS: int = BROKER_CONFIG.agent_public_summary_chars
AGENT_PUBLIC_ANSWER_CHARS: int = BROKER_CONFIG.agent_public_answer_chars
AGENT_PUBLIC_RESULT_INLINE_CHARS: int = BROKER_CONFIG.agent_public_result_inline_chars

LAB_REPO = BROKER_CONFIG.lab_repo
REAL_REPO = BROKER_CONFIG.real_repo
WORKSPACE = BROKER_CONFIG.workspace
AGENT_JOB_ROOT = BROKER_CONFIG.agent_job_root
AGENT_JOB_DB = BROKER_CONFIG.agent_job_db
PLANNER_MEMORY_DB = BROKER_CONFIG.planner_memory_db
PLANNER_MEMORY_RETENTION_DAYS: int = BROKER_CONFIG.planner_memory_retention_days
PLANNER_RAG_DB = BROKER_CONFIG.planner_rag_db
PLANNER_INTRINSIC_CONTEXT_MAX_CHARS: int = BROKER_CONFIG.planner_intrinsic_context_max_chars
PLANNER_INTRINSIC_RAG_TOP_K: int = BROKER_CONFIG.planner_intrinsic_rag_top_k
PLANNER_INTRINSIC_RAG_CHAR_BUDGET: int = BROKER_CONFIG.planner_intrinsic_rag_char_budget
PLANNER_RAG_RERANKING_ENGINE: str = BROKER_CONFIG.planner_rag_reranking_engine
PLANNER_RAG_EXTERNAL_RERANKER_URL: str = (
    BROKER_CONFIG.planner_rag_external_reranker_url
)
PLANNER_RAG_RERANKING_MODEL: str = BROKER_CONFIG.planner_rag_reranking_model
PLANNER_RAG_RERANK_TIMEOUT_SECONDS: float = (
    BROKER_CONFIG.planner_rag_rerank_timeout_seconds
)
PLANNER_RAG_EMBEDDING_BATCH_SIZE: int = BROKER_CONFIG.planner_rag_embedding_batch_size

AGENT_PUBLIC_BASE_URL: str = BROKER_CONFIG.agent_public_base_url
COMMAND_TIMEOUT_SECONDS: int = BROKER_CONFIG.command_timeout_seconds
MAX_TOOL_RESULT_CHARS: int = BROKER_CONFIG.max_tool_result_chars
V6_MARKER: str = BROKER_CONFIG.v6_marker

AGENT_JOB_BACKGROUND_THREADS: dict[str, object] = {}
AGENT_JOB_LOCK: threading.RLock = threading.RLock()


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
        "temperature": float(VULKAN_TEMPERATURE),
        "num_ctx": env_int("AICARMINE_VULKAN_NUM_CTX", 2048),
    }
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    return options
