# TaskComplete Hook
# PowerShell template for Windows hook execution.
# Handles task completion with cleanup orchestration and state consolidation.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskComplete' -RawInput $rawInput
    
    # Parse input for completion state
    if ($rawInput) {
        $payload = $rawInput | ConvertFrom-Json
        $taskIdentity = $null
        foreach ($alias in @('taskId', 'task_id', 'taskID')) {
            $property = $payload.PSObject.Properties[$alias]
            if ($null -ne $property) {
                $taskIdentity = $property.Value
                break
            }
        }
        
        # Add completion orchestration guidance for large-scale operations
        if ($taskIdentity) {
            $contextModification = 'AICARMINE TASK COMPLETE: verify all modifications, stage changes, run final verification. Use git diff to review before commit.'
        }
    }
} catch {
    Write-Error "[TaskComplete] Invalid JSON input: $($_.Exception.Message)"
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
