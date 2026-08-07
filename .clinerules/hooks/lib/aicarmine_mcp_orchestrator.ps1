#Requires -RunAsAdmin
<#
.SYNOPSIS
    MCP Orchestrator Hook — Aggressive MCP-first with quantum/pre-quantum engineering awareness.
    This PowerShell hook implements MCP tool routing at the Cline hook level,
    enabling the system to select optimal MCP tools BEFORE Cline invokes them.
    
    Workflow:
    1. Cline receives user query
    2. PreToolUse.ps1 calls aicarmine_mcp_orchestrator.ps1
    3. Orchestrator analyzes query and selects optimal MCP tool
    4. Optimal tool passed to Cline for execution
    
    Tool exposure:
    - mcp_select_optimal_tool: Analyzes query and selects optimal tool
    - mcp_list_optimal_tools: Lists optimal tools per query type
    - mcp_selection_log: Logs MCP selections
    - mcp_orchestrate_large_scale: Large-scale orchestration
    - mcp_quantum_orchestrate: Quantum/pre-quantum engineering orchestration
    
    Extended with quantum computing, pre-quantum engineering, and hybrid quantum-classical systems.
#>

param(
    [string]$Query,
    [string]$PreferredServer,
    [switch]$ListTools,
    [switch]$ShowLog,
    [int]$LogLimit = 10,
    [switch]$OrchestrateMode,
    [switch]$QuantumMode
)

# Import modules
$ErrorActionPreference = "Continue"

# Project path
$ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$ServicesPath = Join-Path $ProjectRoot "services"

# Orchestrator state
$OrchestratorState = @{
    Selections = @()
    Timestamps = @()
    OrchestrationProgress = @()
}

# Query types — extended with quantum/pre-quantum engineering categories
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
    QuantumCircuit
    QuantumState
    QuantumExperiment
    PreQuantumSimulation
}

# Tool selection per query type — extended with quantum routing
$ToolMap = @{
    Search = @{
        Primary   = @{ Server = "aicarmine-repo-search-det"; Tool = "aicarmine_repo_search_fd"; Reason = "Fast fd search for simple patterns" }
        Fallback  = @{ Server = "aicarmine-repo-search-det"; Tool = "aicarmine_repo_search_rg"; Reason = "Ripgrep search for complex patterns" }
    }
    Read = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_read"; Reason = "Direct read of known files" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_list_files"; Reason = "List files when path unknown" }
    }
    Validate = @{
        Primary   = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_diffcheck"; Reason = "Diff validation before modification" }
        Fallback  = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_ruff"; Reason = "Python validation with ruff" }
    }
    Debug = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_bridge_health"; Reason = "Bridge health check" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_status"; Reason = "Repository status for diagnostics" }
    }
    Security = @{
        Primary   = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_semgrep"; Reason = "Static security scanning" }
        Fallback  = @{ Server = "aicarmine-repo-validate"; Tool = "aicarmine_repo_validate_ruff"; Reason = "Security validation with ruff" }
    }
    Git = @{
        Primary   = @{ Server = "aicarmine-git-readonly"; Tool = "aicarmine_git_readonly_log"; Reason = "Git log for repository history" }
        Fallback  = @{ Server = "aicarmine-git-readonly"; Tool = "aicarmine_git_readonly_diff"; Reason = "Git diff for changes" }
    }
    Memory = @{
        Primary   = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_search"; Reason = "Persistent memory search" }
        Fallback  = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_get"; Reason = "Memory read by specific record" }
    }
    Job = @{
        Primary   = @{ Server = "aicarmine-job-artifact"; Tool = "aicarmine_job_artifact_list_jobs"; Reason = "Job listing for inspection" }
        Fallback  = @{ Server = "aicarmine-job-view"; Tool = "aicarmine_job_view_render"; Reason = "HTML rendering for visualization" }
    }
    RAG = @{
        Primary   = @{ Server = "aicarmine-rag"; Tool = "aicarmine_rag_context"; Reason = "RAG context for semantic knowledge" }
        Fallback  = @{ Server = "aicarmine-rag"; Tool = "aicarmine_rag_index_status"; Reason = "RAG index status for diagnostics" }
    }
    Write = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_apply_patch"; Reason = "Patch application with guards" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_write_file"; Reason = "File write with guards" }
    }
    Orchestrate = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_tree"; Reason = "Repository structure mapping for orchestration" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_search"; Reason = "Dependency search for orchestration" }
    }
    Analyze = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_capabilities"; Reason = "Repository capabilities for architectural analysis" }
        Fallback  = @{ Server = "aicarmine-repo-state"; Tool = "aicarmine_repo_state_status"; Reason = "Repository state for analysis" }
    }
    # Quantum/pre-quantum engineering tool routing — MCP-first
    QuantumCircuit = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_read"; Reason = "Read circuit definition files (Qiskit/Cirq/PennyLane) for HTML visualization" }
        Fallback  = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_search"; Reason = "Search circuit patterns in repository" }
    }
    QuantumState = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_read"; Reason = "Read statevector/density matrix data for Bloch sphere visualization" }
        Fallback  = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_search"; Reason = "Search quantum experiment metadata" }
    }
    QuantumExperiment = @{
        Primary   = @{ Server = "aicarmine-project-memory"; Tool = "aicarmine_project_memory_search"; Reason = "Search quantum experiment logs and results" }
        Fallback  = @{ Server = "aicarmine-job-artifact"; Tool = "aicarmine_job_artifact_list_jobs"; Reason = "List quantum job artifacts" }
    }
    PreQuantumSimulation = @{
        Primary   = @{ Server = "aicarmine-codex-app"; Tool = "aicarmine_repo_read"; Reason = "Read classical approximation code for HTML dashboard" }
        Fallback  = @{ Server = "aicarmine-repo-search-det"; Tool = "aicarmine_repo_search_fd"; Reason = "Search simulation patterns" }
    }
}

