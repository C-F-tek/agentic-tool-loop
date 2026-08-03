# ia_carmine/context/heap_context_memory_reload context

## Role

`ia_carmine/context/heap_context_memory_reload` prepares the startup context that makes a heap run tool-owned and file-backed instead of chat-memory-backed.

It should run before provider planning so GPU/NPU lanes consume real context, tool inventory, memory state and request/task files.

## Responsibilities

- Load required AI context files.
- Build repository documentation maps.
- Build tool catalog/inventory evidence.
- Load operational/persistent memory summaries.
- Write/search operational scratch memory when required.
- Build transient request context.
- Build semantic code/evidence chunk manifests.
- Produce startup task/context files for the heap runtime.

## Expected artifacts

Typical startup outputs include JSON/Markdown reports such as:

```text
startup_repo_scan_index.json
startup_required_ai_context_files.*
startup_repo_docs_map.*
startup_tool_catalog.*
startup_memory_inventory.*
startup_operational_memory_status.*
startup_operational_memory_search.*
startup_transient_request_context.*
startup_semantic_code_chunks.*
startup_ai_context_pack.*
heap_startup_input_ready_context.md
```

Exact names may vary by profile/run, but the artifact role must remain explicit.

## Canonical command surface

Use through the AI dispatcher:

```powershell
python -m ia_carmine.cli heap_context_memory_reload ...
python -m ia_carmine.cli reconcile_heap_report_with_startup_reload ...
```

## Boundaries

- Startup context is not an apply-ready patch.
- Context file count is not product success.
- A failed partial preload should be reported as degraded, not silently converted into success.
- Runtime output belongs under `output/**` and is not committed unless converted into compact evidence.

## Extension notes

When adding new preload sources, expose them as structured report sections and guardrails. Avoid adding ad-hoc provider prompts that bypass the startup manifest/task file.

Startup reload should prefer the single `startup_repo_scan_index.json` surface for file refs, delta status and top-level partitions. Heavy artifacts may use cache hits only when the scan digest for their dependency family is unchanged; reports must say `cache_hit`, `cache_miss_reason` and `source_run` when applicable.
