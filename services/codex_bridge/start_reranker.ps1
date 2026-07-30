#!/usr/bin/env pwsh
#
# PowerShell launcher for the Python-native Reranker Server
# This replaces the OVMS reranker and works on Windows without OpenVINO
#
# Usage:
#   .\start_reranker.ps1              # Start with defaults (port 3550)
#   .\start_reranker.ps1 --port 3551  # Start on custom port
#

param(
    [int]$Port = 3550,
    [string]$Host = "127.0.0.1",
    [string]$Model = "BAAI/bge-reranker-v2-m3",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$RERANKER_SCRIPT = Join-Path $SCRIPT_DIR "ovms_alternative_reranker.py"

# Check if the reranker script exists
if (-not (Test-Path $RERANKER_SCRIPT)) {
    Write-Host "ERROR: Reranker script not found: $RERANKER_SCRIPT" -ForegroundColor Red
    exit 1
}

# Check if port is already in use
$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "WARNING: Port $Port is already in use (PID: $($portInUse.OwningProcess))" -ForegroundColor Yellow
    Write-Host "Stopping existing process..." -ForegroundColor Yellow
    Stop-Process -Id $portInUse.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

if ($CheckOnly) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
        exit 1
    }
    $pyVersion = python --version 2>&1
    Write-Host "Python: $pyVersion" -ForegroundColor Green
    Write-Host "Reranker script: $RERANKER_SCRIPT" -ForegroundColor Green
    Write-Host "Port: $Port" -ForegroundColor Green
    Write-Host "Model: $Model" -ForegroundColor Green
    Write-Host "Health check URL: http://$Host:`$Port/health" -ForegroundColor Green
    Write-Host "Rerank endpoint: http://$Host:`$Port/v3/rerank" -ForegroundColor Green
    exit 0
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Python-Native Reranker Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Port:        $Port" -ForegroundColor White
Write-Host "Host:        $Host" -ForegroundColor White
Write-Host "Model:       $Model" -ForegroundColor White
Write-Host "Script:      $RERANKER_SCRIPT" -ForegroundColor White
Write-Host ""
Write-Host "Starting server..." -ForegroundColor Yellow
Write-Host ""

# Set environment variables for RAG integration
$env:AICARMINE_RAG_RERANK_URL = "http://$Host`:$Port/v3/rerank"
$env:AICARMINE_RAG_RERANK_READY_URL = "http://$Host`:$Port/v2/models/$([System.Web.HttpUtility]::UrlEncode($Model))/ready"
$env:AICARMINE_RAG_RERANK_MODEL = $Model

# Run the reranker server
python "$RERANKER_SCRIPT" --port $Port --host $Host --model $Model

exit $LASTEXITCODE