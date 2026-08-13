from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path

from .env_loader import EnvMapping, env_bool, env_error_context, env_first, env_float, env_int, env_int_any, env_str

@dataclass(frozen=True)
class BrokerConfig:
    """Frozen configuration for the 3572 broker service.

    Contains all runtime settings including service metadata, planner parameters,
    agent job configuration, repository paths, and tool execution constraints.
    """
    service_name: str
    orientation_lane_mode: str
    app_title: str
    app_version: str
    app_description: str
    vulkan_agent_path: str
    jobs_index_path: str
    jobs_json_path: str
    health_path: str
    jobs_refresh_seconds: int
    openapi_contract: str
    agent_approval_mode: str
    vulkan_interpreter_num_predict: int
    ollama_task_url: str
    ollama_task_model: str
    ollama_keep_alive: str
    planner_url: str
    planner_model: str
    agentic_planner_enabled: bool
    agentic_fallback_oneshot: bool
    result_compact_chars: int
    num_ctx_requested: int
    num_ctx_cap: int
    num_ctx_effective: int
    prompt_char_budget: int
    prompt_compact_ratio: float
    history_prompt_tail: int
    prompt_preview_chars: int
    num_predict: int
    planner_step_timeout: int
    planner_forced_decision_timeout: int
    planner_temperature: float
    planner_top_k: int
    planner_top_p: float
    planner_presence_penalty: float
    planner_incomprehensible_retries: int
    native_tools: bool
    require_native_tools: bool
    native_max_parallel_readonly: int
    agent_default_max_steps: int
    agent_max_steps: int
    agent_return_wait_seconds: int
    agent_wait_poll_seconds: float
    agent_job_max_inline_events: int
    agent_public_summary_chars: int
    agent_public_answer_chars: int
    agent_public_result_inline_chars: int
    lab_repo: Path
    real_repo: Path
    workspace: Path
    agent_job_root: Path
    agent_job_db: Path
    planner_memory_db: Path
    planner_memory_retention_days: int
    planner_rag_db: Path
    planner_intrinsic_context_max_chars: int
    planner_intrinsic_rag_top_k: int
    planner_intrinsic_rag_char_budget: int
    planner_rag_reranking_engine: str
    planner_rag_external_reranker_url: str
    planner_rag_reranking_model: str
    planner_rag_rerank_timeout_seconds: float
    planner_rag_embedding_batch_size: int
    agent_public_base_url: str
    command_timeout_seconds: int
    max_tool_result_chars: int
    v6_marker: str

def _normalized_lane_mode(value: object, *, default: str = "legacy") -> str:
    """Normalize lane mode value.
    Contract:
    - valori ammessi: legacy, shadow, active;
    - trim e lowercase;
    - valore assente, vuoto o sconosciuto => legacy;
    - nessuna eccezione per valore sconosciuto;
    - nessun logging;
    - nessun side effect.
    """
    if not isinstance(value, str):
        return default
    normalized = str(value).strip().lower()
    if normalized in {"legacy", "shadow", "active"}:
        return normalized
    return default

