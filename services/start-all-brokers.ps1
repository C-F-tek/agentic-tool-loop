#!/usr/bin/env powershell
$ErrorActionPreference = "Stop"

# Set working directory to repo root
Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop"

# Set PYTHONPATH
$env:PYTHONPATH = "C:\Users\sanit\progeetsbat\agentic-tool-loop"

Write-Host "================================================" -ForegroundColor Green
Write-Host "  Starting All Broker Services" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

# Check if ports are already in use
function Test-Port {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

# Start Vulkan Tool Broker on port 3572
if (-not (Test-Port 3572)) {
    Write-Host "[INFO] Starting Vulkan Tool Broker on port 3572..." -ForegroundColor Yellow
    Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop\services"
    Start-Process -FilePath "python" -ArgumentList @("-m", "uvicorn", "services.aicarmine_vulkan_tool_broker:app", "--host", "127.0.0.1", "--port", "3572") -WorkingDirectory "C:\Users\sanit\progeetsbat\agentic-tool-loop\services" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop"
    if (Test-Port 3572) {
        Write-Host "[OK] Vulkan Tool Broker started on port 3572" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to start Vulkan Tool Broker on port 3572" -ForegroundColor Red
    }
} else {
    Write-Host "[OK] Vulkan Tool Broker already running on port 3572" -ForegroundColor Green
}

Write-Host ""

# Start Agentic-loop Client MCP Server on port 3579
if (-not (Test-Port 3579)) {
    Write-Host "[INFO] Starting Agentic-loop Client MCP Server on port 3579..." -ForegroundColor Yellow
    
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
    
    Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop\services"
    Start-Process -FilePath "python" -ArgumentList @("-m", "uvicorn", "services.codex_bridge.agentic_loop_client_mcp_server:app", "--host", "127.0.0.1", "--port", "3579") -WorkingDirectory "C:\Users\sanit\progeetsbat\agentic-tool-loop\services" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop"
    
    if (Test-Port 3579) {
        Write-Host "[OK] Agentic-loop Client MCP Server started on port 3579" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to start Agentic-loop Client MCP Server on port 3579" -ForegroundColor Red
    }
} else {
    Write-Host "[OK] Agentic-loop Client MCP Server already running on port 3579" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Service Status" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check status
if (Test-Port 3572) {
    Write-Host "Vulkan Tool Broker (3572): [OK]" -ForegroundColor Green
} else {
    Write-Host "Vulkan Tool Broker (3572): [FAILED]" -ForegroundColor Red
}

if (Test-Port 3579) {
    Write-Host "Agentic-loop Client (3579): [OK]" -ForegroundColor Green
} else {
    Write-Host "Agentic-loop Client (3579): [FAILED]" -ForegroundColor Red
}

Write-Host ""
Write-Host "To stop all services:" -ForegroundColor Yellow
Write-Host "  Get-Process python | Where-Object { `\$_ .CommandLine -like '*uvicorn*' } | Stop-Process -Force" -ForegroundColor Yellow
Write-Host ""