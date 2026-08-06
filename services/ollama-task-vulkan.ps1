$ErrorActionPreference = "Stop"

$OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($null -eq $OllamaCommand) {
    throw "ollama.exe non trovato nel PATH. Installa Ollama o aggiungi ollama.exe al PATH prima di avviare il task backend."
}
$OllamaExe = $OllamaCommand.Source

# Find repo root by walking up from current location
$SearchDir = Split-Path -Parent (Get-Location)
$AI_ROOT = $null

while ($SearchDir -and $SearchDir.Length -gt 3) {
    if (Test-Path (Join-Path $SearchDir "agentic-tool-loop")) {
        $AI_ROOT = Join-Path $SearchDir "agentic-tool-loop"
        break
    }
    if (Test-Path (Join-Path $SearchDir ".git")) {
        $AI_ROOT = $SearchDir
        break
    }
    $SearchDir = Split-Path -Parent $SearchDir
}

if (-not $AI_ROOT) {
    $AI_ROOT = Split-Path -Parent (Get-Location)
}

$ModelsTaskDir = Join-Path $AI_ROOT "models-task"

$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_MODELS = $ModelsTaskDir
$env:OLLAMA_CONTEXT_LENGTH = "12288"
$env:OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_NO_CLOUD = "1"

# Evita CUDA/NVIDIA sulla task.
$env:CUDA_VISIBLE_DEVICES = "-1"

# Prova Vulkan su device 1, perché device 0 nel tuo log era NVIDIA.
$env:OLLAMA_VULKAN = "1"
$env:GGML_VK_VISIBLE_DEVICES = "1"

# Create models-task directory dynamically
New-Item -ItemType Directory -Force -Path $ModelsTaskDir | Out-Null

& $OllamaExe serve