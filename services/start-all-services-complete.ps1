#!/usr/bin/env powershell
# Complete service startup sequence for agentic-tool-loop
# This script starts all services in the correct order, each in its own visible window

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\\agentic-tool-loop"

function Test-Port {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Starting All Services - Each in its own window" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Ollama is running
Write-Host "[Step 1] Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaVersion = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 5
    Write-Host "[OK] Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Ollama not reachable at http://127.0.0.1:11434" -ForegroundColor Red
    Write-Host "[HINT] Start Ollama first: ollama serve" -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Start OVMS Reranker on port 3550 (in its own visible window)
Write-Host "[Step 2] Starting OVMS Reranker on port 3550..." -ForegroundColor Yellow
if (-not (Test-Path "C:\Users\sanit\\agentic-tool-loop\services\launch\models-ovms-rerank\config.json")) {
    Write-Host "[ERROR] OVMS config.json not found" -ForegroundColor Red
} else {
    Start-Process -FilePath "C:\Users\sanit\\agentic-tool-loop\services\launch\ovms-runtime\bin\ovms.exe" `
        -ArgumentList @("--rest_port", "3550", "--rest_bind_address", "127.0.0.1", 
                        "--config_path", "C:\Users\sanit\\agentic-tool-loop\services\launch\models-ovms-rerank\config.json") `
        -WindowStyle Normal `
        -WorkingDirectory "C:\Users\sanit\\agentic-tool-loop\services\launch"
    Start-Sleep -Seconds 3
    if (Test-Port 3550) {
        Write-Host "[OK] OVMS Reranker started on port 3550" -ForegroundColor Green
    } else {
        Write-Host "[WARN] OVMS Reranker may not have started on port 3550" -ForegroundColor Yellow
    }
}

Write-Host ""

# Step 3: Start Vulkan Tool Broker on port 3579 (in its own visible window)
Write-Host "[Step 3] Starting Vulkan Tool Broker on port 3579..." -ForegroundColor Yellow
if (-not (Test-Port 3579)) {
    Start-Process -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "aicarmine_vulkan_tool_broker:app", "--host", "127.0.0.1", "--port", "3579") `
        -WindowStyle Normal `
        -WorkingDirectory "C:\Users\sanit\\agentic-tool-loop\services"
    Start-Sleep -Seconds 3
    if (Test-Port 3579) {
        Write-Host "[OK] Vulkan Tool Broker started on port 3579" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to start Vulkan Tool Broker on port 3579" -ForegroundColor Red
    }
} else {
    Write-Host "[OK] Vulkan Tool Broker already running on port 3579" -ForegroundColor Green
}

Write-Host ""

# Step 4: Start Vulkan Bridge on port 3571 (in its own visible window)
Write-Host "[Step 4] Starting Vulkan Bridge on port 3571..." -ForegroundColor Yellow
if (-not (Test-Port 3571)) {
    Start-Process -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "aicarmine_vulkan_bridge_server:app", "--host", "127.0.0.1", "--port", "3571") `
        -WindowStyle Normal `
        -WorkingDirectory "C:\Users\sanit\\agentic-tool-loop\services"
    Start-Sleep -Seconds 3
    if (Test-Port 3571) {
        Write-Host "[OK] Vulkan Bridge started on port 3571" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Vulkan Bridge may not have started on port 3571" -ForegroundColor Yellow
    }
} else {
    Write-Host "[OK] Vulkan Bridge already running on port 3571" -ForegroundColor Green
}

Write-Host ""

# Step 5: Verify all ports
Write-Host "[Step 5] Verifying service status..." -ForegroundColor Yellow
Write-Host ""

if (Test-Port 3550) {
    Write-Host "OVMS Reranker (3550): [OK]" -ForegroundColor Green
} else {
    Write-Host "OVMS Reranker (3550): [FAILED]" -ForegroundColor Red
}

if (Test-Port 3579) {
    Write-Host "Vulkan Tool Broker (3579): [OK]" -ForegroundColor Green
} else {
    Write-Host "Vulkan Tool Broker (3579): [FAILED]" -ForegroundColor Red
}

if (Test-Port 3571) {
    Write-Host "Vulkan Bridge (3571): [OK]" -ForegroundColor Green
} else {
    Write-Host "Vulkan Bridge (3571): [FAILED]" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Service Startup Complete" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: Agentic-loop Client MCP Server (port 3579) is a stdio-based MCP server." -ForegroundColor Yellow
Write-Host "It is started by Cline directly, not via uvicorn HTTP." -ForegroundColor Yellow
Write-Host ""
Write-Host "All services are now running in separate visible windows." -ForegroundColor Green
Write-Host "Close each window individually to stop the corresponding service." -ForegroundColor Yellow