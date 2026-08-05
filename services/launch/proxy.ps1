# services/launch/proxy.ps1
# AICarmine MCP Proxy - Quick Start Script
Write-Host "=== AICarmine MCP Proxy ===" -ForegroundColor Cyan
Write-Host "Avvio proxy MCP unificato..." -ForegroundColor Yellow

Set-Location $PSScriptRoot\..

$env:PYTHONPATH = "."
$env:AICARMINE_CODEX_MCP_REPO_ROOT = "."
$env:AICARMINE_LAB_REPO = "."
$env:AICARMINE_MCP_GZIP_ENABLED = "1"
$env:AICARMINE_MCP_GZIP_THRESHOLD = "8192"

Write-Host "`n[INFO] Avvio proxy MCP..." -ForegroundColor Green
python -u -m services.codex_bridge.mcp_proxy.proxy_server