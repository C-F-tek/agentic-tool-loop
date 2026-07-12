$ErrorActionPreference = "Stop"

$OllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($null -eq $OllamaCommand) {
    throw "ollama.exe non trovato nel PATH. Installa Ollama o aggiungi ollama.exe al PATH prima di avviare il task backend."
}
$OllamaExe = $OllamaCommand.Source

$env:OLLAMA_HOST = "127.0.0.1:11435"
# Use dynamic home directory instead of hardcoded 'carmi'
$homeAI = Join-Path $env:USERPROFILE "AI"
$env:OLLAMA_MODELS = Join-Path $homeAI "models-task"
$env:OLLAMA_CONTEXT_LENGTH = "12288"
$env:OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_NO_CLOUD = "1"

# Evita CUDA/NVIDIA sulla task.
$env:CUDA_VISIBLE_DEVICES = "-1"

# Prova Vulkan su device 1, perché device 0 nel tuo log era NVIDIA.
$env:OLLAMA_VULKAN = "1"
$env:GGML_VK_VISIBLE_DEVICES = "1"

# Use current user's home directory dynamically instead of hardcoded 'carmi'
$homeAI = Join-Path $env:USERPROFILE "AI"
New-Item -ItemType Directory -Force -Path (Join-Path $homeAI "models-task") | Out-Null

& $OllamaExe serve
