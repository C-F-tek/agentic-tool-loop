$ErrorActionPreference = "Stop"

$env:AI_ROOT = "C:\Users\carmi\AI"

$env:OPENVINO_CACHE_DIR = "C:\Users\carmi\AI\cache\openvino"
$env:HF_HOME = "C:\Users\carmi\AI\cache\huggingface"
$env:TRANSFORMERS_CACHE = "C:\Users\carmi\AI\cache\huggingface\transformers"

New-Item -ItemType Directory -Force -Path `
  $env:OPENVINO_CACHE_DIR, `
  $env:HF_HOME, `
  $env:TRANSFORMERS_CACHE | Out-Null