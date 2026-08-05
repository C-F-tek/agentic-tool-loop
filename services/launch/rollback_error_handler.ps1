# rollback_error_handler.ps1
param(
    [string]$Env = "prod"
)

Write-Host "🔄 Rollback Error Handler..." -ForegroundColor Yellow
Write-Host ""

# Disattiva immediatamente
$env:AICARMINE_USE_WRAPPER = "false"
$env:AICARMINE_LOG_STRUCTURED = "false"
$env:AICARMINE_RAISE_ON_ERROR = "false"

if ($Env -eq "prod") {
    Write-Host "✅ Error handler disattivato in PRODUZIONE" -ForegroundColor Green
} else {
    Write-Host "✅ Error handler disattivato in $Env" -ForegroundColor Green
}

Write-Host ""
Write-Host "📋 Configurazione dopo rollback:" -ForegroundColor Cyan
Write-Host "   AICARMINE_USE_WRAPPER=$env:AICARMINE_USE_WRAPPER" -ForegroundColor White
Write-Host "   AICARMINE_LOG_STRUCTURED=$env:AICARMINE_LOG_STRUCTURED" -ForegroundColor White
Write-Host "   AICARMINE_RAISE_ON_ERROR=$env:AICARMINE_RAISE_ON_ERROR" -ForegroundColor White
Write-Host ""
Write-Host "✅ Rollback completato - Modalità legacy attivata" -ForegroundColor Green
Write-Host ""
Write-Host "Per riattivare il debug, esegui: ./activate_debug.ps1" -ForegroundColor Gray