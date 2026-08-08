<<<<<<< HEAD
# [PostToolUse] Hook — MCP-First Enforcement v2
# Enhances post-tool observation with aggressive MCP validation and quantum awareness.
=======
# [PostToolUse] Hook
# PowerShell template for Windows hook execution.
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PostToolUse' -RawInput $rawInput
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_posttool_observer.ps1')
<<<<<<< HEAD
    . (Join-Path $PSScriptRoot 'lib\aicarmine_mcp_orchestrator.ps1')
    $observation = Get-AICarmineClinePostToolObservation -RawInput $rawInput
    if ($null -ne $observation) {
        $contextModification = [string]$observation.contextModification
        
        # Parse payload for tool classification
        $payload = ConvertFrom-Json -InputObject $rawInput -ErrorAction SilentlyContinue
        if ($null -ne $payload) {
            # Check for native tool success after MCP failure pattern
            $resultProp = $payload.PSObject.Properties['result']
            if ($null -ne $resultProp) {
                $resultText = [string]$resultProp.Value
                $isSuccess = $resultText -match '(?i)(success|ok=true|completed)'
                
                # Detect if a native tool succeeded where MCP was available
                $wrapperTool = $null
                $propNames = @('toolName', 'tool_name', 'tool')
                foreach ($pn in $propNames) {
                    if ($payload.PSObject.Properties[$pn]) {
                        $wrapperTool = [string]$payload.($pn)
                        break
                    }
                }
                
                # If native tool succeeded, reinforce that MCP should have been tried first
                if ($wrapperTool -notin @('aicarmine_*') -and $isSuccess) {
                    $mcpHint = 'POST-TOOL: Native tool succeeded but MCP equivalent was available. For future iterations, prefer MCP tools (aicarmine_repo_read, aicarmine_repo_search, aicarmine_git_readonly_*) over native tools (read_file, search_files, execute_command). MCP provides truncation control and structured output.'
                    if ([string]::IsNullOrEmpty($contextModification)) {
                        $contextModification = $mcpHint
                    } else {
                        $contextModification += [Environment]::NewLine + $mcpHint
                    }
                }
            }
            
            # Track orchestration state for large-scale operations
            if ($rawInput -match '(?i)(refactor|migration|orchestrate|large.?scale|multi.?module)') {
                $orchMsg = 'POST-TOOL: Track orchestration progress after tool execution. Verify integration points before proceeding to next module. Prefer MCP tools for each step in the sequence.'
                if ([string]::IsNullOrEmpty($contextModification)) {
                    $contextModification = $orchMsg
                } else {
                    $contextModification += [Environment]::NewLine + $orchMsg
                }
            }
        }
=======
    $observation = Get-AICarmineClinePostToolObservation -RawInput $rawInput
    if ($null -ne $observation) {
        $contextModification = [string]$observation.contextModification
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
    }
}
catch {
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
