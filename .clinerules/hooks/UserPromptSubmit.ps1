# [UserPromptSubmit] Hook
# PowerShell template for Windows hook execution.

$rawInput = ''
$routingHint = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'UserPromptSubmit' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_mcp_router.ps1')
    $routingHint = Get-AICarmineMcpRoutingHint -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    [void](Write-AICarmineClineTaskRoutingState -RawInput $rawInput -RoutingHint $routingHint)
}
catch {
    # Hooks are fail-open; probe failures must not affect Cline.
    $routingHint = ''
}

[ordered]@{
    cancel = $false
    contextModification = $routingHint
    errorMessage = ''
} | ConvertTo-Json -Compress
