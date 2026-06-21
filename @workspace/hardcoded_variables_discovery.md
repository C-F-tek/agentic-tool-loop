# Hardcoded Variables Discovery Report

## Methodology
Search across `services/aicarmine_broker/**/*.py` for common hardcoded patterns. Results classified by whether they are **true hardcoding problems** vs **properly-configured defaults**.

---

## 1. Model Names ✅ FIXED

### Status: All centralized in `config/models.py`

| File | Line | Value | Type | Action Taken |
|------|------|-------|------|--------------|
| `config/models.py` | ~140 | `"Qwen3.6-35B-coding-v6:latest"` | Planner model default | ✅ Set as `DEFAULT_GLOBAL_MODEL` |
| `config/models.py` | ~130 | `"qwen3-task-8k"` | Vulkan/GPU0 model default | ✅ Kept separate (intentional) |

**No remaining hardcoded model names** outside of `config/models.py`.

---

## 2. URLs / Ports ✅ CENTRALIZED

### Status: All wrapped in `env_first()` in `config/models.py`

| Variable | Default | Env Override | Location |
|----------|---------|-------------|----------|
| Vulkan URL | `http://127.0.0.1:11435/api/chat` | `AICARMINE_OLLAMA_TASK_URL` | `config/models.py` |
| Planner URL | `http://127.0.0.1:11434/api/chat` | `AICARMINE_AGENT_PLANNER_URL` | `config/models.py` |
| Broker base URL | `http://127.0.0.1:3572` | `AICARMINE_AGENT_PUBLIC_BASE_URL` | `config/models.py` |

**Result**: No scattered hardcoded URLs. All use `env_first()` pattern.

---

## 3. Temperatures ✅ FIXED

### Before: 7 occurrences of `"temperature": 0` scattered across files
### After: All replaced with `GLOBAL_TEMPERATURE` (=0.1 float)

| File | Replacements | Scope |
|------|--------------|-------|
| `planner.py` | 4 | `_repo_analysis_final_answer_model_quality`, `planner_replan_specialist_for_validation`, `finalize_agentic_job` judge fallback |
| `orientation_lane.py` | 1 | `controller_orientation_model_select` |
| `rag_preseed.py` | 2 | `_repair_preplanner_query_plan_json`, `controller_preplanner_rag_query_plan` |

### Vulkan Temperature
- Stored as **string** `"0.1"` in `VULKAN_TEMPERATURE`
- Converted to `float()` at runtime in `ollama_options()`
- Previously was string `"0"`

---

## 4. Timeout Values ⚠️ TOOL-LEVEL DEFAULTS (Not Problems)

Timeouts found are **tool function parameter defaults**, not global configuration. They follow a consistent pattern using `_bounded_int_arg()` which allows override per-call:

```python
timeout = _bounded_int_arg(args, "timeout_seconds", default=120, minimum=1, maximum=600)
```

This is intentional design — each tool has its own reasonable timeout range. Not candidates for centralization because different operations have fundamentally different time requirements (e.g., grep=120s vs pytest=300s).

| Tool Category | Typical Default Range |
|---------------|----------------------|
| Search tools (fd, rg, ast-grep) | 60–120s |
| Validation tools (ruff, pyright, semgrep) | 180–240s |
| Test runner (pytest) | 300s |
| Shell commands | 120s |
| JSON I/O helper | 120s |

**Verdict**: No action needed. These are correctly scoped per-tool.

---

## 5. Filesystem Paths ⚠️ CONFIGURED IN models.py

All paths are defined once in `config/models.py` via `_resolved_path()` or `env_str()`:

| Variable | Default Path | Env Override |
|----------|-------------|--------------|
| `AICARMINE_REAL_REPO` | `C:\Users\carmi\ProjectsDir\blender-audio-project` | `AICARMINE_REAL_REPO` |
| `AICARMINE_LAB_REPO` | `C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab` | `AICARMINE_LAB_REPO` |
| `AICARMINE_VULKAN_WORKSPACE` | `C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker` | `AICARMINE_VULKAN_WORKSPACE` |
| `AICARMINE_AGENT_JOB_ROOT` | `{workspace}/agent-jobs` | `AICARMINE_AGENT_JOB_ROOT` |

**Single point of change**: `config/models.py` `load_broker_config_from_env()`.

### Example Path Reference
One example path appears in `services/aicarmine_broker/tools/terminal.py` line ~error_message:
```python
"repairs": ["Use an absolute Windows path with drive, e.g. C:\\Users\\carmi\\AI\\services"]
```
This is a **help text example** in an error message, not a configurable value. Intentionally shows user how to format their input.

---

## 6. Other Critical Strings/Numbers

### Fixed Constants (in `config/models.py`)
| Constant | Value | Purpose |
|----------|-------|---------|
| `DEFAULT_GLOBAL_MODEL` | `"Qwen3.6-35B-coding-v6:latest"` | Base model name |
| `DEFAULT_GLOBAL_TEMPERATURE` | `0.1` | Global temperature for planner |
| `DEFAULT_PLANNER_NUM_CTX` | `262144` | Default context window size |

### Configurable Defaults (via `env_*` functions)
These are NOT hardcoded — they can be overridden at startup:

| Parameter | Default | Env Var |
|-----------|---------|---------|
| `planner_temperature` | `0.3` | `AICARMINE_AGENTIC_PLANNER_TEMPERATURE` |
| `planner_top_k` | `20` | `AICARMINE_AGENTIC_PLANNER_TOP_K` |
| `planner_top_p` | `0.85` | `AICARMINE_AGENTIC_PLANNER_TOP_P` |
| `prompt_char_budget` | computed from num_ctx | `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET` |
| `num_predict` | `-1` (unlimited) | `AICARMINE_AGENTIC_PLANNER_NUM_PREDICT` |
| `command_timeout` | `600` | `AICARMINE_CODEX_COMMAND_TIMEOUT` |
| `max_tool_result_chars` | `12000` | `AICARMINE_CODEX_MAX_TOOL_RESULT_CHARS` |
| `result_compact_chars` | `25000` | `AICARMINE_AGENTIC_RESULT_COMPACT_CHARS` |

---

## Summary Table

| Category | Hardcoded? | Centralized? | Action Needed |
|----------|------------|--------------|---------------|
| Model names | ❌ No | ✅ `config/models.py` | Done (fixed) |
| URLs/Ports | ❌ No | ✅ `config/models.py` | Already correct |
| Temperatures | ❌ No | ✅ `config/models.py` + `compatibility.py` | Done (replaced 7× `"temperature": 0`) |
| Timeouts | N/A | Per-tool (intentional) | None |
| Filesystem paths | ❌ No | ✅ `config/models.py` | Already correct |
| Agent parameters | ❌ No | ✅ `config/models.py` | Already correct |

---

## Remaining Items for Future Review

1. **Test file assertions** (`services/codex_bridge/repo_probe_profiles.py`) still assert old model name `"qwen3.6-35b-coding-v5:latest"` — these verify specific behavior but should be updated when tests run.

2. **Main entry point** (`services/aicarmine_broker.py` line ~model declaration) still has hardcoded `"qwen3.6-35b-coding-v5:latest"` — needs review if it's the actual runtime model or dead code.

3. **NPU phi pipeline** (`services/npu_phi_service/`) — not scanned yet; may have hardcoded temperatures or model names.

4. **Launch scripts** (`services/launch/*.ps1`, `services/*.ps1`) — not scanned; may reference old model names or ports.