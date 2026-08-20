#!/usr/bin/env powershell
# ------------------------------------------------------------------
# Unified Broker Launcher - Avvia TUTTI i servizi Vulkan/Agentic
# ------------------------------------------------------------------
# Questo script avvia in sequenza:
# 1. Vulkan Tool Broker su porta 3572
# 2. Vulkan Bridge su porta 3571
# 3. Agentic-loop Client MCP su porta 3579
#
# COMANDO DA USARE:
# cd C:\Users\sanit\agentic-tool-loop
# powershell -ExecutionPolicy Bypass -File services\launch_all_brokers.ps1
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
$repoRoot = "C:\Users\sanit\agentic-tool-loop"
$PYTHONPATH = "$repoRoot;$env:PYTHONPATH"
$env:PYTHONPATH = $PYTHONPATH

$HOSTNAME = "127.0.0.1"
$SERVICES = @(
    @{ Name = "Vulkan Tool Broker"; Port = 3572; Module = "services.aicarmine_vulkan_tool_broker:app" },
    @{ Name = "Vulkan Bridge"; Port = 3571; Module = "services.aicarmine_vulkan_bridge_server:app" }
)

# Note: Agentic-loop Client MCP (3579) is a stdio MCP server, not an HTTP uvicorn app.
# It is launched by Cline MCP configuration, not by this script.
# To launch it manually: python -m services.codex_bridge.agentic_loop_client_mcp_server

$LOGS_DIR = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
function Test-HttpEndpoint {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Timeout = $TimeoutSec * 1000
        $response = $request.GetResponse()
        $response.Close()
        return $true
    }
    catch { return $false }
}

function Stop-PortOwner {
    param([int]$Port, [string]$Label)
    try {
        $connections = netstat -ano | Where-Object { $_ -match ":\s*$Port\s+" -and $_ -match "LISTENING" }
        if ($connections) {
            $parts = ($connections -split '\s+')
            $processId = $parts[-1]
            if ($processId -match '^\d+$') {
                Write-Warning "$Label porta $Port occupata. Termino PID=$processId"
                Stop-Process -Id [int]$processId -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        }
    }
    catch { }
}

function Wait-ForEndpoint {
    param([string]$Url, [string]$Label, [int]$TimeoutSec = 60)
    Write-Host "[INFO] Attendo $Label su $Url..."
    for ($i = 0; $i -lt $TimeoutSec; $i++) {
        if (Test-HttpEndpoint -Url $Url -TimeoutSec 2) {
            Write-Host "[OK] $Label pronto su porta $($Url -split ':')[2]"
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "[ERROR] $Label non risponde dopo $TimeoutSec secondi"
    return $false
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Unified Broker Launcher" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Repo root: $repoRoot" -ForegroundColor Cyan
Write-Host "PYTHONPATH: $env:PYTHONPATH" -ForegroundColor Cyan
Write-Host ""

$processes = @{}

foreach ($svc in $SERVICES) {
    $healthUrl = "http://$($HOSTNAME):$($svc.Port)/health"
    $isRunning = Test-HttpEndpoint -Url $healthUrl -TimeoutSec 1

    if ($isRunning) {
        Write-Host "[OK] $($svc.Name) gia' attivo su porta $($svc.Port)" -ForegroundColor Green
        continue
    }

    # Stop existing process on port
    Stop-PortOwner -Port $svc.Port -Label $svc.Name

    # Start process (stdout and stderr must be separate files in PowerShell)
    $stdoutFile = Join-Path $LOGS_DIR "broker-$($svc.Port)-$(Get-Date -Format 'yyyyMMdd_HHmmss').stdout.log"
    $stderrFile = Join-Path $LOGS_DIR "broker-$($svc.Port)-$(Get-Date -Format 'yyyyMMdd_HHmmss').stderr.log"
    Write-Host ""
    Write-Host "[INFO] Avvio $($svc.Name) su porta $($svc.Port)..." -ForegroundColor Yellow
    Write-Host "  Module: $($svc.Module)"
    Write-Host "  Stdout: $stdoutFile"
    Write-Host "  Stderr: $stderrFile"

    $proc = Start-Process `
        -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", $svc.Module, "--host", $HOSTNAME, "--port", "$($svc.Port)") `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile `
        -PassThru

    $processes[$svc.Port] = @{ Process = $proc; Name = $svc.Name; Url = $healthUrl }
}

# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Health Checks" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$allOk = $true
foreach ($port in $processes.Keys) {
    $info = $processes[$port]
    $ok = Wait-ForEndpoint -Url $info.Url -Label $info.Name -TimeoutSec 30
    if (-not $ok) { $allOk = $false }
}

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Launch Complete" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

foreach ($svc in $SERVICES) {
    $status = if (Test-HttpEndpoint -Url "http://$($HOSTNAME):$($svc.Port)/health" -TimeoutSec 1) { "OK" } else { "FAILED" }
    $color = if ($status -eq "OK") { "Green" } else { "Red" }
    Write-Host "$($svc.Name,-25) http://$($HOSTNAME):$($svc.Port) [$status]" -ForegroundColor $color
}

Write-Host ""
Write-Host "Per fermare tutti i broker:" -ForegroundColor Yellow
Write-Host "  Get-Process python | Where-Object { `\$_ .CommandLine -like '*uvicorn*' } | Stop-Process -Force" -ForegroundColor Yellow
Write-Host ""

if (-not $allOk) {
    Write-Host "[WARN] Alcuni servizi non sono pronti. Controlla i log in: $LOGS_DIR" -ForegroundColor Yellow
}