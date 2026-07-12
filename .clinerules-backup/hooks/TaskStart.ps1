# [TaskStart] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$bootstrap = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'TaskStart' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_task_bootstrap.ps1')
    $bootstrap = Get-AICarmineClineTaskBootstrap -RawInput $rawInput
}
catch {
    # Hooks are fail-open; bootstrap or probe failures must not affect Cline.
    $bootstrap = ''
}

[ordered]@{
    cancel = $false
    contextModification = $bootstrap
    errorMessage = ''
} | ConvertTo-Json -Compress
