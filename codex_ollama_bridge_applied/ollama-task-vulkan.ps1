$ErrorActionPreference = "Stop"

$OllamaExe = (Get-Command ollama.exe).Source

$env:OLLAMA_HOST = "127.0.0.1:11435"
$env:OLLAMA_MODELS = "C:\Users\carmi\AI\models-task"
$env:OLLAMA_CONTEXT_LENGTH = "12288"
$env:OLLAMA_KEEP_ALIVE = "15m"
$env:OLLAMA_NO_CLOUD = "1"

# Evita CUDA/NVIDIA sulla task.
$env:CUDA_VISIBLE_DEVICES = "-1"

# Prova Vulkan su device 1, perché device 0 nel tuo log era NVIDIA.
$env:OLLAMA_VULKAN = "1"
$env:GGML_VK_VISIBLE_DEVICES = "1"

New-Item -ItemType Directory -Force -Path "C:\Users\carmi\AI\models-task" | Out-Null

& $OllamaExe serve