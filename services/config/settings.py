# services/config/settings - Centralized configuration management
#
# This module provides centralized configuration for all services, replacing
# the scattered env parsing in config/compatibility.py and config/models.py.
#
# All services must use these configuration models instead of reading
# environment variables directly.

from __future__ import annotations

import os
from typing import Optional
from pydantic import BaseModel, Field, validator


class BrokerConfig(BaseModel):
    """Broker configuration model.
    
    Replaces config/compatibility.py and config/models.py for broker (3572) settings.
    """
    
    # Ollama planner endpoint
    planner_url: str = Field(default="http://127.0.0.1:11434/api/chat")
    planner_model: str = Field(default="qwen3coder:latest")
    
    # Ollama task/repair endpoint
    ollama_task_url: str = Field(default="http://127.0.0.1:11435/api/chat")
    ollama_task_model: str = Field(default="qwen3coder:latest")
    
    # Agentic loop settings
    agentic_planner_enabled: bool = Field(default=True)
    planner_max_steps: int = Field(default=50)
    planner_timeout_seconds: int = Field(default=300)
    
    # Result limits
    result_max_content_length: int = Field(default=10000)
    result_max_history_entries: int = Field(default=100)
    
    # RAG settings
    rag_reranking_engine: str = Field(default="external")
    rag_fts_candidate_count: int = Field(default=80)
    rag_reranker_input_count: int = Field(default=12)
    rag_per_document_cap: int = Field(default=2500)
    rag_rerank_timeout: float = Field(default=30.0)
    
    # Native tool calling
    planner_native_tools: bool = Field(default=False)
    planner_require_native_tools: bool = Field(default=False)
    
    # Prompt packing
    num_ctx_requested: int = Field(default=262144)
    num_ctx_cap: int = Field(default=262144)
    prompt_char_budget: int = Field(default=48000)
    compaction_threshold_percent: float = Field(default=50.0)
    
    # Repository roots
    lab_repo: str = Field(default=r"C:\Users\sanit\agentic-tool-loop")
    real_repo: Optional[str] = None
    vulkan_workspace: Optional[str] = None
    agent_job_root: Optional[str] = None
    
    # Ports
    broker_port: int = Field(default=3572)
    openwebui_visible_tool_aliases: tuple = Field(default=("vulkan_helper",))
    
    @validator("planner_url", pre=True)
    def validate_planner_url(cls, v):
        """Validate planner URL format."""
        if not v.startswith("http://"):
            raise ValueError("planner_url must start with http://")
        return v
    
    @validator("ollama_task_url", pre=True)
    def validate_ollama_task_url(cls, v):
        """Validate ollama task URL format."""
        if not v.startswith("http://"):
            raise ValueError("ollama_task_url must start with http://")
        return v


class PortConfig(BaseModel):
    """Port configuration model for all services.
    
    Defines the port map for all runtime services.
    """
    
    # Service ports
    ovms_reranker_port: int = Field(default=3550)
    vulkan_bridge_port: int = Field(default=3571)
    broker_port: int = Field(default=3572)
    agentic_loop_client_port: int = Field(default=3579)
    ollama_main_port: int = Field(default=11434)
    ollama_task_port: int = Field(default=11435)
    executor_port: int = Field(default=3560)
    npu_phi_port: int = Field(default=3551)
    openwebui_port: int = Field(default=8080)
    
    # Process types
    ovms_process: str = Field(default="ovms.exe")
    vulkan_process: str = Field(default="uvicorn")
    broker_process: str = Field(default="uvicorn")
    ollama_process: str = Field(default="ollama.exe")
    
    # Default venvs
    labtools_venv: str = Field(default=r"C:\Users\carmi\AI\venvs\labtools")
    openwebui_venv: str = Field(default=r"C:\Users\carmi\AI\venvs\openwebui")
    openvino_venv: str = Field(default=r"C:\Users\carmi\AI\venvs\openvino")


class PlannerConfig(BaseModel):
    """Planner configuration model for Ollama-based planning.
    
    Centralized single point of control for all planner settings.
    Fixes the bug where native_tools was hard-coded to True somewhere in 4000+ lines.
    """
    
    # Ollama planner endpoint
    model: str = Field(default="qwen3.5:9b-coding")
    url: str = Field(default="http://127.0.0.1:11434/api/chat")
    
    # Native tool calling - THE SINGLE POINT OF CONTROL
    native_tools: bool = Field(default=False)
    require_native_tools: bool = Field(default=False)
    
    # Context and prompt settings
    context_window: int = Field(default=262144)
    num_ctx: int = Field(default=262144)
    prompt_char_budget: int = Field(default=48000)
    
    # Timeout and retry
    timeout: int = Field(default=3600)
    max_retries: int = Field(default=3)
    
    # RAG settings
    rag_reranking_engine: str = Field(default="external")
    rag_fts_candidate_count: int = Field(default=80)
    rag_reranker_input_count: int = Field(default=12)
    rag_per_document_cap: int = Field(default=2500)
    rag_rerank_timeout: float = Field(default=30.0)
    
    @validator("url", pre=True)
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith("http://"):
            raise ValueError("url must start with http://")
        return v


