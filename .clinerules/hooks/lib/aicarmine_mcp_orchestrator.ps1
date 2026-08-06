#Requires -RunAsAdmin
<#
.SYNOPSIS
    MCP Orchestrator Hook - Seleziona automaticamente il tool ottimale in base al tipo di query.
    Questo hook PowerShell implementa l'orchestratore MCP a livello di hook Cline,
    permettendo al sistema di routing di Cline di selezionare automaticamente il tool ottimale
    PRIMA che Cline debba chiamare l'orchestratore.
    
    Workflow:
    1. Cline riceve la query utente
    2. L'hook PreToolUse.ps1 chiama aicarmine_mcp_orchestrator.ps1
    3. L'orchestratore analizza la query e seleziona il tool ottimale
    4. Il tool ottimale viene passato a Cline per l'esecuzione
    
    Tool esposti:
    - mcp_select_optimal_tool: Analizza query e seleziona tool ottimale
    - mcp_list_optimal_tools: Lista dei tool ottimali per ogni tipo di query
    - mcp_selection_log: Log delle selezioni MCP effettuate
    - mcp_orchestrate_large_scale: Orchestrazione operazioni su larga scala
    
    Enhanced for large-scale software engineering operations.
#>

param(
    [string]$Query,
    [string]$PreferredServer,
    [switch]$ListTools,
    [switch]$ShowLog,
    [int]$LogLimit = 10,
    [switch]$OrchestrateMode
)

# Importazione moduli
$ErrorActionPreference = "Continue"

# Path del progetto
$ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$ServicesPath = Join-Path $ProjectRoot "services"

# Stato dell'orchestratore
$OrchestratorState = @{
    Selections = @()
    Timestamps = @()
    OrchestrationProgress = @()
}

# Classi di query supportate
enum QueryType {
    Search
    Read
    Validate
    Debug
    Security
    Git
    Memory
    Job
    RAG
    Write
    Orchestrate
    Analyze
}

# Tool selection per ogni tipo di query
$ToolMap = @{
    Search = @{
        Primary   = @{ Server = "aicarmine-repo-search-det"; Tool = "aicarmine_repo_search_fd"; Reason = "Ricerca veloce con fd per pattern semplici" }
        Fallback  = @{ Server = "aicarmine-repo-search-det"; Tool = "aicarmine_repo_search_rg"; Reason = "Ricerca ripgrep per pattern complessi" }
    }
    Read = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_read"; Reason = "Lettura diretta di file noti" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_list_files"; Reason = "Listatura file quando il path è sconosciuto" }
    }
    Validate = @{
        Primary   = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_diffcheck"; Reason = "Validazione diff prima di applicare modifiche" }
        Fallback  = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_ruff"; Reason = "Validazione Python con ruff" }
    }
    Debug = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_bridge_health"; Reason = "Verifica salute bridge" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_status"; Reason = "Stato repository per diagnostica" }
    }
    Security = @{
        Primary   = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_semgrep"; Reason = "Scansione sicurezza statica" }
        Fallback  = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_ruff"; Reason = "Validazione sicurezza con ruff" }
    }
    Git = @{
        Primary   = @{ Server = "aicarmine-git-readonly"; Tool = "aicarmine_git_readonly_log"; Reason = "Log Git per storia repository" }
        Fallback  = @{ Server = "aicarmine-git-readonly"; Tool = "aicarmine_git_readonly_diff"; Reason = "Diff Git per modifiche" }
    }
    Memory = @{
        Primary   = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_search"; Reason = "Ricerca memoria persistente" }
        Fallback  = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_get"; Reason = "Lettura memoria per record specifico" }
    }
    Job = @{
        Primary   = @{ Server = "aicarmine-job-artifact"; Tool = "aicarmine_job_artifact_list_jobs"; Reason = "Listatura job per ispezione" }
        Fallback  = @{ Server = "aicarmine-job-view"; Tool = "aicarmine_job_view_render"; Reason = "Rendering HTML per visualizzazione" }
    }
    RAG = @{
        Primary   = @{ Server = "aicarmine-rag"; Tool = "aicarmine_rag_context"; Reason = "Contesto RAG per conoscenza semantica" }
        Fallback  = @{ Server = "aicarmine-rag"; Tool = "aicarmine_rag_index_status"; Reason = "Stato indice RAG per diagnostica" }
    }
    Write = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_apply_patch"; Reason = "Applicazione patch con guardie" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_write_file"; Reason = "Scrittura file con guardie" }
    }
    Orchestrate = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_tree"; Reason = "Mappa struttura repository per orchestrazione" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_search"; Reason = "Ricerca dipendenze per orchestrazione" }
    }
    Analyze = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_capabilities"; Reason = "Capacità repository per analisi architetturale" }
        Fallback  = @{ Server = "aicarmine-repo-state"; Tool = "aicarmine_repo_state_status"; Reason = "Stato repository per analisi" }
    }
}

# Large-scale orchestration tool sequence
$OrchestrationSequence = @(
    @{ Step = 1; Tool = "aicarmine_repo_tree"; Purpose = "Full structure mapping" },
    @{ Step = 2; Tool = "aicarmine_repo_search"; Purpose = "Dependency discovery" },
    @{ Step = 3; Tool = "aicarmine_git_readonly_log"; Purpose = "History navigation" },
    @{ Step = 4; Tool = "aicarmine_rag_context"; Purpose = "Semantic orientation" },
    @{ Step = 5; Tool = "aicarmine_repo_status"; Purpose = "Repository state verification" }
)

