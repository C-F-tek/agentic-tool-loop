# [PreToolUse] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreToolUse' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    $observation = Get-AICarmineClinePreToolObservation -RawInput $rawInput
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
