#!/usr/bin/env powershell
$ErrorActionPreference = "Continue"

# Set working directory to services/ so repo_mcp_common is directly importable
Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop\services"

# Set PYTHONPATH to include services/codex_bridge (for repo_mcp_common), services/, and repo root
$env:PYTHONPATH = "C:\Users\sanit\progeetsbat\agentic-tool-loop\services\codex_bridge;C:\Users\sanit\progeetsbat\agentic-tool-loop\services;C:\Users\sanit\progeetsbat\agentic-tool-loop"

# Enable debug mode for all MCP servers
$env:AICARMINE_REPO_MCP_DEBUG = "1"
$env:AICARMINE_RAG_MCP_DEBUG = "1"

# Force all models to qwen2.5:7b as per user requirement
$env:AICARMINE_OLLAMA_TASK_MODEL = "qwen2.5:7b"
$env:AICARMINE_VULKAN_BROKER_MODEL = "qwen2.5:7b"
$env:AICARMINE_AGENT_PLANNER_MODEL = "qwen2.5:7b"
$env:AICARMINE_PLANNER_MODEL = "qwen2.5:7b"

# Set environment variables for agentic loop client
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\progeetsbat\agentic-tool-loop"
$env:AICARMINE_REAL_REPO = "C:\Users\sanit\progeetsbat\agentic-tool-loop"
$env:AICARMINE_CODEX_MCP_REPO_ROOT = "C:\Users\sanit\progeetsbat\agentic-tool-loop"

$workspaceDir = "C:\Users\sanit\progeetsbat\agentic-tool-loop\state\codex_bridge\agentic_loop_client\port-3579\workspace"
$jobDir = "$workspaceDir\agent-jobs"
New-Item -ItemType Directory -Force -Path $workspaceDir | Out-Null
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null

$env:AICARMINE_VULKAN_WORKSPACE = $workspaceDir
$env:AICARMINE_AGENT_JOB_ROOT = $jobDir
$env:AICARMINE_AGENT_JOB_DB = "$jobDir\agent_jobs.sqlite3"
$env:AICARMINE_AGENT_PUBLIC_BASE_URL = "http://127.0.0.1:3579"
$env:AICARMINE_VULKAN_AGENT_URL = "http://127.0.0.1:3579/vulkan/agent"
$env:AICARMINE_BROKER_SERVICE_NAME = "aicarmine-codex-agentic-loop-3579"
$env:AICARMINE_BROKER_APP_TITLE = "AI-Carmine Codex Agentic Loop 3579"
$env:AICARMINE_BROKER_UVICORN_RELOAD = "0"

Write-Host "[INFO] Starting Agentic-loop Client MCP Server..." -ForegroundColor Yellow
Write-Host "[INFO] This is a stdio-based MCP server, not HTTP on port 3579." -ForegroundColor Yellow
Write-Host "[INFO] It communicates via stdin/stdout, not a listening port." -ForegroundColor Yellow
Write-Host "[INFO] Running self-test:" -ForegroundColor Yellow

# Run self-test to verify the server works
python -c "import sys; sys.path.insert(0, '.'); from codex_bridge.agentic_loop_client_mcp_server import main; exit(main(['--self-test']))"

if ($?) {
    Write-Host "[INFO] Self-test passed. Server ready for Cline MCP invocation." -ForegroundColor Green
} else {
    Write-Host "[ERROR] Self-test failed. Check errors above." -ForegroundColor Red
}

Write-Host ""
Write-Host "[INFO] To start the server (Cline will invoke this):" -ForegroundColor Yellow
Write-Host "python -c 'import sys; sys.path.insert(0, '.'); from codex_bridge.agentic_loop_client_mcp_server import main; main()'"
Write-Host ""