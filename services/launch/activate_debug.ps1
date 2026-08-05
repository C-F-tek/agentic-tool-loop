# activate_debug.ps1 - Attiva debug per testing
param(
    [string]$Env = "dev",
    [switch]$RaiseOnError = $false
)

Write-Host "🔧 Attivazione Error Handler Debug" -ForegroundColor Cyan
Write-Host ""

# Imposta le variabili d'ambiente
$env:AICARMINE_USE_WRAPPER = "true"
$env:AICARMINE_LOG_STRUCTURED = "true"

if ($RaiseOnError) {
    $env:AICARMINE_RAISE_ON_ERROR = "true"
    Write-Host "⚠️ RAISE_ON_ERROR attivo - le eccezioni verranno rilanciate!" -ForegroundColor Red
} else {
    $env:AICARMINE_RAISE_ON_ERROR = "false"
    Write-Host "✅ RAISE_ON_ERROR disattivato (modalità produzione)" -ForegroundColor Green
}

if ($Env -eq "prod") {
    Write-Host "🚨 ATTENZIONE: Attivazione in PRODUZIONE!" -ForegroundColor Yellow
    $env:AICARMINE_RAISE_ON_ERROR = "false"
    Write-Host "   → RAISE_ON_ERROR forzato a false per sicurezza" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📋 Configurazione attiva:" -ForegroundColor Cyan
Write-Host "   AICARMINE_USE_WRAPPER=$env:AICARMINE_USE_WRAPPER" -ForegroundColor White
Write-Host "   AICARMINE_LOG_STRUCTURED=$env:AICARMINE_LOG_STRUCTURED" -ForegroundColor White
Write-Host "   AICARMINE_RAISE_ON_ERROR=$env:AICARMINE_RAISE_ON_ERROR" -ForegroundColor White
Write-Host ""
Write-Host "✅ Error handler attivato" -ForegroundColor Green
Write-Host ""
Write-Host "Per disattivare, esegui: ./rollback_error_handler.ps1" -ForegroundColor Gray