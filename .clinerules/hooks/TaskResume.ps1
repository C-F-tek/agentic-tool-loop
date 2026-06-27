# [TaskResume] Hook
# PowerShell template for Windows hook execution.
# Restores task context when Cline resumes a paused/interrupted task.

$rawInput = ''
$contextModification = ''
$errorMessages = @()
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskResume' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_task_bootstrap.ps1')
    $observation = Get-AICarmineClineTaskResumeObservation -RawInput $rawInput
    if ($null -ne $observation -and $observation.contextModification -is [string]) {
        $contextModification = $observation.contextModification
    }
} catch {
    # Hooks are fail-open; resume failures must not affect Cline.
    $errorMessages += "TaskResume failed: $_"
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ($errorMessages -join '; ')
} | ConvertTo-Json -Compress
