# [PreToolUse] Hook
# PowerShell template for Windows hook execution.
# Enhanced with symbol injector for immediate tool comprehension.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreToolUse' -RawInput $rawInput
    
    # Primary: use existing pretool observer
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    $observation = Get-AICarmineClinePreToolObservation -RawInput $rawInput
    if ($null -ne $observation -and $observation.contextModification -is [string]) {
        $contextModification = $observation.contextModification
    }
    
    # Secondary: inject symbol context for immediate tool comprehension
    . (Join-Path $PSScriptRoot 'aicarmine_pretool_symbol_injector.ps1')
    $symbolInjection = Get-AICarminePreToolSymbolInjection -RawInput $rawInput
    if (-not [string]::IsNullOrWhiteSpace($symbolInjection)) {
        # Prepend symbol injection to existing context modification
        if ([string]::IsNullOrWhiteSpace($contextModification)) {
            $contextModification = $symbolInjection
        }
        else {
            $contextModification = $symbolInjection + "`n" + $contextModification
        }
    }
}
catch {
    # Hooks are fail-open; probe, observer, or injector failures must not affect Cline.
    $contextModification = ''
}

[ordered]@{
    cancel = $false
    contextModification = $contextModification
    errorMessage = ''
} | ConvertTo-Json -Compress
