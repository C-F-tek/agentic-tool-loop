# [TaskStart] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$bootstrap = ''
$errorMessages = @()
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskStart' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_task_bootstrap.ps1')
    $result = Get-AICarmineClineTaskBootstrap -RawInput $rawInput
    if ($null -ne $result -and $result.contextModification -is [string]) {
        $bootstrap = $result.contextModification
    }
}
catch {
    # Hooks are fail-open; bootstrap or probe failures must not affect Cline.
    $errorMessages += "TaskStart failed: $_"
    $bootstrap = ''
}

[ordered]@{
    cancel = $false
    contextModification = $bootstrap
    errorMessage = ($errorMessages -join '; ')
} | ConvertTo-Json -Compress