def load_planner_config() -> PlannerConfig:
    """Load planner configuration from environment variables.
    
    Reads AICARMINE_AGENTIC_PLANNER_* environment variables and applies defaults.
    Returns a validated PlannerConfig instance.
    """
    config_data = {
        "model": os.getenv("PLANNER_MODEL", "qwen3coder:latest"),
        "url": os.getenv("PLANNER_URL", "http://127.0.0.1:11434/api/chat"),
        "native_tools": os.getenv("AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS", "false").lower() == "true",
        "require_native_tools": os.getenv("AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS", "false").lower() == "true",
        "context_window": int(os.getenv("NUM_CTX_REQUESTED", "262144")),
        "num_ctx": int(os.getenv("NUM_CTX_CAP", "262144")),
        "prompt_char_budget": int(os.getenv("PROMPT_CHAR_BUDGET", "48000")),
        "timeout": int(os.getenv("PLANNER_TIMEOUT_SECONDS", "3600")),
        "max_retries": int(os.getenv("PLANNER_MAX_RETRIES", "3")),
        "rag_reranking_engine": os.getenv("RAG_RERANKING_ENGINE", "external"),
        "rag_fts_candidate_count": int(os.getenv("RAG_FTS_CANDIDATE_COUNT", "80")),
        "rag_reranker_input_count": int(os.getenv("RAG_RERANKER_INPUT_COUNT", "12")),
        "rag_per_document_cap": int(os.getenv("RAG_PER_DOCUMENT_CAP", "2500")),
        "rag_rerank_timeout": float(os.getenv("RAG_RERANK_TIMEOUT", "30.0")),
    }
    
    return PlannerConfig(**config_data)


_planner_config_singleton: PlannerConfig | None = None


def get_planner_config() -> PlannerConfig:
    """Get singleton planner configuration.
    
    Returns a cached PlannerConfig instance loaded from environment variables.
    """
    global _planner_config_singleton
    if _planner_config_singleton is None:
        _planner_config_singleton = load_planner_config()
    return _planner_config_singleton


class McpServerConfig(BaseModel):
    """MCP server configuration model.
    
    Defines MCP server inventory and routing.
    """
    
    # Server categories
    core_infrastructure: list[str] = Field(default=["aicarmine-codex-app", "aicarmine-codex-ops"])
    repository_operations: list[str] = Field(default=[
        "aicarmine-repo-state",
        "aicarmine-repo-search-det",
        "aicarmine-repo-code",
        "aicarmine-repo-validate",
        "aicarmine-git-readonly"
    ])
    runtime_jobs: list[str] = Field(default=[
        "aicarmine-job-artifact",
        "aicarmine-job-view",
        "aicarmine-agentic-loop-client",
        "aicarmine-local-subagent",
        "aicarmine-broker-planner",
        "aicarmine-planner-components"
    ])
    data_memory: list[str] = Field(default=[
        "aicarmine-project-memory",
        "aicarmine-sqlite-readonly",
        "aicarmine-rag",
        "aicarmine-rag-router"
    ])
    model_inference: list[str] = Field(default=[
        "aicarmine-ollama",
        "aicarmine-ovms-reranker"
    ])
    
    # Total tool count
    total_tools: int = Field(default=95)
    server_count: int = Field(default=16)


