# Auto-activate .venv-py147 virtual environment (Python 3.14.7)
# Source this file or add to PowerShell profile for automatic activation

function Activate-VirtualEnv {
    $venvPath = Join-Path $PWD ".venv-py147"
    $scriptPath = Join-Path $venvPath "Scripts\Activate.ps1"
    
    if (Test-Path $scriptPath) {
        . $scriptPath
        Write-Host "Virtual environment activated: $venvPath" -ForegroundColor Green
    } else {
        Write-Host "Virtual environment not found at: $venvPath" -ForegroundColor Yellow
    }
}

# Auto-activate when entering this directory
Set-Alias activate-virtualenv Activate-VirtualEnv