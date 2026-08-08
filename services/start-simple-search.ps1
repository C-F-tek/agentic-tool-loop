$ErrorActionPreference = "Stop"
Set-Location "C:\Users\sanit\agentic-tool-loop"

function Test-Port {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Simple Search Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Ollama is running on port 11434
Write-Host "[Step 1] Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaVersion = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 5
    Write-Host "[OK] Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Ollama not reachable at http://127.0.0.1:11434" -ForegroundColor Red
    Write-Host "[HINT] Start Ollama first: ollama serve" -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Start OVMS Reranker on port 3550
Write-Host "[Step 2] Starting OVMS Reranker on port 3550..." -ForegroundColor Yellow
$ovmsScript = "C:\Users\sanit\agentic-tool-loop\services\ovms-reranker-npu.ps1"
if (Test-Path $ovmsScript) {
    Start-Process -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-File", $ovmsScript) `
        -WindowStyle Normal
    Start-Sleep -Seconds 5
    if (Test-Port 3550) {
        Write-Host "[OK] OVMS Reranker started on port 3550" -ForegroundColor Green
    } else {
        Write-Host "[WARN] OVMS Reranker may not have started on port 3550" -ForegroundColor Yellow
    }
} else {
    Write-Host "[ERROR] OVMS script not found at $ovmsScript" -ForegroundColor Red
}

Write-Host ""

# Step 3: Verify status
Write-Host "[Step 3] Verifying service status..." -ForegroundColor Yellow
Write-Host ""

if (Test-Port 11434) {
    Write-Host "Ollama (11434): [OK]" -ForegroundColor Green
} else {
    Write-Host "Ollama (11434): [FAILED]" -ForegroundColor Red
}

if (Test-Port 3550) {
    Write-Host "OVMS Reranker (3550): [OK]" -ForegroundColor Green
} else {
    Write-Host "OVMS Reranker (3550): [FAILED]" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Startup Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: Simple Local Search MCP is a stdio-based server." -ForegroundColor Yellow
Write-Host "Start it manually when needed:" -ForegroundColor Yellow
Write-Host "  cd services\codex_bridge; python simple_local_search_mcp_server.py" -ForegroundColor White
Write-Host ""