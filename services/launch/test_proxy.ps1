# services/launch/test_proxy.ps1
Write-Host "=== AICarmine MCP Proxy Test ===" -ForegroundColor Cyan
Write-Host "Esecuzione test proxy..." -ForegroundColor Yellow

# Vai alla root del progetto
Set-Location $PSScriptRoot\..\..

# Imposta PYTHONPATH
$env:PYTHONPATH = "."

# Esegui il test
python -m services.codex_bridge.mcp_proxy.test_proxy

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Tutti i test passati!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Alcuni test falliti!" -ForegroundColor Red
}

Read-Host "Premi Enter per uscire"