# Large-scale orchestration sequence
$OrchestrationSequence = @(
    @{ Step = 1; Tool = "aicarmine_repo_tree"; Purpose = "Full structure mapping" },
    @{ Step = 2; Tool = "aicarmine_repo_search"; Purpose = "Dependency discovery" },
    @{ Step = 3; Tool = "aicarmine_git_readonly_log"; Purpose = "History navigation" },
    @{ Step = 4; Tool = "aicarmine_rag_context"; Purpose = "Semantic orientation" },
    @{ Step = 5; Tool = "aicarmine_repo_status"; Purpose = "Repository state verification" }
)

# Quantum/pre-quantum engineering orchestration sequence — MCP-first
$QuantumOrchestrationSequence = @(
    @{ Step = 1; Tool = "aicarmine_repo_read"; Purpose = "Read circuit definition (Qiskit/Cirq/PennyLane)" },
    @{ Step = 2; Tool = "aicarmine_repo_search"; Purpose = "Find related quantum module files" },
    @{ Step = 3; Tool = "aicarmine_project_memory_search"; Purpose = "Retrieve experiment metadata" },
    @{ Step = 4; Tool = "aicarmine_repo_read"; Purpose = "Read statevector/data for HTML visualization" },
    @{ Step = 5; Tool = "aicarmine_repo_apply_patch"; Purpose = "Apply HTML template updates for circuit display" }
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
    # Quantum/pre-quantum engineering task classification
    if ($QueryLower | Select-String -Pattern 'circuit|gate|quantum.?circuit|qubit.?register') { return [QueryType]::QuantumCircuit }
    if ($QueryLower | Select-String -Pattern 'statevector|bloch|density.?matrix|state.?browser') { return [QueryType]::QuantumState }
    if ($QueryLower | Select-String -Pattern 'experiment|shots|measurement|vqe|qaoa|qnn|nisq') { return [QueryType]::QuantumExperiment }
    if ($QueryLower | Select-String -Pattern 'pre.?quantum|classical.?approximation|simulation|hybrid.?quantum') { return [QueryType]::PreQuantumSimulation }
    
    return [QueryType]::Search
}

function Select-OptimalTool {
    param([string]$Query, [string]$PreferredServer)
    
    $queryType = Get-QueryType -Query $Query
    $toolInfo = $ToolMap[$queryType]
    
    # If preferred server specified, override selection
    if ($PreferredServer) {
        return @{
            QueryType = $queryType.ToString()
            SelectedServer = $PreferredServer
            SelectedTool = "N/A (manual override)"
            Confidence = 0.5
            Reason = "Preferred server specified"
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

function Get-QuantumOrchestrationSequence {
    return $QuantumOrchestrationSequence | ConvertTo-Json -Depth 3
}

# Special request handling
if ($ListTools) {
    # Return complete optimal tool map — including quantum types
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
    # Return selection logs
    $logEntries = $OrchestratorState.Selections | Select-Object -Last $LogLimit
    $logEntries | ConvertTo-Json -Depth 2
    exit 0
}

if ($OrchestrateMode) {
    # Large-scale orchestration sequence
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

# Quantum orchestration mode — MCP-first for quantum engineering tasks
if ($Query -and $Query.ToLower() -match '(?i)(quantum|qubit|circuit|statevector|bloch|pre.?quantum|hybrid.?quantum)') {
    $quantumResult = @{
        Mode = "QuantumOrchestration"
        Sequence = $QuantumOrchestrationSequence
        Principles = @(
            "MCP-first: Use aicarmine_repo_read for circuit/statevector data, never native read_file",
            "HTML visualization requires bounded JSON export via MCP tools",
            "Quantum experiment metadata tracked via aicarmine_project_memory_search",
            "Classical approximation fallback uses aicarmine_repo_search for simulation code"
        )
        PreferredServers = @(
            "aicarmine-codex-app (repo operations with truncation control)",
            "aicarmine-project-memory (experiment metadata)",
            "aicarmine-repo-search-det (simulation pattern discovery)"
        )
        Practices = @(
            "Quantum computing: circuit visualization, statevector display, Bloch sphere coordinates",
            "Pre-quantum engineering: classical approximation layer, hybrid workflow orchestrator",
            "Quantum-classical hybrid systems: deterministic seeding, shot budgets, graceful degradation"
        )
    }
    $quantumResult | ConvertTo-Json -Depth 3
    exit 0
}

# Optimal tool selection
if ($Query) {
    $result = Select-OptimalTool -Query $Query -PreferredServer $PreferredServer
    
    # Record selection
    $OrchestratorState.Selections += @{
        Query = $Query
        Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        Result = $result
    }
    
    # Return result in JSON format
    $result | ConvertTo-Json -Depth 3
} else {
    Write-Host "Usage: aicarmine_mcp_orchestrator.ps1 [-Query <query>] [-PreferredServer <server>]" -ForegroundColor Yellow
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -Query: User query" -ForegroundColor Yellow
    Write-Host "  -PreferredServer: Preferred MCP server (optional)" -ForegroundColor Yellow
    Write-Host "  -ListTools: Returns complete optimal tool map" -ForegroundColor Yellow
    Write-Host "  -ShowLog: Returns selection logs" -ForegroundColor Yellow
    Write-Host "  -OrchestrateMode: Returns orchestration sequence" -ForegroundColor Yellow
    Write-Host "  -QuantumMode: Returns quantum orchestration sequence" -ForegroundColor Yellow
}