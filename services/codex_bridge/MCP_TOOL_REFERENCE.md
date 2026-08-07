# MCP Tool Reference — AICarmine Codex Bridge

**Generated**: 2026-06-24  
**Scope**: All MCP servers in `services/codex_bridge/`  
**Total Tools**: ~56 tools across 15 MCP servers

---

## Table of Contents

1. [CLI Tool Infrastructure](#1-cli-tool-infrastructure)
2. [Ruff MCP Server](#2-ruff-mcp-server)
3. [Black MCP Server](#3-black-mcp-server)
4. [Prettier MCP Server](#4-prettier-mcp-server)
5. [Biome MCP Server](#5-biome-mcp-server)
6. [ESLint MCP Server](#6-eslint-mcp-server)
7. [Clang-Format MCP Server](#7-clang-format-mcp-server)
8. [Codex App MCP Server](#8-codex-app-mcp-server)
9. [Shared Infrastructure](#9-shared-infrastructure)

---

## 1. CLI Tool Infrastructure

### `cli_tool_common.py`

Unified CLI tool discovery and execution for all formatting/linting servers.

| Function | Purpose |
|----------|---------|
| `find_cli_tool(name)` | Locate a CLI binary via PATH, AppData/Roaming/npm, or .local/bin |
| `run_cli_command(binary, args, **kwargs)` | Execute CLI command with bounded timeout and capture output |
| `find_tool(name)` | Legacy alias for `find_cli_tool` |
| `run_tool(binary, args, **kwargs)` | Legacy alias for `run_cli_command` |

**Environment Variables**:
- `AICARMINE_MCP_COMPRESSION=1` → Enable bz2 compression for large payloads
- `AICARMINE_MCP_MAX_TEXT_CHARS=100000` → Max text chars in responses
- `AICARMINE_MCP_STDIO_TRANSPORT=content-length` → Use Content-Length framing

---

## 2. Ruff MCP Server

**Server**: `aicarmine_ruff`  
**File**: `services/codex_bridge/ruff_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `check_file` | Lint a Python file with Ruff diagnostics | `file_path` | `fix`, `line_length` (default: 88) |
| `format_file` | Read-only format preview | `file_path` | `line_length` |
| `format_file_write` | Format and write back to disk | `file_path` | `line_length` |
| `format_stdin` | Format code from stdin | `content` | `line_length` |
| `list_rules` | List all Ruff lint rules | — | — |

**Example**:
```json
{
  "method": "tools/call",
  "params": {
    "name": "check_file",
    "arguments": {
      "file_path": "src/main.py",
      "fix": true,
      "line_length": 88
    }
  }
}
```

---

## 3. Black MCP Server

**Server**: `aicarmine_black`  
**File**: `services/codex_bridge/black_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `check_file` | Check if file is formatted by Black | `file_path` | `diff`, `line_length` (default: 88) |
| `format_file` | Read-only format preview | `file_path` | `line_length` |
| `format_file_write` | Format and write back to disk | `file_path` | `line_length` |
| `format_stdin` | Format code from stdin | `content` | `line_length` |

---

## 4. Prettier MCP Server

**Server**: `aicarmine_prettier`  
**File**: `services/codex_bridge/prettier_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `format_file` | Format file with Prettier | `file_path` | `parser`, `tab_width` (default: 2) |
| `format_file_write` | Format and write back to disk | `file_path` | `parser`, `tab_width` |
| `format_stdin` | Format code from stdin | `content` | `parser`, `tab_width` |
| `list_supported_parsers` | List all supported parsers | — | — |

**Parsers**: `babel`, `typescript`, `flow`, `json`, `yaml`, `markdown`, `css`, `html`

---

## 5. Biome MCP Server

**Server**: `aicarmine_biome`  
**File**: `services/codex_bridge/biome_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `format_file` | Format JS/TS/JSON/CSS file | `file_path` | `indent_style` (tab/space), `indent_width` (default: 2) |
| `format_file_write` | Format and write back to disk | `file_path` | `indent_style`, `indent_width` |
| `check_file` | Lint and check for errors | `file_path` | `fix` |
| `format_stdin` | Format JS/TS from stdin | `content` | `indent_style`, `indent_width` |
| `list_supported_file_types` | List supported file types | — | — |

---

## 6. ESLint MCP Server

**Server**: `aicarmine_eslint`  
**File**: `services/codex_bridge/eslint_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `check_file` | Lint JS/TS file with ESLint | `file_path` | `fix`, `quiet` |
| `format_stdin` | Lint code from stdin | `content` | — |
| `list_rules` | List all ESLint rules | — | — |

---

## 7. Clang-Format MCP Server

**Server**: `aicarmine_clang_format`  
**File**: `services/codex_bridge/clang_format_mcp_server.py`

| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `check_file` | Check C/C++/Java/C# formatting | `file_path` | `style` (default: LLVM), `config` |
| `format_file` | Format file (read-only) | `file_path` | `style`, `config` |
| `format_file_write` | Format and write back to disk | `file_path` | `style`, `config` |
| `format_stdin` | Format code from stdin | `content` | `style`, `config` |

---

## 8. Codex App MCP Server

**Server**: `aicarmine-codex-app-mcp`  
**File**: `services/codex_bridge/mcp_server.py`

### Health & Info
| Tool | Description |
|------|-------------|
| `aicarmine_bridge_health` | Local MCP health status |

### Terminal Tools (Read-Only)
| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `terminal_list_files` | File listing | — | `path` (default: "."), `max_results` (200) |
| `terminal_search_files` | File search | `query` | `path`, `max_results` (80) |

### Planner & Memory
| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `planner_scratchpad_write` | Write scratchpad memory | `content` | `key`, `scope` (codex_app) |
| `runtime_sqlite_memory_write` | Write runtime SQLite memory | `content`, `summary` | `kind`, `scope`, `tags` |

### Repository Tools (via Dispatcher)
| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `aicarmine_repo_capabilities` | Repo capability map | — | — |
| `aicarmine_repo_status` | Git/repository status | — | — |
| `aicarmine_repo_tree` | Bounded tree listing | — | `path`, `max_depth` (2), `max_files` (200) |
| `aicarmine_repo_list_files` | File listing under path | — | `path`, `glob`, `max_files` (500) |
| `aicarmine_repo_search` | Repository search | `query` | `path`, `mode` (rg), `max_results` (80) |
| `aicarmine_repo_rg_search` | Ripgrep-style search | `query` | `path`, `max_results` |
| `aicarmine_repo_fd_files` | fd-style file discovery | — | `pattern`, `path`, `max_results` (200) |
| `aicarmine_repo_read` | Read repo files | `path` or `paths` | `max_chars` (20000) |
| `aicarmine_repo_ast_grep_search` | AST grep search | `query` | `path`, `max_results` |
| `aicarmine_repo_ast_grep_dry_run` | AST grep dry-run | `query` | `path` |
| `aicarmine_repo_tree_sitter_parse` | Tree-sitter parse | `path` | — |
| `aicarmine_repo_ctags_symbols` | Ctags symbols | — | `path`, `max_results` (200) |
| `aicarmine_repo_jq_query` | jq query for JSON | `path`, `query` | — |
| `aicarmine_repo_propose_code_edit` | Code edit proposal | `path`, `request` | — |
| `aicarmine_repo_unidiff_validate` | Validate unified diff | `diff` | — |
| `aicarmine_repo_git_apply_check` | Git apply check | `diff` | — |
| `aicarmine_repo_apply_patch` | **Write** old_text/new_text patch | `path`, `old_text`, `new_text` | `max_replacements` (1) |
| `aicarmine_repo_validate` | Run validation | — | `continue_on_failure`, `timeout_seconds` (300) |
| `aicarmine_repo_ruff_check` | Ruff check wrapper | — | `path`, `timeout_seconds` |
| `aicarmine_repo_pyright_check` | Pyright check wrapper | — | `path`, `timeout_seconds` |
| `aicarmine_repo_pytest_run` | Pytest runner wrapper | — | `path`, `timeout_seconds` |
| `aicarmine_repo_shellcheck` | Shellcheck wrapper | — | `path`, `timeout_seconds` |
| `aicarmine_repo_semgrep_scan` | Semgrep scan wrapper | — | `path`, `timeout_seconds` |

### Job Artifacts
| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `aicarmine_jobs_status` | List agent jobs | — | `limit` (50) |
| `aicarmine_job_detail` | Read job artifact | `job_id` | `max_chars` (24000) |

### Memory Tools
| Tool | Description | Required Args | Optional Args |
|------|-------------|---------------|---------------|
| `aicarmine_memory_report` | Read memory SQLite records | — | `query`, `limit`, `operational_db`, `persistent_db` |
| `aicarmine_memory_state_packet` | Build context packet from memory | — | `objective`, `query`, `limit`, `max_memory_chars` |

---

## 9. Shared Infrastructure

### `repo_mcp_common.py`

Shared helpers used across all MCP servers:

| Function | Purpose |
|----------|---------|
| `ok(msg_id, result)` | JSON-RPC 2.0 success response |
| `err(msg_id, code, message, data)` | JSON-RPC 2.0 error response |
| `json_dumps(value, compact=False)` | JSON serialization with ensure_ascii=False |
| `json_compress(value)` | bz2-compressed JSON payload |
| `json_decompress(hex_data)` | Decompress bz2 payload |
| `smart_json_dumps(value, use_compression=None)` | Auto-compress if payload > 10KB |
| `compact_text(value, limit=500)` | Truncate text to limit |
| `tool_content(value, is_error=False)` | MCP tool content wrapper |
| `decompress_tool_text(text)` | Decompress bz2 MCP tool text |
| `log(server_name, message)` | Debug logging to stderr |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AICARMINE_MCP_COMPRESSION` | (unset) | Enable bz2 compression |
| `AICARMINE_MCP_MAX_TEXT_CHARS` | 100000 | Max text chars in responses |
| `AICARMINE_MCP_STDIO_TRANSPORT` | auto | jsonl or content-length |
| `AICARMINE_MCP_DEBUG` | 0 | Enable debug logging |
| `AICARMINE_LAB_REPO` | (cwd) | Repository root for imports |
| `AICARMINE_CODEX_MCP_REPO_ROOT` | (synced) | Codex-specific repo root |

---

## Quick Reference: Tool Categories

### Code Formatting
- **Python**: Ruff, Black
- **JS/TS**: Prettier, Biome, ESLint
- **C/C++**: Clang-Format

### Repository Operations
- **Read**: repo_status, repo_tree, repo_list_files, repo_search, repo_read, repo_fd_files, repo_ast_grep_search, repo_ctags_symbols, repo_jq_query
- **Write**: repo_apply_patch (only write tool exposed)

### Memory & Context
- **SQLite**: memory_report, memory_state_packet
- **Scratchpad**: planner_scratchpad_write, runtime_sqlite_memory_write

### Validation & Analysis
- **Linting**: repo_ruff_check, repo_pyright_check, repo_shellcheck, repo_semgrep_scan
- **Testing**: repo_pytest_run
- **Diff**: repo_unidiff_validate, repo_git_apply_check

---

## Notes

1. All MCP servers use JSON-RPC 2.0 over stdio transport
2. Supported transports: `jsonl` and `content-length`
3. Compression is opt-in via environment variables
4. No HTTP calls or agentic loop in any server
5. Repository operations route through in-process dispatcher (no shell)