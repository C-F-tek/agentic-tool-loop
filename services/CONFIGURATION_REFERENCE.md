# Configuration Reference

Last updated: 2026-08-13

## Overview

This document provides a complete reference for all configuration sources, environment variables, configuration models, and runtime settings across the `services/` directory. The configuration system is built around three layers:

1. **Environment variable loading layer** (`config/env_loader.py`) — parses `os.environ` with type-safe helpers
2. **Configuration model layer** (`config/models.py`) — frozen dataclass `BrokerConfig` with 80+ fields
3. **Compatibility layer** (`config/compatibility.py`) — module-level constants for legacy imports

## Configuration Architecture

```
┌────────────────────────────────────────────────┐
│              os.environ                        │
│         (shell / launch scripts)               │
└───────────────────┬──────────────────────────-─┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│           env_loader.py                         │
│  - env_str()                                    │
│  - env_int(), env_float()                       │
│  - env_bool(), parse_bool()                     │
│  - env_first() — fallback chains                │
│  - env_int_any() — tuple fallback               │
└───────────────────┬───────────────────────────--┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│           models.py                             │
│  BrokerConfig (frozen dataclass)                │
│  load_broker_config_from_env()                  │
└───────────────────┬─────────────────────────--──┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│           compatibility.py                      │
│  BROKER_CONFIG, SERVICE_NAME, APP_TITLE...      │
│  Module-level constants for legacy imports      │
└─────────────────────────────────────────────────┘
```

## Configuration Files

### services/aicarmine_broker/config/

| File | Purpose | Lines |
|------|---------|-------|
| `__init__.py` | Compatibility surface — re-exports all constants from `compatibility.py` for legacy imports like `from aicarmine_broker.config import SERVICE_NAME` | 193 |
| `env_loader.py` | Type-safe environment variable parsing helpers | 176 |
| `models.py` | `BrokerConfig` frozen dataclass + `load_broker_config_from_env()` factory | 297 |
| `compatibility.py` | Module-level constant aliases + `internal_tools_list()`, `ollama_options()` | 145 |

### services/model_export/config.py

Configuration for model export CLI tool (separate from broker config).

### services/npu_phi_service/settings.py

Settings for NPU Phi service (separate runtime configuration).

## Environment Variable Reference

All environment variables are loaded via `BrokerConfig.load_broker_config_from_env()`. Default values are shown.

### Service Metadata

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_BROKER_SERVICE_NAME` | str | `"aicarmine-vulkan-tool-broker"` | Service identifier |
| `AICARMINE_BROKER_APP_TITLE` | str | `"AI-Carmine Vulkan Tool Broker"` | UI display title |
| `AICARMINE_BROKER_APP_VERSION` | str | `"2.0.0"` | Semantic version |
| `AICARMINE_BROKER_APP_DESCRIPTION` | str | Internal broker description | OpenAPI description |
| `AICARMINE_BROKER_VULKAN_AGENT_PATH` | str | `"/vulkan/agent"` | FastAPI route path |
| `AICARMINE_BROKER_JOBS_PATH` | str | `"/jobs"` | Jobs index route |
| `AICARMINE_BROKER_JOBS_JSON_PATH` | str | `"/jobs.json"` | Jobs JSON route |
| `AICARMINE_BROKER_HEALTH_PATH` | str | `"/health"` | Health check route |
| `AICARMINE_BROKER_JOBS_REFRESH_SECONDS` | int | `10` | UI refresh interval |
| `AICARMINE_BROKER_OPENAPI_CONTRACT` | str | Contract string | OpenAPI spec description |

### Runtime Paths

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_REAL_REPO` | Path | `"C:\Users\carmi\ProjectsDir\blender-audio-project"` | Production repository root |
| `AICARMINE_VULKAN_WORKSPACE` | Path | `"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker"` | Vulkan workspace root |
| `AICARMINE_AGENT_JOB_ROOT` | Path | `workspace/agent-jobs` | Agent job artifact directory |
| `AICARMINE_LAB_REPO` | Path | `"C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"` | Lab (development) repository |
| `AICARMINE_AGENT_JOB_DB` | Path | `agent_job_root/agent_jobs.sqlite3` | Agent job SQLite store |
| `AICARMINE_PLANNER_MEMORY_DB` | Path | `real_repo/indexAI/agent_memory/agent_memory.sqlite` | Planner persistent memory DB |
| `AICARMINE_PLANNER_RAG_DB` | Path | `real_repo/output/ai_runtime_memory/rag/rag.sqlite` | Planner RAG index DB |

