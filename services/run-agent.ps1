# Run-Agent Script
# Wrapper per avviare uvicorn con PYTHONPATH impostato correttamente
#
# Usage: .\run-agent.ps1 [--port <port>]
#
# Questo script:
# 1. Imposta PYTHONPATH includendo C:\Users\carmi\AI\services
# 2. Lancia uvicorn con l'argomento corretto

param(
    [int]$Port = 3572
)

$Root = r"C:\Users\carmi\AI\services"
$Py = r"C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"

# Imposta PYTHONPATH
$env:PYTHONPATH = $Root

# Costruisci gli argomenti per uvicorn
$uvicornArgs = @("-m", "uvicorn", "aicarmine_vulkan_tool_broker:app", "--host", "127.0.0.1", "--port", $Port.ToString())

Write-Host "Starting uvicorn with PYTHONPATH=$Root"
Write-Host "Arguments:"
foreach ($arg in $uvicornArgs) {
    Write-Host "  $arg"
}

& $Py $uvicornArgs