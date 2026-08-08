# [PreCompact] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreCompact' -RawInput $rawInput
<<<<<<< HEAD
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_precompact_orchestrator.ps1')
    $observation = Get-AICarmineClinePreCompactObservation -RawInput $rawInput
    if ($null -ne $observation -and $observation.contextModification -is [string]) {
        $contextModification = $observation.contextModification
    }
}
catch {
    # Hooks are fail-open; probe or observer failures must not affect Cline.
=======
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_precompact_continuity.ps1')
    $result = Get-AICarmineClinePreCompactContinuity -RawInput $rawInput
    if ($null -ne $result -and $result.ContextModification -is [string]) {
        $contextModification = $result.ContextModification
    }
}
catch {
    # Hooks are fail-open; continuity failures must not affect Cline.
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
<<<<<<< HEAD
} | ConvertTo-Json -Compress
=======
} | ConvertTo-Json -Compress
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
