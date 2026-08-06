# TaskCancel Hook
# PowerShell template for Windows hook execution.
# Handles task cancellation with cleanup orchestration.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskCancel' -RawInput $rawInput
    
    # Parse input for cancellation state
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
        
        # Add cleanup orchestration guidance for cancelled large-scale operations
        if ($taskIdentity) {
            $contextModification = 'AICARMINE TASK CANCEL: pending changes should be staged or reverted. Use git stash for uncommitted work when cancelling mid-operation.'
        }
    }
} catch {
    Write-Error "[TaskCancel] Invalid JSON input: $($_.Exception.Message)"
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
