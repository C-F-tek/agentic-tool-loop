# Standalone launcher for AI-Carmine Executor Server (port 3560)
# This script starts the executor service independently without OpenWebUI

$ErrorActionPreference = "Stop"
$AI_ROOT = "C:\Users\someo\agentic-tool-loop"
$PYTHONPATH = "$AI_ROOT;$env:PYTHONPATH"
$env:PYTHONPATH = $PYTHONPATH

# Start executor server
$Py = "$AI_ROOT\venvs\labtools\Scripts\python.exe"
$ServicesRoot = "$AI_ROOT\services"

Write-Host "Starting AI-Carmine Executor on port 3560..."
Write-Host "Python: $Py"

Start-Process `
    -FilePath $Py `
    -ArgumentList @("-m", "uvicorn", "aicarmine-executor-server:app", "--host", "127.0.0.1", "--port", "3560") `
    -WorkingDirectory $ServicesRoot `
    -WindowStyle Minimized `
    -PassThru

Write-Host "Waiting for executor health check..."
for ($i = 0; $i -lt 30; $i++) {
    try {
        $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:3560/health")
        $request.Timeout = 3000
        $response = $request.GetResponse()
        $response.Close()
        Write-Host "Executor health check passed!"
        break
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

Write-Host "Executor service started on http://127.0.0.1:3560/health"