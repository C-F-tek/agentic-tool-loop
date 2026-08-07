#!/usr/bin/env powershell
# Stop all agentic-tool-loop services

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\agentic-tool-loop"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Stopping All Services" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Known service ports to close
$servicePorts = @(
    @{ Port = 3550; Name = "OpenWebUI" },
    @{ Port = 3560; Name = "Ollama" },
    @{ Port = 3571; Name = "Vulkan Bridge" },
    @{ Port = 3572; Name = "Vulkan Tool Broker" },
    @{ Port = 3579; Name = "Agentic Loop Client" },
    @{ Port = 3581; Name = "Codex Provider Bridge" },
    @{ Port = 8080; Name = "Reranker" },
    @{ Port = 8888; Name = "OVMS Model Server" },
    @{ Port = 8889; Name = "OVMS Reranker" },
    @{ Port = 11434; Name = "Ollama Default" },
    @{ Port = 11435; Name = "Ollama Vulkan GPU" }
)

# Step 1: Stop OVMS Reranker
Write-Host "[Step 1] Stopping OVMS Reranker..." -ForegroundColor Yellow
Get-Process "ovms.exe" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
if (-not (Get-Process "ovms.exe" -ErrorAction SilentlyContinue)) {
    Write-Host "[OK] OVMS Reranker stopped" -ForegroundColor Green
} else {
    Write-Host "[WARN] OVMS Reranker still running" -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Close each known service port via TCP connection
foreach ($svc in $servicePorts) {
    $portNum = $svc.Port
    $portName = $svc.Name
    Write-Host "[Step 2.$($servicePorts.IndexOf($svc))] Stopping $portName (port $portNum)..." -ForegroundColor Yellow
    
    $conn = Get-NetTCPConnection -LocalPort $portNum -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $targetPid = $conn.OwningProcess
        if ($targetPid -gt 0) {
            $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                Write-Host "  -> Killed PID $targetPid ($($proc.Name))" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "[OK] $portName (port $portNum) not listening" -ForegroundColor Green
    }
}

Start-Sleep -Seconds 3

Write-Host ""

# Step 3: Stop all Python/uvicorn processes
Write-Host "[Step 3] Stopping all Python/uvicorn processes..." -ForegroundColor Yellow
$pythonUvicorn = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" }
if ($pythonUvicorn) {
    $pythonUvicorn | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "[OK] Python/uvicorn processes stopped" -ForegroundColor Green
} else {
    Write-Host "[OK] No Python/uvicorn processes found" -ForegroundColor Green
}

Write-Host ""

# Step 4: Force kill any remaining Python processes on service ports
Write-Host "[Step 4] Checking for remaining Python processes on service ports..." -ForegroundColor Yellow
$remaining = Get-NetTCPConnection -LocalPort ($servicePorts | ForEach-Object { $_.Port }) -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 }
if ($remaining) {
    $processIds = $remaining | Select-Object -ExpandProperty OwningProcess | Get-Unique
    foreach ($processId in $processIds) {
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -eq "python") {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "  -> Force killed PID $processId" -ForegroundColor Yellow
        }
    }
    Write-Host "[OK] Remaining Python processes cleaned up" -ForegroundColor Green
} else {
    Write-Host "[OK] No remaining Python processes on service ports" -ForegroundColor Green
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  All Services Stopped" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