### Ollama / LLM Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_OLLAMA_TASK_URL` | str | `"http://127.0.0.1:11435/api/chat"` | Ollama task endpoint (fallback: `AICARMINE_VULKAN_BROKER_OLLAMA_URL`) |
| `AICARMINE_OLLAMA_TASK_MODEL` | str | `"mio-qwen-code-6:latest"` | Task model name (fallback: `AICARMINE_VULKAN_BROKER_MODEL`) |
| `AICARMINE_OLLAMA_KEEP_ALIVE` | str | `"24h"` | Model keep-alive duration (fallback: `AICARMINE_VULKAN_KEEP_ALIVE`) |
| `AICARMINE_AGENT_PLANNER_URL` | str | `"http://127.0.0.1:11434/api/chat"` | Planner Ollama endpoint (fallback: `AICARMINE_PLANNER_URL`) |
| `AICARMINE_AGENT_PLANNER_MODEL` | str | `"mio-qwen-code-6:latest"` | Planner model (fallback chain: planner model → ollama planner model) |

### Context Window Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_AGENTIC_PLANNER_NUM_CTX` | int | `262144` | Requested context size |
| `AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP` | int | `262144` | Maximum allowed context size |
| `AICARMINE_AGENTIC_PLANNER_NUM_CTX_EFFECTIVE` | computed | `min(requested, cap)` if cap > 0 else requested | Effective context size |
| `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET` | int | `max(48000, num_ctx_effective)` | Character budget for prompts |
| `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO` | float | `0.85` | Prompt compaction ratio |
| `AICARMINE_AGENTIC_PLANNER_HISTORY_PROMPT_TAIL` | int | `8` | Number of tail history messages to include |
| `AICARMINE_AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS` | int | `360` | Preview character count for prompt previews |

### Planner LLM Parameters

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_AGENTIC_PLANNER_NUM_PREDICT` | int | `-1` | Max tokens to generate (-1 = unlimited) |
| `AICARMINE_AGENTIC_PLANNER_STEP_TIMEOUT` | int | `60` | Seconds per planning step |
| `AICARMINE_AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT` | int | `75` | Timeout for forced planner decisions |
| `AICARMINE_AGENTIC_PLANNER_TEMPERATURE` | float | `0.3` | LLM temperature |
| `AICARMINE_AGENTIC_PLANNER_TOP_K` | int | `20` | Top-K sampling |
| `AICARMINE_AGENTIC_PLANNER_TOP_P` | float | `0.85` | Top-p sampling |
| `AICARMINE_AGENTIC_PLANNER_PRESENCE_PENALTY` | float | `0.0` | Presence penalty |
| `AICARMINE_AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES` | int | `3` | Retries for incomprehensible planner output |

### Agentic Planner Flags

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_AGENTIC_PLANNER_ENABLED` | bool | `True` | Enable agentic planner loop |
| `AICARMINE_AGENTIC_FALLBACK_ONESHOT` | bool | `False` | Fallback to one-shot on planner failure |
| `AICARMINE_AGENTIC_RESULT_COMPACT_CHARS` | int | `25000` | Compact result character limit |
| `AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS` | bool | `True` | Use native MCP tools |
| `AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS` | bool | `True` | Require native tools (no fallback) |
| `AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY` | int | `8` | Max parallel readonly tool calls |

