# run-python.ps1
# Usage: ./run-python.ps1 <script.py> [args...] or ./run-python.ps1 -c <code>
# Activates .venv-py147 virtual environment and runs Python non-interactively

param(
    [Parameter(Mandatory=$false, Position=0)]
    [string[]]$Command
)

$projectDir = Join-Path $env:USERPROFILE "agentic-tool-loop"
$venvPython = Join-Path $projectDir ".venv-py147\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Virtual environment not found at $venvPython" -ForegroundColor Red
    exit 1
}

# Activate venv by prepending Scripts to PATH
$venvScripts = Join-Path $projectDir ".venv-py147\Scripts"
$env:PATH = "$venvScripts;$env:PATH"

Write-Host "Python: $($venvPython)" -ForegroundColor Green
Write-Host "Python version:" -ForegroundColor Yellow
& $venvPython --version
Write-Host ""

if ($Command -and $Command.Count -gt 0) {
    # Execute Python with all remaining arguments non-interactively
    & $venvPython @Command
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host "Exit code: $exitCode" -ForegroundColor Red
    } else {
        Write-Host "Exit code: $exitCode" -ForegroundColor Green
    }
    exit $exitCode
}

# If no command provided, show usage
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  ./run-python.ps1 <script.py> [args...]" -ForegroundColor White
Write-Host "  ./run-python.ps1 -c <code>" -ForegroundColor White
Write-Host ""
Write-Host "Example:" -ForegroundColor Cyan
Write-Host "  ./run-python.ps1 main.py --arg1 --arg2" -ForegroundColor White
exit 0