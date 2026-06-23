$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"

$OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($null -eq $OllamaCommand) {
    throw "ollama.exe non trovato nel PATH. Installa Ollama o aggiungi ollama.exe al PATH prima di avviare il task backend."
}
$OllamaExe = $OllamaCommand.Source

# ------------------------------------------------------------------
# Isolated Python venv environment (same pattern as openwebui_runtime.ps1)
# ------------------------------------------------------------------

$LabToolsRoot = "$AI_ROOT\venvs\labtools"
$LabToolsScripts = "$LabToolsRoot\Scripts"

if (-not (Test-Path -LiteralPath "$LabToolsScripts\python.exe")) {
    throw "Python labtools non trovato: $LabToolsScripts\python.exe"
}

# Save old env values for restoration
$OldVirtualEnv = $env:VIRTUAL_ENV
$OldPythonHome = $env:PYTHONHOME
$OldPythonPath = $env:PYTHONPATH
$OldPath = $env:PATH
$OldAICarmineLabtoolsPython = $env:AICARMINE_LABTOOLS_PYTHON

# Set isolated venv environment
$env:AICARMINE_LABTOOLS_PYTHON = "$LabToolsScripts\python.exe"
$env:VIRTUAL_ENV = $LabToolsRoot
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

# Prepend labtools Scripts to PATH, removing other venv scripts paths
$pathParts = @($env:PATH -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
$cleanPathParts = @(
    $pathParts | Where-Object {
        $normalized = $_.TrimEnd('\').ToLowerInvariant()
        ($normalized -ne ($LabToolsScripts).TrimEnd('\').ToLowerInvariant()) -and
            (-not ($normalized.StartsWith(($AI_ROOT + "\venvs").ToLowerInvariant()) -and $normalized.EndsWith("\scripts")))
    }
)
$env:PATH = (@($LabToolsScripts) + $cleanPathParts) -join ';'

# ------------------------------------------------------------------
# Ollama environment variables for Intel GPU only on port 11435
# Hide NVIDIA GPU by disabling Vulkan on device 0, show only Intel iGPU (Vulkan1)
# ------------------------------------------------------------------

$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_MODELS = "C:\Users\carmi\AI\models-task"
$env:OLLAMA_CONTEXT_LENGTH = "12288"
$env:OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_NO_CLOUD = "1"

# Hide NVIDIA GPU from Ollama - only expose Intel iGPU (device 1) to Vulkan layer
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:GGML_VK_VISIBLE_DEVICES = "1"
$env:OLLAMA_IGPU_ENABLE = "1"

# Intel GPU specific settings

New-Item -ItemType Directory -Force -Path "C:\Users\carmi\AI\models-task" | Out-Null

Write-Host "Starting Ollama subagent on 127.0.0.1:11435 with Intel GPU device 0..."
Write-Host "Python venv isolated: $LabToolsRoot"
Write-Host "VIRTUAL_ENV=$env:VIRTUAL_ENV"

try {
    & $OllamaExe serve
} finally {
    # Restore original environment
    if ($null -eq $OldVirtualEnv) { Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue } else { $env:VIRTUAL_ENV = $OldVirtualEnv }
    if ($null -eq $OldPythonHome) { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue } else { $env:PYTHONHOME = $OldPythonHome }
    if ($null -eq $OldPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $OldPythonPath }
    if ($null -eq $OldPath) { Remove-Item Env:PATH -ErrorAction SilentlyContinue } else { $env:PATH = $OldPath }
    if ($null -eq $OldAICarmineLabtoolsPython) { Remove-Item Env:AICARMINE_LABTOOLS_PYTHON -ErrorAction SilentlyContinue } else { $env:AICARMINE_LABTOOLS_PYTHON = $OldAICarmineLabtoolsPython }
}