### Agent Job Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_AGENT_DEFAULT_MAX_STEPS` | int | `20` | Default max steps per job |
| `AICARMINE_AGENT_MAX_STEPS` | int | `60` | Absolute max steps per job |
| `AICARMINE_AGENT_RETURN_WAIT_SECONDS` | int | `900` | Wait timeout for background jobs |
| `AICARMINE_AGENT_WAIT_POLL_SECONDS` | float | `1.0` | Poll interval for job status |
| `AICARMINE_AGENT_JOB_MAX_INLINE_EVENTS` | int | `20` | Max inline events in job summary |
| `AICARMINE_AGENT_PUBLIC_SUMMARY_CHARS` | int | `4000` | Public summary character limit |
| `AICARMINE_AGENT_PUBLIC_ANSWER_CHARS` | int | `0` | Public answer character limit (0 = unlimited) |
| `AICARMINE_AGENT_PUBLIC_RESULT_INLINE_CHARS` | int | `25000` | Inline result character limit |
| `AICARMINE_AGENT_APPROVAL_MODE` | str | `"safe_write_lab"` | Approval mode: safe_write_lab, auto, manual |

### Repository Orientation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_ORIENTATION_LANE_MODE` | str | `"legacy"` | Lane mode: legacy, shadow, active |

### RAG Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_PLANNER_MEMORY_RETENTION_DAYS` | int | `2` | Memory record retention days |
| `AICARMINE_PLANNER_INTRINSIC_CONTEXT_MAX_CHARS` | int | `10000` | Intrinsic context max characters |
| `AICARMINE_PLANNER_INTRINSIC_RAG_TOP_K` | int | `6` | Intrinsic RAG top-k results |
| `AICARMINE_PLANNER_INTRINSIC_RAG_CHAR_BUDGET` | int | `2000` | Intrinsic RAG character budget |
| `RAG_RERANKING_ENGINE` | str | `""` | RAG reranking engine identifier |
| `RAG_EXTERNAL_RERANKER_URL` | str | `""` | External reranker URL |
| `RAG_RERANKING_MODEL` | str | `"BAAI/bge-reranker-v2-m3"` | RAG reranker model name |
| `AICARMINE_PLANNER_RAG_RERANK_TIMEOUT_SECONDS` | float | `30.0` | RAG rerank timeout |
| `RAG_EMBEDDING_BATCH_SIZE` | int | `4` | Embedding batch size |

### Tool Execution

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_CODEX_COMMAND_TIMEOUT` | int | `600` | Command execution timeout (seconds) |
| `AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS` | int | `12000` | Max tool result characters (fallback: `AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS`) |
| `AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT` | int | `1024` | Vulkan interpreter max tokens |

### Public API

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AICARMINE_AGENT_PUBLIC_BASE_URL` | str | `"http://127.0.0.1:3572"` | Base URL for public API |

### Internal Marker

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `v6_marker` | str | `"public_x_v6_vulkan_select_dispatcher_execute_deterministic_wrap"` | Protocol version marker |

## Configuration Loading Flow

```python
# 1. Entry point — called at module load time
BROKER_CONFIG = load_broker_config_from_env()

# 2. Inside load_broker_config_from_env():
num_ctx_requested = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX", 262144, env)
num_ctx_cap = env_int("AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP", 262144, env)
num_ctx_effective = min(num_ctx_requested, num_ctx_cap) if num_ctx_cap > 0 else num_ctx_requested

# 3. Path resolution with validation
real_repo = _resolved_path(env_str("AICARMINE_REAL_REPO", default_path, env), "AICARMINE_REAL_REPO")

# 4. Boolean parsing with fallback chains
agentic_planner_enabled = env_bool("AICARMINE_AGENTIC_PLANNER_ENABLED", True, env)

# 5. First-non-empty from tuple
ollama_task_url = env_first(("AICARMINE_OLLAMA_TASK_URL", "AICARMINE_VULKAN_BROKER_OLLAMA_URL"), "http://127.0.0.1:11435/api/chat", env)

# 6. Frozen dataclass construction
BrokerConfig(
    service_name=..., app_title=..., app_version=..., ...
)
```

