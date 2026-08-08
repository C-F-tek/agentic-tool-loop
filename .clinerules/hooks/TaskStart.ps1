<<<<<<< HEAD
# [TaskStart] Hook — MCP Initialization v2
# Initializes MCP tool routing state at task start for aggressive MCP-first enforcement.

$rawInput = ''
$contextModification = ''
=======
# [TaskStart] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$bootstrap = ''
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskStart' -RawInput $rawInput
<<<<<<< HEAD
    
    # Load MCP orchestrator for initial tool routing setup
    . (Join-Path $PSScriptRoot 'lib\aicarmine_mcp_orchestrator.ps1')
    
    # Initialize MCP routing state for this task
    $payload = ConvertFrom-Json -InputObject $rawInput -ErrorAction SilentlyContinue
    if ($null -ne $payload) {
        # Extract task key for routing state initialization
        $taskKey = $null
        $keyNames = @('taskId', 'task_id', 'taskID')
        foreach ($kn in $keyNames) {
            if ($payload.PSObject.Properties[$kn]) {
                $taskKey = [string]$payload.($kn)
                break
            }
        }
        
        if (-not [string]::IsNullOrEmpty($taskKey)) {
            # Build initial MCP routing hint based on task classification
            $taskText = ''
            $textProp = $payload.PSObject.Properties['message']
            if ($null -ne $textProp) { $taskText = [string]$textProp.Value }
            if ($null -ne $payload.messages) { $taskText = ($payload.messages | Select-Object -First 1 | ConvertTo-Json).ToString() }
            
            # Classify task type and set MCP-first priority
            $mcpPriority = 'high'
            $preferredMcpTools = @()
            $taskLower = $taskText.ToLower()
            
            if ($taskLower -match '(?i)(search|find|look|cerca|trova|read|leggi|apri|validate|verifica|write|scrivi|edit|modifica)') {
                $preferredMcpTools = @(
                    'aicarmine_repo_read',
                    'aicarmine_repo_search',
                    'aicarmine_repo_list_files',
                    'aicarmine_git_readonly_log',
                    'aicarmine_git_readonly_diff',
                    'aicarmine_rag_context',
                    'aicarmine_project_memory_search'
                )
            } elseif ($taskLower -match '(?i)(write|create|modify|patch|apply|refactor|rename|extract)') {
                $preferredMcpTools = @(
                    'aicarmine_repo_apply_patch',
                    'aicarmine_repo_code_apply_patch',
                    'aicarmine_repo_code_propose_edit',
                    'aicarmine_repo_unidiff_validate'
                )
            } elseif ($taskLower -match '(?i)(debug|diagnose|health|check|inspect)') {
                $preferredMcpTools = @(
                    'aicarmine_bridge_health',
                    'aicarmine_repo_status',
                    'aicarmine_repo_capabilities',
                    'aicarmine_repo_validate_diffcheck'
                )
            } else {
                $preferredMcpTools = @(
                    'aicarmine_repo_read',
                    'aicarmine_repo_search',
                    'aicarmine_git_readonly_log'
                )
            }
            
            # Build routing hint for observer state initialization
            $routingHint = @"
Task classes:
- repository_operation
- mcp_first_enforcement

Preferred sequence:
1. $($preferredMcpTools[0])
2. $($preferredMcpTools[1] -join ', ')

Constraints:
- Read-only: false
"@
            
            # Write initial routing state via observer
            . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
            try {
                Write-AICarmineClineTaskRoutingState -RawInput $rawInput -RoutingHint $routingHint
            } catch {
                # Observer write failure is non-blocking
            }
            
            # Emit context modification with MCP-first directive
            $mcpDirective = @"
AICARMINE TASK START: MCP-first enforcement active. Preferred tools: $($preferredMcpTools -join ', '). Always prefer MCP tools over native Cline tools. Native fallback only after concrete MCP failure.
"@
            $contextModification = $mcpDirective
        }
    }
}
catch {
    # Hooks are fail-open; probe or observer failures must not affect Cline.
    $contextModification = ''
=======
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_task_bootstrap.ps1')
    $bootstrap = Get-AICarmineClineTaskBootstrap -RawInput $rawInput
}
catch {
    # Hooks are fail-open; bootstrap or probe failures must not affect Cline.
    $bootstrap = ''
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
}

[ordered]@{
    cancel = $false
<<<<<<< HEAD
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
=======
    contextModification = $bootstrap
    errorMessage = ''
} | ConvertTo-Json -Compress
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
