# TaskResume Hook
# PowerShell template for Windows hook execution.
# Handles task resumption with state recovery orchestration.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskResume' -RawInput $rawInput
    
    # Parse input for resumption state
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
        
        # Add resumption orchestration guidance for large-scale operations
        if ($taskIdentity) {
            $contextModification = 'AICARMINE TASK RESUME: recover operational state from project memory, check git status for pending changes, verify repository state before continuing multi-step operations.'
        }
    }
} catch {
    Write-Error "[TaskResume] Invalid JSON input: $($_.Exception.Message)"
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
