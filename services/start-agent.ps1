# Start-Agent Script
# Avvia uvicorn con PYTHONPATH impostato correttamente
#
# Usage: .\start-agent.ps1 --port <port> [--reload]
#
# Questo script:
# 1. Imposta PYTHONPATH includendo C:\Users\carmi\AI\services
# 2. Lancia uvicorn con i parametri forniti dall'utente

param(
    [string[]]$ExtraArgs = @()
)

$Root = "C:\Users\carmi\AI\services"
$Py = "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"

# Imposta PYTHONPATH
$env:PYTHONPATH = $Root

# Costruisci gli argomenti per uvicorn
$baseArgs = @("-m", "uvicorn", "aicarmine_vulkan_tool_broker:app", "--host", "127.0.0.1", "--port", "3579")

# Aggiungi argomenti extra (es: --port 3579, --reload)
$baseArgs += $ExtraArgs

Write-Host "Starting uvicorn with PYTHONPATH=$Root" -ForegroundColor Cyan
Write-Host "Arguments:" -ForegroundColor Yellow
foreach ($arg in $baseArgs) {
    Write-Host "  $arg"
}

& $Py $baseArgs