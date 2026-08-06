# [UserPromptSubmit] Hook
# PowerShell template for Windows hook execution.
# Enhances MCP routing with large-scale operation awareness.

$rawInput = ''
$routingHint = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'UserPromptSubmit' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_mcp_router.ps1')
    $routingHint = Get-AICarmineMcpRoutingHint -RawInput $rawInput
    
    # Add large-scale operation routing hints if task involves multi-module changes
    if ($rawInput -match '(?i)(refactor|migration|orchestrate|large.?scale|multi.?module|codebase|system.?level)') {
        $routingHint += [Environment]::NewLine
        $routingHint += 'Task classes: large-scale-operation, multi-module-refactoring, system-engineering'
        $routingHint += [Environment]::NewLine
        $routingHint += 'Preferred sequence:'
        $routingHint += '1. aicarmine_repo_tree => full structure mapping'
        $routingHint += '2. aicarmine_repo_search => dependency discovery'
        $routingHint += '3. aicarmine_git_readonly_log => history navigation'
        $routingHint += '4. aicarmine_rag_context => semantic orientation'
        $routingHint += [Environment]::NewLine
        $routingHint += 'Constraints:'
        $routingHint += '- Read-only analysis before execution'
    }
    
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
