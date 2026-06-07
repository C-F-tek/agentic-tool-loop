# AI-Carmine Codex App MCP-only launcher/config installer.
# This does NOT start a long-lived MCP service.
# Codex App starts the MCP process on demand through .codex/config.toml.

param(
    [string]$RepoRoot = "C:\Users\carmi\AI",
    [switch]$SkipSelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[codex-app-mcp] $Message" -ForegroundColor Cyan
}

function Escape-TomlString {
    param([string]$Value)
    return ($Value -replace '\\', '\\' -replace '"', '\"')
}

$RepoRoot = (Resolve-Path $RepoRoot).Path
$CodexDir = Join-Path $RepoRoot ".codex"
$ConfigPath = Join-Path $CodexDir "config.toml"
$McpServer = Join-Path $RepoRoot "services\aicarmine_codex_mcp_server.py"
$UsefulTools = Join-Path $RepoRoot "services\useful_tools"

if (-not (Test-Path $McpServer)) {
    throw "MCP wrapper not found: $McpServer"
}

New-Item -ItemType Directory -Force -Path $CodexDir | Out-Null

if (Test-Path $ConfigPath) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $BackupPath = "$ConfigPath.bak-$stamp"
    Copy-Item $ConfigPath $BackupPath
    Write-Info "Backup created: $BackupPath"
}

$RepoRootToml = Escape-TomlString $RepoRoot
$McpServerToml = Escape-TomlString $McpServer
$UsefulToolsToml = Escape-TomlString $UsefulTools

$config = @"
# AI-Carmine Codex App MCP-only config.
# Purpose:
# - expose robust in-repo MCP tools to Codex App
# - avoid 3571 OpenWebUI bridge
# - avoid 3572/vulkan/agent
# - avoid agentic loop, selector and planner lifecycle
# - keep Codex App internal tools untouched

[mcp_servers.aicarmine_tools]
command = "python"
args = ["$McpServerToml"]
cwd = "$RepoRootToml"
enabled = true
required = true
startup_timeout_sec = 20
tool_timeout_sec = 900
default_tools_approval_mode = "prompt"

env = {
  AICARMINE_LAB_REPO = "$RepoRootToml",
  AICARMINE_USEFUL_TOOLS_ROOT = "$UsefulToolsToml",
  AICARMINE_MCP_TOOL_TIMEOUT_SECONDS = "900",
  AICARMINE_MCP_MAX_TEXT_CHARS = "24000"
}

enabled_tools = [
  "aicarmine_bridge_health",
  "aicarmine_repo_capabilities",
  "aicarmine_repo_status",
  "aicarmine_repo_tree",
  "aicarmine_repo_list_files",
  "aicarmine_repo_search",
  "aicarmine_repo_rg_search",
  "aicarmine_repo_fd_files",
  "aicarmine_repo_read",
  "aicarmine_repo_ast_grep_search",
  "aicarmine_repo_ast_grep_dry_run",
  "aicarmine_repo_tree_sitter_parse",
  "aicarmine_repo_ctags_symbols",
  "aicarmine_repo_jq_query",
  "aicarmine_repo_propose_code_edit",
  "aicarmine_repo_unidiff_validate",
  "aicarmine_repo_git_apply_check",
  "aicarmine_repo_apply_patch",
  "aicarmine_repo_validate",
  "aicarmine_repo_ruff_check",
  "aicarmine_repo_pyright_check",
  "aicarmine_repo_pytest_run",
  "aicarmine_repo_shellcheck",
  "aicarmine_repo_semgrep_scan",
  "aicarmine_jobs_status",
  "aicarmine_job_detail",
  "aicarmine_memory_report",
  "aicarmine_memory_state_packet"
]

disabled_tools = [
  "aicarmine_vulkan_helper",
  "aicarmine_repo_command",
  "aicarmine_repo_write_file",
  "terminal_list_files",
  "terminal_search_files",
  "terminal_run_command_wait",
  "runtime_sqlite_memory_write",
  "runtime_sqlite_memory_cleanup",
  "planner_scratchpad_write"
]

[mcp_servers.aicarmine_tools.tools.aicarmine_bridge_health]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_capabilities]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_status]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_tree]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_list_files]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_search]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_rg_search]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_fd_files]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_read]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_ast_grep_search]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_ast_grep_dry_run]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_tree_sitter_parse]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_ctags_symbols]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_jq_query]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_propose_code_edit]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_memory_report]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_memory_state_packet]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_jobs_status]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_job_detail]
approval_mode = "approve"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_unidiff_validate]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_git_apply_check]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_apply_patch]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_validate]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_ruff_check]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_pyright_check]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_pytest_run]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_shellcheck]
approval_mode = "prompt"

[mcp_servers.aicarmine_tools.tools.aicarmine_repo_semgrep_scan]
approval_mode = "prompt"
"@

Set-Content -Path $ConfigPath -Value $config -Encoding UTF8
Write-Info "Wrote: $ConfigPath"
Write-Info "MCP server command configured. Codex App will start it on demand."

if (-not $SkipSelfTest) {
    Write-Info "Running transient MCP self-test..."
    Push-Location $RepoRoot
    try {
        python $McpServer --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "MCP self-test failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    Write-Info "Self-test OK."
}

Write-Info "Done. In Codex App run: /mcp"
