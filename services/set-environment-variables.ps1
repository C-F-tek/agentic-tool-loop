#!/usr/bin/env pwsh
# ============================================================
# AICARMINE / CODEX - Environment Variables Setup
# ============================================================
# This script sets all essential environment variables for
# the agentic-tool-loop workspace. Run it before any broker,
# MCP server, or agentic loop client invocation.
#
# Usage:
#   .\services\set-environment-variables.ps1          # session-only
# ============================================================

# ------------------------------------------------------------------
# 1. Detect repo root if not provided
# ------------------------------------------------------------------
$RepoRoot = $null
if (-not $env:AICARMINE_LAB_REPO) {
    $candidate = Get-Location
    if (Test-Path (Join-Path $candidate ".git")) {
        $RepoRoot = $candidate
    } else {
        $scriptDir = Split-Path (Split-Path $PSScriptRoot -Parent)
        if (Test-Path (Join-Path $scriptDir ".git")) {
            $RepoRoot = $scriptDir
        } else {
            $RepoRoot = "C:\Users\sanit\progeetsbat\agentic-tool-loop"
        }
    }
} else {
    $RepoRoot = $env:AICARMINE_LAB_REPO
}

Write-Host "`n[AICARMINE] Repo root: $RepoRoot" -ForegroundColor Cyan

# ------------------------------------------------------------------
# 2. Compute derived paths
# ------------------------------------------------------------------
$VulkanWorkspace = Join-Path $RepoRoot "state\codex_bridge\agentic_loop_client\port-3579\workspace"
$AgentJobRoot    = Join-Path $VulkanWorkspace "agent-jobs"
$AgentJobDb      = Join-Path $AgentJobRoot "agent_jobs.sqlite3"
$UsefulToolsRoot = Join-Path $RepoRoot "services\useful_tools"
$ProjectMemoryDb = Join-Path $RepoRoot "state\project_memory\project_memory.sqlite3"
$RagDb           = Join-Path $RepoRoot "state\codex_rag\code_rag.sqlite3"
$OperationalMem  = Join-Path $RepoRoot "output\ai_runtime_memory\operational_context.sqlite"
$PersistentMem   = Join-Path $RepoRoot "indexAI\agent_memory\agent_memory.sqlite"

# ------------------------------------------------------------------
# 3. Set environment variables (session scope)
# ------------------------------------------------------------------

# --- Core repository & workspace ---
$env:AICARMINE_LAB_REPO                  = $RepoRoot
$env:AICARMINE_CODEX_MCP_REPO_ROOT       = $RepoRoot
$env:CODEX_WORKSPACE_ROOT                = $RepoRoot
$env:AICARMINE_VULKAN_WORKSPACE          = $VulkanWorkspace
$env:AICARMINE_USEFUL_TOOLS_ROOT         = $UsefulToolsRoot

# --- Agent job paths ---
$env:AICARMINE_AGENT_JOB_ROOT            = $AgentJobRoot
$env:AICARMINE_AGENT_JOB_DB              = $AgentJobDb

# --- Project memory ---
$env:AICARMINE_PROJECT_MEMORY_DB         = $ProjectMemoryDb

# --- SQLite readonly allow roots ---
$env:AICARMINE_SQLITE_READONLY_ALLOW_ROOTS = $RepoRoot

# --- RAG (Retrieval Augmented Generation) ---
$env:AICARMINE_RAG_REPO                  = $RepoRoot
$env:AICARMINE_RAG_DB                    = $RagDb
$env:AICARMINE_RAG_INDEX_SOURCE          = "git"
$env:AICARMINE_RAG_INDEX_MODE            = "delta"
$env:AICARMINE_RAG_MAX_TOTAL_CHARS       = 50000
$env:AICARMINE_RAG_RERANK_URL            = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_RAG_RERANK_READY_URL      = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
$env:AICARMINE_RAG_RERANK_MODEL          = "BAAI/bge-reranker-v2-m3"
$env:AICARMINE_RAG_RERANK_CANDIDATE_LIMIT = 12
$env:AICARMINE_RAG_RERANK_DOC_CHARS      = 2500
$env:AICARMINE_RAG_RERANK_TIMEOUT_SECONDS = 30

# --- MCP transport & debug ---
$env:AICARMINE_MCP_MAX_TEXT_CHARS        = 24000
$env:AICARMINE_MCP_RESOURCE_MAX_CHARS    = 120000
$env:AICARMINE_MCP_DEBUG                 = "0"
$env:AICARMINE_MCP_STDIO_TRANSPORT       = "content-length"
$env:AICARMINE_REPO_MCP_MAX_TEXT_CHARS   = 24000
$env:AICARMINE_REPO_MCP_STDIO_TRANSPORT  = "content-length"
$env:AICARMINE_REPO_MCP_DEBUG            = "0"
$env:AICARMINE_RAG_MCP_DEBUG             = "0"
$env:AICARMINE_RAG_MCP_STDIO_TRANSPORT   = "content-length"

# --- Agentic loop client ---
$env:AICARMINE_AGENTIC_LOOP_CLIENT_PORT     = 3579
$env:AICARMINE_AGENTIC_LOOP_CLIENT_URL      = "http://127.0.0.1:3579/vulkan/agent"
$env:AICARMINE_AGENTIC_LOOP_CLIENT_HEALTH_URL = "http://127.0.0.1:3579/health"
$env:AICARMINE_CONTROLLER_RAG_RERANK_URL    = $env:AICARMINE_RAG_RERANK_URL
$env:AICARMINE_LABTOOLS_PYTHON              = ""

