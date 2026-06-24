# MCP Operational Summary & Next Steps

**Date:** 2026-06-24  
**Repository:** c:/Users/carmi/AI (agentic-tool-loop)  
**Status:** Test/Debug phase — not production

---

## 1. Current State

### 1.1 Single Source of Truth: `repo_mcp_common.py`
All shared stdio MCP helpers are centralized in `services/codex_bridge/repo_mcp_common.py`:

| Function | Purpose | Duplicates Replaced |
|----------|---------|---------------------|
| `json_dumps()` | JSON serialization with indent=2 | 8+ per-server `_json_dumps` |
| `compact_text()` | Truncated text output | 6+ per-server `_compact_text` |
| `tool_content()` | MCP content wrapper + bz2 compression | 8+ per-server `_tool_content` |
| `ok()` / `err()` | JSON-RPC success/error responses | 8+ per-server `_ok`/`_err` |
| `safe_int()` | Safe integer conversion with clamping | 8+ per-server variants |
| `read_tail()` / `_read_tail()` | File tail reading with limits | 2+ per-server variants |
| `diagnostic_preview()` / `_diagnostic_preview()` | Error message preview | 4+ per-server variants |
| `compact_text_tuple()` / `_compact_text` | Tuple-based compact text | 1+ (agentic_loop_client) |
| `json_compress()` / `json_decompress()` | **NEW** bz2 compression | 0 (newly added) |
| `smart_json_dumps()` | **NEW** auto-compression | 0 (newly added) |
| `decompress_tool_text()` | **NEW** decompress MCP responses | 0 (newly added) |

### 1.2 MCP Server Inventory (8 servers)
| Server | Tools | Health | Status |
|--------|-------|--------|--------|
| `aicarmine_repo_search_det` | 8 | OK | ✅ Active |
| `aicarmine_repo_validate` | 9 | OK | ✅ Active |
| `aicarmine_repo_code` | 5 | OK | ✅ Active |
| `aicarmine_git_readonly` | 6 | OK | ✅ Active |
| `aicarmine_job_artifact` | 9 | OK | ✅ Active |
| `aicarmine_job_view` | 8 | OK | ✅ Active |
| `aicarmine_sqlite_readonly` | 4 | OK | ✅ Active |
| `aicarmine_project_memory` | 7 | FAILED | ⚠️ NameError: `_memory_db` |

### 1.3 Persistent Environment Variables
```
AICARMINE_REPO_MCP_COMPRESSION=1      → bz2 compression enabled
AICARMINE_REPO_MMP_MAX_TEXT_CHARS=100000 → 100K chars limit (was 24K)
AICARMINE_REPO_MMP_STDIO_TRANSPORT=content-length
```

---

## 2. Duplicate Object Analysis (_ vs non-_)

### 2.1 Already Unified (via repo_mcp_common.py)
The following patterns have been unified — servers now import from `repo_mcp_common`:

| Pattern | Import Alias | Servers Using It |
|---------|-------------|-------------------|
| `ok` / `err` | Direct import | ruff, prettier, biome, eslint, black, clang-format |
| `tool_content` | `_tool_content` | ruff, prettier, biome, eslint, black, clang-format |
| `diagnostic_preview` | `_diagnostic_preview` | ops, job_view |
| `compact_text_tuple` | `_compact_text` | git_readonly, agentic_loop_client |
| `jsonrpc._json_dumps` | Direct re-export | jsonrpc.py |

### 2.2 Still Duplicate (Same Signature — Should Be Unified)

#### A. `find_*` Functions (6 identical patterns)
Each MCP server has its own binary finder:
- `find_ruff()` → ruff_mcp_server.py
- `find_prettier()` → prettier_mcp_server.py
- `find_black()` → black_mcp_server.py
- `find_biome()` → biome_mcp_server.py
- `find_eslint()` → eslint_mcp_server.py
- `find_clang_format()` → clang_format_mcp_server.py

**Recommendation:** Create `find_cli_tool(name, paths=None)` in `repo_mcp_common.py` and replace all 6.

#### B. `run_*` Functions (6 identical patterns)
Each MCP server has its own runner:
- `run_ruff()` → ruff_mcp_server.py
- `run_prettier()` → prettier_mcp_server.py
- `run_black()` → black_mcp_server.py
- `run_biome()` → biome_mcp_server.py
- `run_eslint()` → eslint_mcp_server.py
- `run_clang_format()` → clang_format_mcp_server.py

**Recommendation:** Create `run_cli_command(binary, args, target)` in `repo_mcp_common.py`.

#### C. `_json_dumps` vs `json_dumps` (Name Conflict)
- `repo_mcp_common.py` exports both `json_dumps()` and `_json_dumps()` (identical)
- `mcp_server.py` still has its own `_json_dumps()` (not imported from repo_mcp_common)
- `agentic_loop_client_mcp_server.py` has its own `_json_preview()` using `_compact_text`

