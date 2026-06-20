# [PostToolUse] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PostToolUse' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_posttool_observer.ps1')
    $observation = Get-AICarmineClinePostToolObservation -RawInput $rawInput
    if ($null -ne $observation) {
        $contextModification = [string]$observation.contextModification
    }
}
catch {
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