## Type-Safe Parsing Functions

### env_loader.py Helpers

| Function | Signature | Description |
|----------|-----------|-------------|
| `env_str(name, default, env)` | `str → str` | Returns env value or default |
| `env_first(names, default, env)` | `tuple[str,...] → str` | Returns first non-empty env value from chain |
| `env_int(name, default, env)` | `str → int` | Parses integer with error context |
| `env_int_any(names, default, env)` | `tuple[str,...] → int` | Parses int from first non-empty in chain |
| `env_float(name, default, env)` | `str → float` | Parses float with error context |
| `env_bool(name, default, env)` | `str → bool` | Parses boolean from string/number |
| `parse_bool(value, default)` | `object → bool` | General boolean parser for any type |
| `_env(env)` | `Mapping \| None → Mapping` | Returns `os.environ` or provided mapping |

### Boolean Value Sets

```python
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
```

### Error Context

```python
env_error_context(name, expected=..., value=..., exc=...) → dict[str, Any]
_format_env_error(context) → str
```

Provides structured error information for debugging configuration loading failures.

## Path Resolution

### _resolved_path()

```python
def _resolved_path(value: Any, *, env_name: str) -> Path:
    raw = str(value).strip()
    if not raw:
        raise ValueError(f"{env_name} path must not be empty")
    return Path(raw).resolve(strict=False)
```

Handles permission and OS errors during path resolution with descriptive error messages.

## Lane Mode Normalization

### _normalized_lane_mode()

```python
def _normalized_lane_mode(value: object, *, default: str = "legacy") -> str:
    normalized = str(value).strip().lower()
    if normalized in {"legacy", "shadow", "active"}:
        return normalized
    return default
```

Validates orientation lane mode values. Only `legacy`, `shadow`, `active` are accepted; all others default to `legacy`.

## Compatibility Layer Constants

The `compatibility.py` module exposes module-level constants that mirror `BrokerConfig` fields:

```python
# Service identity
SERVICE_NAME, APP_TITLE, APP_VERSION, APP_DESCRIPTION

# Route paths
VULKAN_AGENT_PATH, JOBS_INDEX_PATH, JOBS_JSON_PATH, HEALTH_PATH

# Ollama
OLLAMA_TASK_URL, OLLAMA_TASK_MODEL, OLLAMA_KEEP_ALIVE

# Planner
PLANNER_URL, PLANNER_MODEL

# Agentic flags
AGENTIC_PLANNER_ENABLED, AGENTIC_FALLBACK_ONESHOT, AGENTIC_RESULT_COMPACT_CHARS

# Context window
AGENTIC_PLANNER_NUM_CTX_REQUESTED, AGENTIC_PLANNER_NUM_CTX_CAP, AGENTIC_PLANNER_NUM_CTX
AGENTIC_PLANNER_PROMPT_CHAR_BUDGET, AGENTIC_PLANNER_PROMPT_COMPACT_RATIO
AGENTIC_PLANNER_HISTORY_PROMPT_TAIL, AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS
AGENTIC_PLANNER_NUM_PREDICT

# Planner timeouts and sampling
AGENTIC_PLANNER_STEP_TIMEOUT, AGENTIC_PLANNER_FORCED_DECISION_TIMEOUT
AGENTIC_PLANNER_TEMPERATURE, AGENTIC_PLANNER_TOP_K, AGENTIC_PLANNER_TOP_P
AGENTIC_PLANNER_PRESENCE_PENALTY, AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES

# Native tools
AGENTIC_PLANNER_NATIVE_TOOLS, AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS
AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY

# Agent job limits
AGENT_DEFAULT_MAX_STEPS, AGENT_MAX_STEPS, AGENT_RETURN_WAIT_SECONDS
AGENT_WAIT_POLL_SECONDS, AGENT_JOB_MAX_INLINE_EVENTS
AGENT_PUBLIC_SUMMARY_CHARS, AGENT_PUBLIC_ANSWER_CHARS, AGENT_PUBLIC_RESULT_INLINE_CHARS

# Repository paths
LAB_REPO, REAL_REPO, WORKSPACE, AGENT_JOB_ROOT, AGENT_JOB_DB
PLANNER_MEMORY_DB, PLANNER_RAG_DB

# RAG
PLANNER_MEMORY_RETENTION_DAYS, PLANNER_INTRINSIC_CONTEXT_MAX_CHARS
PLANNER_INTRINSIC_RAG_TOP_K, PLANNER_INTRINSIC_RAG_CHAR_BUDGET
PLANNER_RAG_RERANKING_ENGINE, PLANNER_RAG_EXTERNAL_RERANKER_URL
PLANNER_RAG_RERANKING_MODEL, PLANNER_RAG_RERANK_TIMEOUT_SECONDS
PLANNER_RAG_EMBEDDING_BATCH_SIZE

# Tool execution
COMMAND_TIMEOUT_SECONDS, MAX_TOOL_RESULT_CHARS

# Protocol marker
V6_MARKER

# Thread safety
AGENT_JOB_BACKGROUND_THREADS (dict), AGENT_JOB_LOCK (threading.RLock)
```