def _resolved_path(value: Any, *, env_name: str) -> Path:
    try:
        raw = str(value).strip()
    except Exception as exc:
        context = env_error_context(env_name, expected="filesystem path", value=value, exc=exc)
        raise ValueError(
            f"{env_name} path is not stringifiable; "
            f"received_type={context['received_type']}; error_type={context.get('error_type')}"
        ) from exc
    if not raw:
        raise ValueError(f"{env_name} path must not be empty")
    try:
        return Path(raw).resolve(strict=False)
    except PermissionError as exc:
        raise PermissionError(f"{env_name} permission denied while resolving path {raw!r}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"{env_name} OS error while resolving path {raw!r}: {exc}") from exc

DEFAULT_PLANNER_MODEL = "mio-qwen-code-6:latest"
DEFAULT_PLANNER_NUM_CTX = 262144

def _default_prompt_char_budget(num_ctx_effective: int) -> int:
    try:
        ctx = int(num_ctx_effective)
    except Exception:
        ctx = 0
    if ctx <= 0:
        return 48000
    return max(48000, ctx)

def load_broker_config_from_env(env: EnvMapping | None = None) -> BrokerConfig:
    num_ctx_requested = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX", DEFAULT_PLANNER_NUM_CTX, env)
    num_ctx_cap = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP", DEFAULT_PLANNER_NUM_CTX, env)
    num_ctx_effective = (
        min(num_ctx_requested, num_ctx_cap)
        if num_ctx_cap > 0
        else num_ctx_requested
    )
    real_repo = _resolved_path(
        env_str("AICARMINE_REAL_REPO", r"C:\Users\carmi\ProjectsDir\blender-audio-project", env),
        env_name="AICARMINE_REAL_REPO",
    )
    workspace = _resolved_path(
        env_str(
            "AICARMINE_VULKAN_WORKSPACE",
            r"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker",
            env,
        ),
        env_name="AICARMINE_VULKAN_WORKSPACE",
    )
    agent_job_root = _resolved_path(
        env_str("AICARMINE_AGENT_JOB_ROOT", str(workspace / "agent-jobs"), env),
        env_name="AICARMINE_AGENT_JOB_ROOT",
    )
    return BrokerConfig(
        service_name=env_str("AICARMINE_BROKER_SERVICE_NAME", "aicarmine-vulkan-tool-broker", env),
        app_title=env_str("AICARMINE_BROKER_APP_TITLE", "AI-Carmine Vulkan Tool Broker", env),
        app_version=env_str("AICARMINE_BROKER_APP_VERSION", "2.0.0", env),
        app_description=env_str(
            "AICARMINE_BROKER_APP_DESCRIPTION",
            "Internal 3572 broker. Receives public tool X from 3571, asks 11435/Vulkan "
            "to select one internal tool L, executes L, then deterministically wraps "
            "the dispatcher result as public X.",
            env,
        ),
        vulkan_agent_path=env_str("AICARMINE_BROKER_VULKAN_AGENT_PATH", "/vulkan/agent", env),
        jobs_index_path=env_str("AICARMINE_BROKER_JOBS_PATH", "/jobs", env),
        jobs_json_path=env_str("AICARMINE_BROKER_JOBS_JSON_PATH", "/jobs.json", env),
        health_path=env_str("AICARMINE_BROKER_HEALTH_PATH", "/health", env),
        jobs_refresh_seconds=env_int("AICARMINE_BROKER_JOBS_REFRESH_SECONDS", 10, env),
        openapi_contract=env_str(
            "AICARMINE_BROKER_OPENAPI_CONTRACT",
            "3572: public X from 3571 -> 11435 selects internal L -> "
            "3572 dispatcher executes L -> 3572 deterministic field mapping wraps L "
            "result as public X -> 3572 returns wrapper.",
            env,
        ),
        agent_approval_mode=env_str("AICARMINE_AGENT_APPROVAL_MODE", "safe_write_lab", env),
        vulkan_interpreter_num_predict=env_int("AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT", 1024, env),
        ollama_task_url=env_first(
            ("AICARMINE_OLLAMA_TASK_URL", "AICARMINE_VULKAN_BROKER_OLLAMA_URL"),
            "http://127.0.0.1:11435/api/chat",
            env,
        ),
        ollama_task_model=env_first(
            ("AICARMINE_OLLAMA_TASK_MODEL", "AICARMINE_VULKAN_BROKER_MODEL"),
            "mio-qwen-code-6:latest",
            env,
        ),
        ollama_keep_alive=env_first(
            ("AICARMINE_OLLAMA_KEEP_ALIVE", "AICARMINE_VULKAN_KEEP_ALIVE"),
            "24h",
            env,
        ),
        planner_url=env_first(
            ("AICARMINE_AGENT_PLANNER_URL", "AICARMINE_PLANNER_URL"),
            "http://127.0.0.1:11434/api/chat",
            env,
        ),
        planner_model=env_first(
            (
                "AICARMINE_AGENT_PLANNER_MODEL",
                "AICARMINE_PLANNER_MODEL",
                "AICARMINE_OLLAMA_PLANNER_MODEL",
            ),
            DEFAULT_PLANNER_MODEL,
            env,
        ),
        agentic_planner_enabled=env_bool("AICARMINE_AGENTIC_PLANNER_ENABLED", True, env),
        agentic_fallback_oneshot=env_bool("AICARMINE_AGENTIC_FALLBACK_ONESHOT", False, env),
        result_compact_chars=env_int("AICARMINE_AGENTIC_RESULT_COMPACT_CHARS", 25000, env),
        num_ctx_requested=num_ctx_requested,
        num_ctx_cap=num_ctx_cap,
        num_ctx_effective=num_ctx_effective,
        prompt_char_budget=env_int(
            "AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET",
            _default_prompt_char_budget(num_ctx_effective),
            env,
        ),
        prompt_compact_ratio=env_float("AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO", 0.85, env),
        history_prompt_tail=env_int("AICARMINE_AGENTIC_PLANNER_HISTORY_PROMPT_TAIL", 8, env),
        prompt_preview_chars=env_int("AICARMINE_AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS", 360, env),
        num_predict=env_int("AICARMINE_AGENTIC_PLANNER_NUM_PREDICT", -1, env),
        planner_step_timeout=env_int("AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT", 60, env),
        planner_forced_decision_timeout=env_int("AICARMINE_AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT", 75, env),
        planner_temperature=env_float("AICARMINE_AGENTIC_PLANNER_TEMPERATURE", 0.3, env),
        planner_top_k=env_int("AICARMINE_AGENTIC_PLANNER_TOP_K", 20, env),
        planner_top_p=env_float("AICARMINE_AGENTIC_PLANNER_TOP_P", 0.85, env),
        planner_presence_penalty=env_float("AICARMINE_AGENTIC_PLANNER_PRESENCE_PENALTY", 0.0, env),
        planner_incomprehensible_retries=env_int("AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 3, env),
        native_tools=env_bool("AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS", True, env),
        require_native_tools=env_bool("AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS", True, env),
        native_max_parallel_readonly=env_int("AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY", 8, env),
        agent_default_max_steps=env_int("AICARMINE_AGENT_DEFAULT_MAX_STEPS", 20, env),
        agent_max_steps=env_int("AICARMINE_AGENT_MAX_STEPS", 60, env),
        agent_return_wait_seconds=env_int("AICARMINE_AGENT_RETURN_WAIT_SECONDS", 900, env),
        agent_wait_poll_seconds=env_float("AICARMINE_AGENT_WAIT_POLL_SECONDS", 1.0, env),
        agent_job_max_inline_events=env_int("AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS", 20, env),
        agent_public_summary_chars=env_int("AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS", 4000, env),
        agent_public_answer_chars=env_int("AICARMINE_AGENT_PUBLIC_ANSWER_CHARS", 0, env),
        agent_public_result_inline_chars=env_int("AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS", 25000, env),
        lab_repo=_resolved_path(
            env_str(
                "AICARMINE_LAB_REPO",
                r"C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab",
                env,
            ),
            env_name="AICARMINE_LAB_REPO",
        ),
        real_repo=real_repo,
        workspace=workspace,
        agent_job_root=agent_job_root,
        agent_job_db=_resolved_path(
            env_str("AICARMINE_AGENT_JOB_DB", str(agent_job_root / "agent_jobs.sqlite3"), env),
            env_name="AICARMINE_AGENT_JOB_DB",
        ),
        planner_memory_db=_resolved_path(
            env_first(
                ("AICARMINE_PLANNER_MEMORY_DB", "AICARMINE_PERSISTENT_MEMORY_DB"),
                str(real_repo / "indexAI" / "agent_memory" / "agent_memory.sqlite"),
                env,
            ),
            env_name="AICARMINE_PLANNER_MEMORY_DB",
        ),
        planner_memory_retention_days=env_int("AICARMINE_PLANNER_MEMORY_RETENTION_DAYS", 2, env),
        planner_rag_db=_resolved_path(
            env_str(
                "AICARMINE_PLANNER_RAG_DB",
                str(real_repo / "output" / "ai_runtime_memory" / "rag" / "rag.sqlite"),
                env,
            ),
            env_name="AICARMINE_PLANNER_RAG_DB",
        ),
        planner_intrinsic_context_max_chars=env_int("AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS", 10000, env),
        planner_intrinsic_rag_top_k=env_int("AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K", 6, env),
        planner_intrinsic_rag_char_budget=env_int("AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET", 2000, env),
        planner_rag_reranking_engine=env_str("RAG_RERANKING_ENGINE", "", env).strip(),
        planner_rag_external_reranker_url=env_str("RAG_EXTERNAL_RERANKER_URL", "", env).strip(),
        planner_rag_reranking_model=env_str("RAG_RERANKING_MODEL", "BAAI/bge-reranker-v2-m3", env).strip(),
        planner_rag_rerank_timeout_seconds=env_float("AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS", 30.0, env),
        planner_rag_embedding_batch_size=env_int("RAG_EMBEDDING_BATCH_SIZE", 4, env),
        agent_public_base_url=env_str("AICARMINE_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:3572", env),
        command_timeout_seconds=env_int("AICARMINE_CODEX_COMMAND_TIMEOUT", 600, env),
        max_tool_result_chars=env_int_any(
            ("AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS", "AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS"),
            12000,
            env,
        ),
        v6_marker="public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap",
        orientation_lane_mode=_normalized_lane_mode(
            env_str(
                "AICARMINE_ORIENTATION_LANE_MODE",
                "legacy",
                env,
            ),
        ),
    )