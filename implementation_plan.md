# Implementation Plan - Agentic Tool Loop Workspace Simplification Phase 2

## Overview
Continue the workspace rebuild by centralizing planner configuration, extracting Ollama HTTP calls into a dedicated module, consolidating fallback/retry logic, and creating a unified launcher entry point. This addresses the core bug where `native_tools` is hard-coded to `True` somewhere in 4000+ lines of planner code, and fixes potential `UnboundLocalError` issues with response variables.

## Scope
This phase focuses on:
1. Adding `PlannerConfig` to centralized configuration to fix the `native_tools` bug
2. Extracting Ollama HTTP calls into `services/llm/ollama_client.py`
3. Creating `services/llm/fallback.py` for centralized retry/fallback logic
4. Cleaning up `application/planner/turn.py` to use new modules
5. Populating `services/launch/main_launcher.py` with actual service startup logic

## Types

### PlannerConfig Model
```python
@dataclass(frozen=True)
class PlannerConfig:
    """Centralized planner configuration model."""
    model: str = "qwen3.5:9b-coding"
    url: str = "http://127.0.0.1:11434/api/chat"
    native_tools: bool = False  # ← THE SINGLE POINT OF CONTROL
    context_window: int = 262144
    timeout: int = 3600
    max_retries: int = 3
    num_ctx: int = 262144
    prompt_char_budget: int = 48000
    rag_reranking_engine: str = "external"
    rag_fts_candidate_count: int = 80
    rag_reranker_input_count: int = 12
    rag_per_document_cap: int = 2500
    rag_rerank_timeout: float = 30.0
```

### OllamaClient Class
```python
class OllamaClient:
    """Handles all HTTP communication with Ollama endpoints."""
    
    def __init__(self, config: PlannerConfig):
        self.config = config
        self.session = requests.Session()
    
    def chat(self, payload: dict) -> dict:
        """Raw chat call to Ollama, with response always initialized."""
        response = None  # Always initialize
        try:
            response = self._call_ollama(payload)
        except Exception as e:
            logger.error(f"Ollama failed: {e}")
        if response is None:
            return self._empty_response()
        return response
    
    def chat_with_tools(self, payload: dict) -> dict:
        """Chat with native tool calling enabled."""
        ...
    
    def chat_json_text(self, payload: dict) -> dict:
        """Chat without tools, expects JSON as text response."""
        ...
```

### FallbackHandler Class
```python
class FallbackHandler:
    """Centralized retry and fallback logic."""
    
    def __init__(self, client: OllamaClient, config: PlannerConfig):
        self.client = client
        self.config = config
    
    def try_with_fallback(self, payload: dict) -> dict:
        """Try native tools → JSON-text → retry ×3 → block."""
        for attempt in range(self.config.max_retries):
            try:
                result = self._try_native_tools(payload)
                if result:
                    return result
                result = self._try_json_text(payload)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
        return self._block_response()
```

## Files

### New Files to Create
1. **`services/llm/__init__.py`** - LLM module package initialization
2. **`services/llm/ollama_client.py`** - Ollama HTTP client with retry logic
3. **`services/llm/fallback.py`** - Centralized fallback/retry handler

### Existing Files to Modify
1. **`services/config/settings.py`** - Add `PlannerConfig` model and `load_planner_config()` function
2. **`services/config/__init__.py`** - Export `PlannerConfig`, `get_planner_config`
3. **`services/aicarmine_broker/planner.py`** - Replace `os.environ.get("NATIVE_TOOLS", "1")` with `get_planner_config().native_tools`
4. **`services/aicarmine_broker/application/planner/turn.py`** - Import from `services.llm` modules, remove scattered retry logic
5. **`services/launch/main_launcher.py`** - Populate with actual service startup logic using PortManager

### Files to Delete (Optional Cleanup)
- Multiple PowerShell launch scripts can be marked as legacy/deprecated after main_launcher.py is populated

## Functions

