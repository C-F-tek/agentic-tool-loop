# ------------------------------------------------------------------
# Script per impostare le variabili d'ambiente permanenti in PowerShell
# Esegui questo script UNA VOLTA per rendere le variabili permanenti
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================"
Write-Host "  Imposta variabili d'ambiente permanenti"
Write-Host "============================================"
Write-Host ""

# Verifica se il profilo PowerShell esiste
$profilePath = $PROFILE.CurrentUserCurrentHost
Write-Host "Profile PowerShell: $profilePath"
Write-Host ""

# Controlla se le variabili sono già state aggiunte
$profileContent = if (Test-Path $profilePath) {
    Get-Content $profilePath -Raw
} else {
    ""
}

if ($profileContent -contains "AICARMINE_LAB_REPO") {
    Write-Host "[OK] Le variabili d'ambiente sono già presenti nel profilo PowerShell."
    Write-Host ""
    Write-Host "Sei pronto. Riapri PowerShell e avvia il broker."
    Write-Host ""
    return
}

# Aggiunge le variabili al profilo PowerShell
$envBlock = @'

# ------------------------------------------------------------------
# AICarmine Environment Variables (permanent)
# ------------------------------------------------------------------
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_VULKAN_WORKSPACE = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker"
$env:AICARMINE_AGENT_JOB_ROOT = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs"
$env:AICARMINE_AGENT_JOB_DB = "C:\Users\sanit\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\agent_jobs.sqlite3"
$env:AICARMINE_AGENTIC_PLANNER_MODEL = "mio-qwen-code-toolnative:latest"
$env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = "262144"
$env:AICARMINE_AGENTIC_PLANNER_ENABLED = "1"
$env:AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS = "1"
$env:AICARMINE_AGENTIC_PLANNER_URL = "http://127.0.0.1:11435/api/chat"
$env:AICARMINE_VULKAN_BROKER_OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
$env:AICARMINE_VULKAN_BROKER_MODEL = "qwen3-task-8k"
$env:AICARMINE_AGENT_DEFAULT_MAX_STEPS = "40"
$env:AICARMINE_AGENT_MAX_STEPS = "100"

'@

# Crea la directory se non esiste
$profileDir = Split-Path $profilePath -Parent
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
}

# Aggiunge il blocco al profilo
Add-Content -Path $profilePath -Value $envBlock -Encoding UTF8

Write-Host "[OK] Variabili d'ambiente aggiunte al profilo PowerShell."
Write-Host ""
Write-Host "Le variabili sono ora permanenti e verranno caricate ad ogni avvio di PowerShell."
Write-Host ""
Write-Host "Per attivare le variabili nella sessione corrente, esegui:"
Write-Host "  . `$PROFILE"
Write-Host ""
Write-Host "============================================"
Write-Host "  Variabili impostate con successo"
Write-Host "============================================"
Write-Host ""