def load_broker_config() -> BrokerConfig:
    """Load broker configuration from environment variables.
    
    Reads AICARMINE_* environment variables and applies defaults for missing values.
    Returns a validated BrokerConfig instance.
    """
    config_data = {
        "planner_url": os.getenv("PLANNER_URL", "http://127.0.0.1:11434/api/chat"),
        "planner_model": os.getenv("PLANNER_MODEL", "qwen3coder:latest"),
        "ollama_task_url": os.getenv("OLLAMA_TASK_URL", "http://127.0.0.1:11435/api/chat"),
        "ollama_task_model": os.getenv("OLLAMA_TASK_MODEL", "qwen3coder:latest"),
        "agentic_planner_enabled": os.getenv("AGENTIC_PLANNER_ENABLED", "true").lower() == "true",
        "planner_max_steps": int(os.getenv("PLANNER_MAX_STEPS", "50")),
        "planner_timeout_seconds": int(os.getenv("PLANNER_TIMEOUT_SECONDS", "300")),
        "result_max_content_length": int(os.getenv("RESULT_MAX_CONTENT_LENGTH", "10000")),
        "result_max_history_entries": int(os.getenv("RESULT_MAX_HISTORY_ENTRIES", "100")),
        "rag_reranking_engine": os.getenv("RAG_RERANKING_ENGINE", "external"),
        "rag_fts_candidate_count": int(os.getenv("RAG_FTS_CANDIDATE_COUNT", "80")),
        "rag_reranker_input_count": int(os.getenv("RAG_RERANKER_INPUT_COUNT", "12")),
        "rag_per_document_cap": int(os.getenv("RAG_PER_DOCUMENT_CAP", "2500")),
        "rag_rerank_timeout": float(os.getenv("RAG_RERANK_TIMEOUT", "30.0")),
        "planner_native_tools": os.getenv("AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS", "false").lower() == "true",
        "planner_require_native_tools": os.getenv("AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS", "false").lower() == "true",
        "num_ctx_requested": int(os.getenv("NUM_CTX_REQUESTED", "262144")),
        "num_ctx_cap": int(os.getenv("NUM_CTX_CAP", "262144")),
        "prompt_char_budget": int(os.getenv("PROMPT_CHAR_BUDGET", "48000")),
        "compaction_threshold_percent": float(os.getenv("COMPACTION_THRESHOLD_PERCENT", "50.0")),
        "lab_repo": os.getenv("AICARMINE_LAB_REPO", r"C:\Users\sanit\agentic-tool-loop"),
        "real_repo": os.getenv("AICARMINE_REAL_REPO"),
        "vulkan_workspace": os.getenv("AICARMINE_VULKAN_WORKSPACE"),
        "agent_job_root": os.getenv("AICARMINE_AGENT_JOB_ROOT"),
        "broker_port": int(os.getenv("AICARMINE_BROKER_PORT", "3572")),
    }
    
    return BrokerConfig(**config_data)


def load_port_config() -> PortConfig:
    """Load port configuration with default values.
    
    Returns a validated PortConfig instance.
    """
    config_data = {
        "ovms_reranker_port": int(os.getenv("OVMS_RERANKER_PORT", "3550")),
        "vulkan_bridge_port": int(os.getenv("VULKAN_BRIDGE_PORT", "3571")),
        "broker_port": int(os.getenv("BROKER_PORT", "3572")),
        "agentic_loop_client_port": int(os.getenv("AGENTIC_LOOP_CLIENT_PORT", "3579")),
        "ollama_main_port": int(os.getenv("OLLAMA_MAIN_PORT", "11434")),
        "ollama_task_port": int(os.getenv("OLLAMA_TASK_PORT", "11435")),
        "executor_port": int(os.getenv("EXECUTOR_PORT", "3560")),
        "npu_phi_port": int(os.getenv("NPU_PHI_PORT", "3551")),
        "openwebui_port": int(os.getenv("OPENWEBUI_PORT", "8080")),
        "labtools_venv": os.getenv("AICARMINE_LABTOOLS_PYTHON", r"C:\Users\carmi\AI\venvs\labtools"),
        "openwebui_venv": os.getenv("OPENWEBUI_PYTHON", r"C:\Users\carmi\AI\venvs\openwebui"),
        "openvino_venv": os.getenv("OPENVINO_PYTHON", r"C:\Users\carmi\AI\venvs\openvino"),
    }
    
    return PortConfig(**config_data)


def load_mcp_server_config() -> McpServerConfig:
    """Load MCP server configuration with default inventory.
    
    Returns a validated McpServerConfig instance.
    """
    config_data = {
        "core_infrastructure": ["aicarmine-codex-app", "aicarmine-codex-ops"],
        "repository_operations": [
            "aicarmine-repo-state",
            "aicarmine-repo-search-det",
            "aicarmine-repo-code",
            "aicarmine-repo-validate",
            "aicarmine-git-readonly"
        ],
        "runtime_jobs": [
            "aicarmine-job-artifact",
            "aicarmine-job-view",
            "aicarmine-agentic-loop-client",
            "aicarmine-local-subagent",
            "aicarmine-broker-planner",
            "aicarmine-planner-components"
        ],
        "data_memory": [
            "aicarmine-project-memory",
            "aicarmine-sqlite-readonly",
            "aicarmine-rag",
            "aicarmine-rag-router"
        ],
        "model_inference": [
            "aicarmine-ollama",
            "aicarmine-ovms-reranker"
        ],
        "total_tools": 95,
        "server_count": 16,
    }
    
    return McpServerConfig(**config_data)


def get_all_config() -> dict:
    """Load all configuration sections at once.
    
    Returns a dictionary with keys: broker, ports, mcp_servers.
    """
    return {
        "broker": load_broker_config(),
        "ports": load_port_config(),
        "mcp_servers": load_mcp_server_config(),
    }