function Get-QueryType {
    param([string]$Query)
    $QueryLower = $Query.ToLower()
    
    if ($QueryLower | Select-String -Pattern 'cerca|trova|search|find|look for') { return [QueryType]::Search }
    if ($QueryLower | Select-String -Pattern 'leggi|apri|visualizza|read|open|view|show') { return [QueryType]::Read }
    if ($QueryLower | Select-String -Pattern 'valida|verifica|validate|check|verify') { return [QueryType]::Validate }
    if ($QueryLower | Select-String -Pattern 'diagnostica|debug|health|diagnose') { return [QueryType]::Debug }
    if ($QueryLower | Select-String -Pattern 'sicurezza|security|scan|safety') { return [QueryType]::Security }
    if ($QueryLower | Select-String -Pattern 'git|commit|branch|log|diff') { return [QueryType]::Git }
    if ($QueryLower | Select-String -Pattern 'memoria|memory|context|contesto') { return [QueryType]::Memory }
    if ($QueryLower | Select-String -Pattern 'job|agent|task|lavoro') { return [QueryType]::Job }
    if ($QueryLower | Select-String -Pattern 'rag|knowledge|semantic|conoscenza') { return [QueryType]::RAG }
    if ($QueryLower | Select-String -Pattern 'scrivi|write|edit|modify') { return [QueryType]::Write }
    if ($QueryLower | Select-String -Pattern 'refactor|migration|orchestrate|large.?scale|multi.?module|codebase|system.?level') { return [QueryType]::Orchestrate }
    if ($QueryLower | Select-String -Pattern 'analyze|architecture|dependency|structure') { return [QueryType]::Analyze }
    
    return [QueryType]::Search
}

function Select-OptimalTool {
    param([string]$Query, [string]$PreferredServer)
    
    $queryType = Get-QueryType -Query $Query
    $toolInfo = $ToolMap[$queryType]
    
    # Se è specificato un server preferito, sovrascrive la selezione
    if ($PreferredServer) {
        return @{
            QueryType = $queryType.ToString()
            SelectedServer = $PreferredServer
            SelectedTool = "N/A (override manuale)"
            Confidence = 0.5
            Reason = "Server preferito specificato"
            Override = $true
            OrchestratorSelection = $toolInfo.Primary
        }
    }
    
    return @{
        QueryType = $queryType.ToString()
        SelectedServer = $toolInfo.Primary.Server
        SelectedTool = $toolInfo.Primary.Tool
        Confidence = 0.9
        Reason = $toolInfo.Primary.Reason
        FallbackServer = $toolInfo.Fallback.Server
        FallbackTool = $toolInfo.Fallback.Tool
        FallbackReason = $toolInfo.Fallback.Reason
        Override = $false
    }
}

function Get-OrchestrationSequence {
    return $OrchestrationSequence | ConvertTo-Json -Depth 3
}

# Gestione delle richieste speciali
if ($ListTools) {
    # Restituisce la mappa completa dei tool ottimali
    $toolMapJson = @{}
    foreach ($type in [QueryType].GetEnumValues()) {
        $info = $ToolMap[$type]
        $toolMapJson[$type.ToString()] = @{
            Primary = $info.Primary
            Fallback = $info.Fallback
        }
    }
    $toolMapJson | ConvertTo-Json -Depth 3
    exit 0
}

if ($ShowLog) {
    # Restituisce il log delle selezioni
    $logEntries = $OrchestratorState.Selections | Select-Object -Last $LogLimit
    $logEntries | ConvertTo-Json -Depth 2
    exit 0
}

if ($OrchestrateMode) {
    # Restituisce la sequenza di orchestrazione per operazioni su larga scala
    $orchResult = @{
        Mode = "Orchestration"
        Sequence = $OrchestrationSequence
        Principles = @(
            "Leaf modules first, then dependent modules, finally top-level",
            "Track all interface changes across module boundaries",
            "Verify compilation/runtime at each phase boundary",
            "Roll back if critical failures detected"
        )
    }
    $orchResult | ConvertTo-Json -Depth 3
    exit 0
}

# Selezione ottimale del tool
if ($Query) {
    $result = Select-OptimalTool -Query $Query -PreferredServer $PreferredServer
    
    # Registra la selezione
    $OrchestratorState.Selections += @{
        Query = $Query
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        Result = $result
    }
    
    # Restituisce il risultato in formato JSON
    $result | ConvertTo-Json -Depth 3
} else {
    Write-Host "Usage: aicarmine_mcp_orchestrator.ps1 [-Query <query>] [-PreferredServer <server>]" -ForegroundColor Yellow
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -Query: Query dell'utente" -ForegroundColor Yellow
    Write-Host "  -PreferredServer: Server MCP preferito (opzionale)" -ForegroundColor Yellow
    Write-Host "  -ListTools: Restituisce la mappa completa dei tool ottimali" -ForegroundColor Yellow
    Write-Host "  -ShowLog: Restituisce il log delle selezioni" -ForegroundColor Yellow
    Write-Host "  -OrchestrateMode: Restituisce la sequenza di orchestrazione" -ForegroundColor Yellow
}