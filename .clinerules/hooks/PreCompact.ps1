# [PreCompact] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreCompact' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_precompact_continuity.ps1')
    $result = Get-AICarmineClinePreCompactContinuity -RawInput $rawInput
    if ($null -ne $result -and $result.ContextModification -is [string]) {
        $contextModification = $result.ContextModification
    }
}
catch {
    # Hooks are fail-open; continuity failures must not affect Cline.
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