## Launch Script Configuration

### services/launch/env.ps1

Sets environment variables before launching services. Sources the PowerShell profile and configures:
- `AICARMINE_LAB_REPO` — lab repository path
- `AICARMINE_REAL_REPO` — real repository path
- Ollama URLs and model names
- Port configurations for broker (3572), vulkan (3571), reranker (3550)

### services/launch/models-ovms-rerank/config.json

OVMS reranker configuration file for BAAI/bge-reranker-v2-m3 model deployment.

## Module-Level Configuration Imports

Legacy code imports configuration via:
```python
from aicarmine_broker.config import SERVICE_NAME, APP_VERSION, ...
from aicarmine_broker.config import load_broker_config_from_env, BrokerConfig
```

The `__init__.py` re-exports everything from `compatibility.py`, which wraps `BrokerConfig` fields as module-level constants.

## Configuration Validation

### Error Handling

All env parsing functions raise `ValueError` with structured context on failure:
- Type mismatch → `received_type` + `received_preview`
- Empty values → descriptive error with env name
- Path resolution failures → `PermissionError` / `OSError` with path details

### Frozen Dataclass

`BrokerConfig` uses `@dataclass(frozen=True)` ensuring all fields are immutable after construction. This prevents runtime mutation of configuration values.

## Quick Reference: Default Ports

| Service | Port | Config Variable |
|---------|------|-----------------|
| AICarmine Broker | 3572 | N/A (hardcoded in app.py) |
| Vulkan Bridge | 3571 | N/A (hardcoded in vulkan_bridge/app.py) |
| Ollama Task | 11435 | `AICARMINE_OLLAMA_TASK_URL` |
| Ollama Planner | 11434 | `AICARMINE_AGENT_PLANNER_URL` |
| OVMS Reranker | 3550 | `RAG_EXTERNAL_RERANKER_URL` |
| OpenWebUI | 8080 | N/A (hardcoded) |
| Public API | 3572 | `AICARMINE_AGENT_PUBLIC_BASE_URL` |

## Related Documentation

- `services/FLOW_STRUCTURE.md` — System-level flow mapping
- `services/CLASS_REFERENCE.md` — Component-level class documentation
- `services/DIRECTORY_STRUCTURE.md` — Organizational-level directory layout
- `services/MODULE_TECHNICAL_DESCRIPTIONS.md` — Module technical descriptions
- `services/aicarmine_broker/MODULE_REFERENCE.md` — Broker module reference
- `services/codex_bridge/MODULE_REFERENCE.md` — Codex bridge module reference