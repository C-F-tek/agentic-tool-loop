# Activate-Venv Script
# Attiva dinamicamente il venv corretto in base allo strumento chiamato
#
# Usage:
#   .\activate-venv.ps1 -tool <tool_name>
#   .\activate-venv.ps1 -scope <scope_name>
#   .\activate-venv.ps1 -auto    # Auto-detection based on current process
#
# Tool names supported:
#   - broker, planner, validator, dispatcher -> labtools
#   - codeinterpreter, jupyter -> codeinterpreter
#   - executor, command, terminal -> executor
#   - openwebui, vulkan_helper -> openwebui
#   - rerank, embedding, npu -> openvino
#   - default -> labtools

param(
    [Parameter(Mandatory=$false)]
    [string]$Tool,

    [Parameter(Mandatory=$false)]
    [string]$Scope,

    [Parameter(Mandatory=$false)]
    [switch]$Auto
)

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT_DIR = Split-Path -Parent $SCRIPT_DIR

# Default venv mapping
$VENVMAP = @{
    'broker' = 'labtools'
    'planner' = 'labtools'
    'validator' = 'labtools'
    'dispatcher' = 'labtools'
    'repo_read' = 'labtools'
    'repo_search' = 'labtools'
    'repo_tree' = 'labtools'
    'repo_apply_patch' = 'labtools'
    'repo_list_files' = 'labtools'
    'repo_rg_search' = 'labtools'
    'repo_ctags_symbols' = 'labtools'
    'repo_fd_files' = 'labtools'
    'repo_semantic_search' = 'labtools'
    'jupyter_execute' = 'codeinterpreter'
    'code_interpreter' = 'codeinterpreter'
    'terminal_run_command_wait' = 'executor'
    'repo_command' = 'executor'
    'openwebui' = 'openwebui'
    'vulkan_helper' = 'openwebui'
    'rerank' = 'openvino'
    'embedding' = 'openvino'
    'npu' = 'openvino'
}

function Get-VenvName {
    param([string]$ToolOrScope)
    
    if ($ToolOrScope) {
        return $VENVMAP[$ToolOrScope.ToLower()] ?? 'labtools'
    }
    
    return 'labtools'
}

function Get-VenvPaths {
    param([string]$VenvName)
    
    $base = Join-Path $ROOT_DIR "venvs\$VenvName"
    return @{
        Path = $base
        Python = Join-Path $base "Scripts\python.exe"
        Pip = Join-Path $base "Scripts\pip.exe"
    }
}

function Set-PythonPath {
    param([string]$VenvPath)
    
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    
    # Add venv to PATH
    $currentPath = $env:PATH
    $newPath = "$currentPath;$VenvPath"
    
    # Set environment variable
    $env:PYTHONPATH = $VenvPath
    
    # Also update PATH for convenience
    $env:PATH = $newPath
    
    return $pythonPath
}

function Write-VenvStatus {
    param([string]$VenvName, [string]$PythonPath)
    
    $status = @"
========================================
Active Venv: $VenvName
Python: $PythonPath
========================================
"@
    
    Write-Host $status -ForegroundColor Cyan
}

# Main logic
if ($Auto) {
    # Auto-detect based on current executable
    $currentExe = $null
    try {
        $currentExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    } catch {}
    
    if ($currentExe -like "*codeinterpreter*") {
        $venvName = 'codeinterpreter'
    } elseif ($currentExe -like "*executor*") {
        $venvName = 'executor'
    } elseif ($currentExe -like "*openwebui*") {
        $venvName = 'openwebui'
    } else {
        $venvName = 'labtools'
    }
} elseif ($Tool) {
    $venvName = Get-VenvName -Tool:$Tool
} elseif ($Scope) {
    $venvName = Get-VenvName -ToolOrScope:$Scope
} else {
    $venvName = 'labtools'
}

# Get and set venv paths
$paths = Get-VenvPaths -VenvName:$venvName
Set-PythonPath -VenvPath:$paths.Path

# Output status
Write-VenvStatus -VenvName:$venvName -PythonPath:$paths.Python

# Return success
exit 0