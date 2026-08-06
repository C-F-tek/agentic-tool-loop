# [PreCompact] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreCompact' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_precompact_orchestrator.ps1')
    $observation = Get-AICarmineClinePreCompactObservation -RawInput $rawInput
    if ($null -ne $observation -and $observation.contextModification -is [string]) {
        $contextModification = $observation.contextModification
    }
}
catch {
    # Hooks are fail-open; probe or observer failures must not affect Cline.
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress