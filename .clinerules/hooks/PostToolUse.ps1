# [PostToolUse] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PostToolUse' -RawInput $rawInput
}
catch {
    # Hooks are fail-open; probe failures must not affect Cline.
}

[ordered]@{
    cancel = $false
    contextModification = ''
    errorMessage = ''
} | ConvertTo-Json -Compress
