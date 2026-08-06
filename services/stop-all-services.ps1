#!/usr/bin/env powershell
# Stop all agentic-tool-loop services

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\progeetsbat\agentic-tool-loop"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Stopping All Services" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Stop OVMS Reranker
Write-Host "[Step 1] Stopping OVMS Reranker..." -ForegroundColor Yellow
Get-Process "ovms.exe" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
if (-not (Get-Process "ovms.exe" -ErrorAction SilentlyContinue)) {
    Write-Host "[OK] OVMS Reranker stopped" -ForegroundColor Green
} else {
    Write-Host "[WARN] OVMS Reranker still running" -ForegroundColor Yellow
}

Write-Host ""

# Stop Vulkan Tool Broker (port 3572)
Write-Host "[Step 2] Stopping Vulkan Tool Broker..." -ForegroundColor Yellow
$proc3572 = Get-NetTCPConnection -LocalPort 3572 -State Listen -ErrorAction SilentlyContinue
if ($proc3572) {
    $targetPid = $proc3572.OwningProcess
    Get-Process -Id $targetPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "[OK] Vulkan Tool Broker stopped" -ForegroundColor Green
} else {
    Write-Host "[OK] Vulkan Tool Broker not running" -ForegroundColor Green
}

Write-Host ""

# Stop Vulkan Bridge (port 3571)
Write-Host "[Step 3] Stopping Vulkan Bridge..." -ForegroundColor Yellow
$proc3571 = Get-NetTCPConnection -LocalPort 3571 -State Listen -ErrorAction SilentlyContinue
if ($proc3571) {
    $targetPid = $proc3571.OwningProcess
    Get-Process -Id $targetPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "[OK] Vulkan Bridge stopped" -ForegroundColor Green
} else {
    Write-Host "[OK] Vulkan Bridge not running" -ForegroundColor Green
}

Write-Host ""

# Stop all Python processes related to uvicorn
Write-Host "[Step 4] Stopping all Python/uvicorn processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "[OK] Python/uvicorn processes stopped" -ForegroundColor Green

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  All Services Stopped" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""