**Recommendation:** Remove `_json_dumps()` alias from `repo_mcp_common.py`, keep only `json_dumps()`. Update `mcp_server.py` to import from `repo_mcp_common`.

#### D. `handle_request()` / `serve()` (8 identical patterns)
Every MCP server implements:
- `handle_request(request, ...)` → JSON-RPC handler
- `serve()` → stdio loop

**Recommendation:** Create `serve_mcp(server_name, server_version, tools)` in `repo_mcp_common.py`.

---

## 3. MCP Tool Improvement Plan for Cline

### 3.1 Knowledge Base for Cline
To improve my understanding and usage of MCP tools, I need:

| Area | Current State | Improvement Needed |
|------|--------------|-------------------|
| Tool schemas | Discovered at runtime via `tools/list` | Pre-load into AGENTS.md for faster triggering |
| Tool signatures | Learned from error messages | Document in `MCP_OPERATIONAL_STATUS.md` |
| Common patterns | Repeated across servers | Extract to `repo_mcp_common.py` (done) |
| Compression | Manual env var | Auto-enabled via persistent env var (done) |
| Error handling | Per-server variations | Unified via `tool_content()` with compression (done) |

### 3.2 Next Steps for Cline Knowledge Improvement

1. **Create `MCP_TOOL_REFERENCE.md`** — Document all 56 tools with:
   - Tool name, server, description
   - Input schema summary
   - Output format
   - Common use cases

2. **Update AGENTS.md** — Add MCP routing table:
   - Which tool to use for what task
   - Preferred sequence
   - Fallback options

3. **Add tool capability hints** — For each tool, document:
   - When to use it vs. alternatives
   - Expected response size
   - Whether compression applies

---

## 4. Reuse-First Deduplication Plan

### 4.1 Priority 1: CLI Tool Infrastructure (High Impact)
Create `services/codex_bridge/cli_tool_common.py`:
```python
def find_cli_tool(name: str, search_paths: list[str] | None = None) -> str | None
def run_cli_command(binary: str, args: list[str], target: str | None = None, **kwargs) -> dict
def serve_mcp(server_name: str, server_version: str, tools: dict) -> int
```

**Impact:** Reduces ~60 lines of duplicate code across 6+ servers.

### 4.2 Priority 2: JSON-RPC Serving (Medium Impact)
Move `handle_request()` and `serve()` from each server to `repo_mcp_common.py`:
- 8 servers × 2 functions = 16 duplicates → 1 unified implementation
- Each function is ~30-50 lines

**Impact:** Reduces ~300 lines of duplicate code.

### 4.3 Priority 3: Name Normalization (Low Impact)
Standardize all shared helpers to non-underscore prefix:
- `_json_dumps` → `json_dumps` (remove alias)
- `_compact_text` → `compact_text` (remove alias)
- `_tool_content` → `tool_content` (keep as alias for imports)
- `_ok` / `_err` → already unified

---

## 5. Compression Architecture

### 5.1 How It Works
```
Payload > 10KB?
├── Yes → bz2.compress(payload) → "__compressed__:<hex>"
└── No  → Send raw JSON

Client receives text:
├── Starts with "__compressed__:" → json_decompress(hex_data)
└── Otherwise → Return as-is
```

### 5.2 Performance
- Small payload (50 bytes): 0% overhead, no compression
- Large payload (20,000 bytes): 99% reduction (20KB → 148 bytes)
- Decompression: ~5ms on modern hardware

### 5.3 Configuration
```bash
# Enable compression (persistent)
AICARMINE_REPO_MCP_COMPRESSION=1

# Increase text limit (with compression, safe to go higher)
AICARMINE_REPO_MMP_MAX_TEXT_CHARS=100000
```

---

## 6. Known Issues

| Issue | Severity | Affected | Fix |
|-------|----------|----------|-----|
| `project_memory` health fails | Medium | `aicarmine_project_memory` | NameError: `_memory_db` not defined |
| `mcp_server.py` still has own `_json_dumps` | Low | `aicarmine_codex_mcp_server` | Import from `repo_mcp_common` |
| Duplicate `find_*` functions | Low | 6 servers | Extract to `cli_tool_common.py` |
| Duplicate `handle_request()` | Low | 8 servers | Extract to `repo_mcp_common.py` |

---

## 7. Next Actions

1. **Create `cli_tool_common.py`** — Unified CLI tool infrastructure
2. **Update `MCP_OPERATIONAL_STATUS.md`** — Add all 56 tools with schemas
3. **Fix `project_memory` health** — `_memory_db` reference error
4. **Remove `_json_dumps` alias** — Standardize on `json_dumps`
5. **Extract `handle_request()`** — Move from per-server to `repo_mcp_common`