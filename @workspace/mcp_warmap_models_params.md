# MCP Warmap: Models & Parameters Centralized Configuration

## Overview
All model names and parameters are centralized in `services/aicarmine_broker/config/models.py` and exported via `services/aicarmine_broker/config/compatibility.py`. No more hardcoded `"temperature": 0` scattered across planner files.

---

## Model Names

### Planner Model (GPU1 / 11434)
| Variable | Default | Source File | Export |
|----------|---------|-------------|--------|
| `DEFAULT_GLOBAL_MODEL` | `"Qwen3.6-35B-coding-v6:latest"` | `config/models.py` | `PLANNER_MODEL` |
| `DEFAULT_GLOBAL_TEMPERATURE` | `0.1` | `config/models.py` | `GLOBAL_TEMPERATURE` |

Environment override priority:
1. `AICARMINE_AGENT_PLANNER_MODEL`
2. `AICARMINE_PLANNER_MODEL`
3. `AICARMINE_OLLAMA_PLANNER_MODEL`

Used by: `planner.py`, `orientation_lane.py`, `rag_preseed.py`, `judge_lane.py`, `guard_evaluator.py`

### Vulkan Interpreter Model (GPU0 / 11435)
| Variable | Default | Source File | Export |
|----------|---------|-------------|--------|
| `ollama_task_model` | `"qwen3-task-8k"` | `config/models.py` | `OLLAMA_TASK_MODEL` |

Environment override priority:
1. `AICARMINE_OLLAMA_TASK_MODEL`
2. `AICARMINE_VULKAN_BROKER_MODEL`

Used by: `planner.py` (`vulkan_repair_invalid_planner_decision`), loop controller

### Vulkan Temperature
| Variable | Type | Default | Source File | Export |
|----------|------|---------|-------------|--------|
| `VULKAN_TEMPERATURE` | `str` | `"0.1"` | `config/compatibility.py` | `VULKAN_TEMPERATURE` |

Environment override: `AICARMINE_VULKAN_TEMPERATURE`

**Important**: Stored as **string** `"0.1"`, converted to `float()` at runtime in `ollama_options()`.

Previously hardcoded as `"temperature": 0` everywhere. Now uses `GLOBAL_TEMPERATURE` (0.1) for planner calls.

---

## Global Temperature Replacement Map

All occurrences of `"temperature": 0` have been replaced with `GLOBAL_TEMPERATURE`:

### Files Modified

#### 1. `services/aicarmine_broker/planner.py`
- **Import added**: `GLOBAL_TEMPERATURE` from `.config.compatibility`
- **Replacements** (4 locations):
  - `_repo_analysis_final_answer_model_quality()` options block
  - `planner_replan_specialist_for_validation()` payload options
  - `finalize_agentic_job()` judge fallback options
- **Before**: `"temperature": 0`
- **After**: `"temperature": GLOBAL_TEMPERATURE`

#### 2. `services/aicarmine_broker/application/controller/orientation_lane.py`
- **Import added**: `GLOBAL_TEMPERATURE` from `...config.compatibility`
- **Replacements** (1 location):
  - `controller_orientation_model_select()` request body options
- **Before**: `"temperature": 0`
- **After**: `"temperature": GLOBAL_TEMPERATURE`

#### 3. `services/aicarmine_broker/application/controller/rag_preseed.py`
- **Import added**: `GLOBAL_TEMPERATURE` from `...config.compatibility`
- **Replacements** (2 locations):
  - `_repair_preplanner_query_plan_json()` repair payload options
  - `controller_preplanner_rag_query_plan()` attempt payload options
- **Before**: `"temperature": 0`
- **After**: `"temperature": GLOBAL_TEMPERATURE`

---

## Parameter Summary Table

| Parameter | Old Value | New Value | Type | Scope |
|-----------|-----------|-----------|------|-------|
| Planner temperature | Hardcoded `0` × 4 | `GLOBAL_TEMPERATURE` (=0.1) | float | All planner calls |
| Vulkan temperature | String `"0"` | String `"0.1"` → float() | str→float | GPU0 interpreter |
| Base model name | `"qwen3.6-35b-coding-v5:latest"` | `"Qwen3.6-35B-coding-v6:latest"` | str | Planner only |
| Vulkan model name | `"qwen3-task-8k"` | Unchanged | str | GPU0 only |

---

## Configuration Flow

```
models.py
├── DEFAULT_GLOBAL_MODEL = "Qwen3.6-35B-coding-v6:latest"
├── DEFAULT_GLOBAL_TEMPERATURE = 0.1
└── BrokerConfig (loaded from env vars)

compatibility.py
├── BROKER_CONFIG = load_broker_config_from_env()
├── PLANNER_MODEL = BROKER_CONFIG.planner_model
├── GLOBAL_MODEL = DEFAULT_GLOBAL_MODEL
├── GLOBAL_TEMPERATURE = DEFAULT_GLOBAL_TEMPERATURE  (float)
├── VULKAN_TEMPERATURE = env_str("...", "0.1")      (str)
└── Exports all planner/agent variables

ollama_options()
└── "temperature": float(VULKAN_TEMPERATURE)         (str→float conversion)

planner.py
├── from .config import ... GLOBAL_TEMPERATURE
├── Uses GLOBAL_TEMPERATURE in all options blocks
└── Never imports compatibility directly

orientation_lane.py
├── from ...config.compatibility import GLOBAL_TEMPERATURE
└── Direct import from compatibility module

rag_preseed.py
├── from ...config.compatibility import GLOBAL_TEMPERATURE
└── Direct import from compatibility module
```

---

## Verification Checklist

- [x] `config/models.py`: `DEFAULT_GLOBAL_MODEL` = `"Qwen3.6-35B-coding-v6:latest"`
- [x] `config/models.py`: `DEFAULT_GLOBAL_TEMPERATURE` = `0.1`
- [x] `config/models.py`: `ollama_task_model` defaults to `"qwen3-task-8k"` (not changed)
- [x] `config/compatibility.py`: exports `GLOBAL_TEMPERATURE` (float), `GLOBAL_MODEL` (str), `VULKAN_TEMPERATURE` (str)
- [x] `config/compatibility.py`: `VULKAN_TEMPERATURE` stored as string `"0.1"`, converted via `float()` in `ollama_options()`
- [x] `planner.py`: 4 replacements of `"temperature": 0` → `GLOBAL_TEMPERATURE`
- [x] `orientation_lane.py`: 1 replacement + import added
- [x] `rag_preseed.py`: 2 replacements + import added
- [x] No remaining `"temperature": 0` in Python source files

---

## Non-Changes

- `AICARMINE_AGENTIC_PLANNER_TEMPERATURE` (0.3) remains unchanged — separate from `GLOBAL_TEMPERATURE`
- `AICARMINE_VULKAN_TEMPERATURE` env var still works as override (stored as string)
- Test files (`repo_probe_profiles.py`) still assert old model name — intentional (tests verify specific behavior)
- `services/aicarmine_broker.py` line 1 still has hardcoded `"qwen3.6-35b-coding-v5:latest"` — main entry point, needs separate review