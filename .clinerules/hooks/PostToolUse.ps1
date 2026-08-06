# [PostToolUse] Hook
# PowerShell template for Windows hook execution.
# Enhances post-tool observation with orchestration state tracking.

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PostToolUse' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_posttool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_mcp_orchestrator.ps1')
    $observation = Get-AICarmineClinePostToolObservation -RawInput $rawInput
    if ($null -ne $observation) {
        $contextModification = [string]$observation.contextModification
        
        # Add orchestration state tracking for large-scale operations
        if ($rawInput -match '(?i)(refactor|migration|orchestrate|large.?scale|multi.?module)') {
            $contextModification += [Environment]::NewLine
            $contextModification += 'AICARMINE POST-TOOL: track orchestration progress after tool execution. Verify integration points before proceeding to next module.'
        }
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