# --- Operational & persistent memory ---
$env:AICARMINE_OPERATIONAL_MEMORY_DB   = $OperationalMem
$env:AICARMINE_PERSISTENT_MEMORY_DB    = $PersistentMem

# --- Codex bridge / Ollama ---
$env:AICARMINE_OLLAMA_BASE_URL              = "http://127.0.0.1:11434"
$env:AICARMINE_CODEX_BRIDGE_STATEFUL        = "0"
$env:AICARMINE_CODEX_BRIDGE_HTTP_TIMEOUT_SECONDS = 900

# --- Broker ---
$env:AICARMINE_REAL_REPO               = $RepoRoot
$env:AICARMINE_BROKER_SERVICE_NAME     = "aicarmine-codex-agentic-loop-3579"
$env:AICARMINE_BROKER_APP_TITLE        = "AI-Carmine Codex Agentic Loop 3579"
$env:AICARMINE_BROKER_UVICORN_RELOAD   = "1"

# --- Open terminal ---
$env:OPEN_TERMINAL_CWD                 = $RepoRoot
$env:AICARMINE_OPEN_TERMINAL_WORKDIR   = $RepoRoot

# --- Model configuration ---
$env:AICARMINE_OLLAMA_TASK_MODEL       = ""
$env:AICARMINE_VULKAN_BROKER_MODEL     = ""
$env:AICARMINE_AGENT_PLANNER_MODEL     = ""
$env:AICARMINE_PLANNER_MODEL           = ""

# ------------------------------------------------------------------
# 4. Print summary
# ------------------------------------------------------------------
Write-Host "`n[AICARMINE] Environment variables set:" -ForegroundColor Cyan
Write-Host "  AICARMINE_LAB_REPO                  = $env:AICARMINE_LAB_REPO" -ForegroundColor White
Write-Host "  AICARMINE_CODEX_MCP_REPO_ROOT       = $env:AICARMINE_CODEX_MCP_REPO_ROOT" -ForegroundColor White
Write-Host "  AICARMINE_VULKAN_WORKSPACE          = $env:AICARMINE_VULKAN_WORKSPACE" -ForegroundColor White
Write-Host "  AICARMINE_AGENT_JOB_ROOT            = $env:AICARMINE_AGENT_JOB_ROOT" -ForegroundColor White
Write-Host "  AICARMINE_AGENT_JOB_DB              = $env:AICARMINE_AGENT_JOB_DB" -ForegroundColor White
Write-Host "  AICARMINE_PROJECT_MEMORY_DB         = $env:AICARMINE_PROJECT_MEMORY_DB" -ForegroundColor White
Write-Host "  AICARMINE_RAG_DB                    = $env:AICARMINE_RAG_DB" -ForegroundColor White
Write-Host "  AICARMINE_MCP_MAX_TEXT_CHARS        = $env:AICARMINE_MCP_MAX_TEXT_CHARS" -ForegroundColor White

# ------------------------------------------------------------------
# 5. Instructions for permanent setup
# ------------------------------------------------------------------
Write-Host "`n[INSTRUCTIONS] To make these variables permanent in PowerShell:" -ForegroundColor Cyan
Write-Host "`nAdd these lines to your PowerShell profile (~\Documents\PowerShell\Microsoft.PowerShell_profile.ps1):" -ForegroundColor White
Write-Host "" -ForegroundColor Gray
Write-Host "# ---- AICARMINE / CODEX environment variables ----" -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_LAB_REPO                  = "C:\Users\sanit\progeetsbat\agentic-tool-loop"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_CODEX_MCP_REPO_ROOT       = $env:AICARMINE_LAB_REPO' -ForegroundColor DarkGray
Write-Host '$env:CODEX_WORKSPACE_ROOT                = $env:AICARMINE_LAB_REPO' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_VULKAN_WORKSPACE          = "C:\Users\sanit\progeetsbat\agentic-tool-loop\state\codex_bridge\agentic_loop_client\port-3579\workspace"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_AGENT_JOB_ROOT            = "$env:AICARMINE_VULKAN_WORKSPACE\agent-jobs"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_AGENT_JOB_DB              = "$env:AICARMINE_AGENT_JOB_ROOT\agent_jobs.sqlite3"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_PROJECT_MEMORY_DB         = "C:\Users\sanit\progeetsbat\agentic-tool-loop\state\project_memory\project_memory.sqlite3"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_SQLITE_READONLY_ALLOW_ROOTS = "C:\Users\sanit\progeetsbat\agentic-tool-loop"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_RAG_DB                    = "C:\Users\sanit\progeetsbat\agentic-tool-loop\state\codex_rag\code_rag.sqlite3"' -ForegroundColor DarkGray
Write-Host '$env:AICARMINE_MCP_MAX_TEXT_CHARS        = 24000' -ForegroundColor DarkGray
Write-Host "" -ForegroundColor Gray
Write-Host "Then restart PowerShell or run: `$profile" -ForegroundColor White

Write-Host "`n[DONE] Environment ready." -ForegroundColor Green