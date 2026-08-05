"""Planner configuration."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannerConfig:
    """Immutable planner configuration."""
    model: str
    url: str
    num_ctx: int
    num_predict: int
    temperature: float
    top_k: int
    top_p: float
    presence_penalty: float
    timeout: int
    max_steps: int
    native_tools: bool
    # Prompt budget
    prompt_char_budget: int = 120_000
    compact_ratio: float = 0.45
    preview_chars: int = 8_000
    # History
    history_tail: int = 50
    # Intrinsic context
    intrinsic_max_chars: int = 16_000
    rag_char_budget: int = 8_000
    rag_top_k: int = 10
    rag_db: str = ""
    rag_embedding_batch_size: int = 32
    rag_reranker_url: str = ""
    rag_reranking_engine: str = "ovms"
    rag_reranking_model: str = ""
    rag_rerank_timeout: int = 30
    # Ollama
    ollama_keep_alive: float = -1.0
    ollama_task_model: str = ""
    ollama_task_url: str = ""
    # Limits
    incomprehensible_retries: int = 2
    max_parallel_readonly: int = 4
    step_timeout: int = 120
    agent_default_max_steps: int = 20
    agent_max_steps: int = 40
    # Orientation lane mode
    orientation_lane_mode: str = "shadow"
    # Result compact chars
    result_compact_chars: int = 8000


def get_planner_config() -> PlannerConfig:
    """Load planner configuration from environment/module defaults."""
    from ..config import (
        AGENT_DEFAULT_MAX_STEPS,
        AGENT_MAX_STEPS,
        AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
        AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
        AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
        AGENTIC_PLANNER_NUM_CTX,
        AGENTIC_PLANNER_NUM_CTX_CAP,
        AGENTIC_PLANNER_NUM_CTX_REQUESTED,
        AGENTIC_PLANNER_NUM_PREDICT,
        AGENTIC_PLANNER_PRESENCE_PENALTY,
        AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
        AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
        AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
        AGENTIC_PLANNER_STEP_TIMEOUT,
        AGENTIC_RESULT_COMPACT_CHARS,
        AGENTIC_PLANNER_TEMPERATURE,
        AGENTIC_PLANNER_TOP_K,
        AGENTIC_PLANNER_TOP_P,
        AICARMINE_ORIENTATION_LANE_MODE,
        OLLAMA_KEEP_ALIVE,
        OLLAMA_TASK_MODEL,
        OLLAMA_TASK_URL,
        PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
        PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
        PLANNER_INTRINSIC_RAG_TOP_K,
        PLANNER_MODEL,
        PLANNER_RAG_DB,
        PLANNER_RAG_EMBEDDING_BATCH_SIZE,
        PLANNER_RAG_EXTERNAL_RERANKER_URL,
        PLANNER_RAG_RERANKING_ENGINE,
        PLANNER_RAG_RERANKING_MODEL,
        PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
        PLANNER_URL,
    )

    return PlannerConfig(
        model=PLANNER_MODEL,
        url=PLANNER_URL,
        num_ctx=AGENTIC_PLANNER_NUM_CTX,
        num_predict=AGENTIC_PLANNER_NUM_PREDICT,
        temperature=AGENTIC_PLANNER_TEMPERATURE,
        top_k=AGENTIC_PLANNER_TOP_K,
        top_p=AGENTIC_PLANNER_TOP_P,
        presence_penalty=AGENTIC_PLANNER_PRESENCE_PENALTY,
        timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
        max_steps=AGENT_MAX_STEPS,
        native_tools=True,
        prompt_char_budget=AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
        compact_ratio=AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
        preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
        history_tail=AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
        intrinsic_max_chars=PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
        rag_char_budget=PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
        rag_top_k=PLANNER_INTRINSIC_RAG_TOP_K,
        rag_db=PLANNER_RAG_DB,
        rag_embedding_batch_size=PLANNER_RAG_EMBEDDING_BATCH_SIZE,
        rag_reranker_url=PLANNER_RAG_EXTERNAL_RERANKER_URL,
        rag_reranking_engine=PLANNER_RAG_RERANKING_ENGINE,
        rag_reranking_model=PLANNER_RAG_RERANKING_MODEL,
        rag_rerank_timeout=PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
        ollama_keep_alive=OLLAMA_KEEP_ALIVE,
        ollama_task_model=OLLAMA_TASK_MODEL,
        ollama_task_url=OLLAMA_TASK_URL,
        incomprehensible_retries=AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES,
        max_parallel_readonly=AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY,
        step_timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
        agent_default_max_steps=AGENT_DEFAULT_MAX_STEPS,
        agent_max_steps=AGENT_MAX_STEPS,
        orientation_lane_mode=AICARMINE_ORIENTATION_LANE_MODE,
        result_compact_chars=AGENTIC_RESULT_COMPACT_CHARS,
    )