### New Functions
1. **`load_planner_config()`** in `services/config/settings.py` - Load planner config from env vars
2. **`get_planner_config()`** in `services/config/__init__.py` - Singleton getter
3. **`OllamaClient.__init__(self, config: PlannerConfig)`** - Initialize HTTP session
4. **`OllamaClient.chat(self, payload: dict) -> dict`** - Main chat method
5. **`OllamaClient._call_ollama(self, payload: dict) -> dict`** - Raw HTTP call
6. **`OllamaClient._empty_response(self) -> dict`** - Default empty response
7. **`FallbackHandler.__init__(self, client, config)`** - Initialize with client and config
8. **`FallbackHandler.try_with_fallback(self, payload: dict) -> dict`** - Main fallback method
9. **`FallbackHandler._try_native_tools(self, payload: dict) -> dict`** - Try native tool calling
10. **`FallbackHandler._try_json_text(self, payload: dict) -> dict`** - Try JSON text mode
11. **`FallbackHandler._block_response(self) -> dict`** - Return blocked response
12. **`MainLauncher.start_all(self)`** - Start all services in order
13. **`MainLauncher.stop_all(self)`** - Stop all services gracefully
14. **`MainLauncher.wait_all_healthy(self)`** - Wait for all ports to be up

### Modified Functions
1. **`planner.py`** - Replace inline HTTP calls with `OllamaClient.chat()`
2. **`turn.py`** - Replace scattered retry logic with `FallbackHandler.try_with_fallback()`
3. **`main_launcher.py`** - Populate service startup methods

## Classes

### New Classes
1. **`PlannerConfig`** in `services/config/settings.py` - Frozen dataclass for planner settings
2. **`OllamaClient`** in `services/llm/ollama_client.py` - HTTP client wrapper
3. **`FallbackHandler`** in `services/llm/fallback.py` - Retry/fallback logic
4. **`ServiceStatus`** in `services/launch/main_launcher.py` - Service status representation

### Modified Classes
1. **`MainLauncher`** in `services/launch/main_launcher.py` - Populate with actual startup logic
2. **`BrokerConfig`** in `services/config/settings.py` - Add planner-related fields if not already present

## Dependencies

### New Dependencies
- `requests` library for HTTP calls (already available in project)
- No new package dependencies required

### Version Changes
- No version changes required
- All modules use existing Python 3.12 environment

## Testing

### Test Requirements
1. **`test_planner_config.py`** - Test PlannerConfig defaults and validation
2. **`test_ollama_client.py`** - Test OllamaClient chat methods with mock HTTP
3. **`test_fallback_handler.py`** - Test fallback retry logic
4. **`test_main_launcher.py`** - Test service startup order

### Validation Strategies
- Verify `native_tools` defaults to `False` in PlannerConfig
- Verify response is always initialized in OllamaClient
- Verify retry count matches config.max_retries
- Verify service startup order: ollama → reranker → broker → agentic_loop

## Implementation Order

1. **Add PlannerConfig to services/config/settings.py** - Fixes native_tools bug at source
2. **Create services/llm/__init__.py and services/llm/ollama_client.py** - Isolate HTTP/Ollama calls
3. **Create services/llm/fallback.py** - Centralize retry ×3 logic
4. **Update application/planner/turn.py** - Remove scattered retry/fallback code
5. **Populate services/launch/main_launcher.py** - Single entry point for all services
6. **Update services/config/__init__.py** - Export new config getters
7. **Update services/aicarmine_broker/planner.py** - Use PlannerConfig instead of os.environ.get
8. **Mark legacy PowerShell scripts as deprecated** - Clean up launch directory

This order ensures:
- Step 1 fixes the native_tools bug at its source
- Step 2 isolates the HTTP call point where UnboundLocalError could occur
- Step 3 centralizes retry logic so no more scattered guards
- Step 4 eliminates duplicated code in turn.py
- Step 5 replaces 4-5 PowerShell scripts with ONE entry point