$ErrorActionPreference = "Stop"

# Find repo root by checking current dir and immediate parents
$AI_ROOT = $null

# Check current directory first
$CurrentDir = Split-Path -Parent (Get-Location)
if (Test-Path (Join-Path $CurrentDir ".git")) {
    $AI_ROOT = $CurrentDir
}

# If not found, check parent directories up to 3 levels
if (-not $AI_ROOT) {
    $SearchDir = $CurrentDir
    for ($i = 0; $i -lt 3; $i++) {
        $SearchDir = Split-Path -Parent $SearchDir
        if (Test-Path (Join-Path $SearchDir ".git")) {
            $AI_ROOT = $SearchDir
            break
        }
    }
}

if (-not $AI_ROOT) {
    # Last fallback: use current directory
    $AI_ROOT = $CurrentDir
}

# Check for explicit environment variable first
$Python = [Environment]::GetEnvironmentVariable("AICARMINE_EXECUTOR_PYTHON", "User")

if ([string]::IsNullOrWhiteSpace($Python)) {
    # Try relative to repo root instead of hardcoded path
    $Python = Join-Path $AI_ROOT "venvs\labtools\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
    # Fallback to python in PATH if labtools venv not available
    $FallbackPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($FallbackPython) {
        $Python = $FallbackPython.Source
    } else {
        throw "Python executor non trovato: $Python"
    }
}

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$env:AICARMINE_SAFE_COMMAND_RUNNER = [Environment]::GetEnvironmentVariable("AICARMINE_SAFE_COMMAND_RUNNER", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_SAFE_COMMAND_RUNNER)) {
    $env:AICARMINE_SAFE_COMMAND_RUNNER = Join-Path $AI_ROOT "services\aicarmine-run-safe-command.ps1"
}

$env:AICARMINE_LAB_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_LAB_REPO)) {
    $env:AICARMINE_LAB_REPO = Join-Path $AI_ROOT "lab-worktrees\blender-audio-project-lab"
}

$env:AICARMINE_REAL_REPO = [Environment]::GetEnvironmentVariable("AICARMINE_REAL_REPO", "User")
if ([string]::IsNullOrWhiteSpace($env:AICARMINE_REAL_REPO)) {
    $env:AICARMINE_REAL_REPO = $AI_ROOT
}

Set-Location (Join-Path $AI_ROOT "services")

& $Python -m uvicorn aicarmine-executor-server:app --host 127.0.0.1 --port 3560