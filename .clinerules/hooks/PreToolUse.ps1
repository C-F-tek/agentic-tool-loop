<<<<<<< HEAD
# [PreToolUse] Hook — MCP-First Enforcement v2
# Aggressive MCP tool priority with quantum/engineering awareness.
=======
# [PreToolUse] Hook
# PowerShell template for Windows hook execution.
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8

$rawInput = ''
$contextModification = ''
try {
    $rawInput = [Console]::In.ReadToEnd()
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_contract_probe.ps1')
    Write-AICarmineHookContractProbe -HookName 'PreToolUse' -RawInput $rawInput
<<<<<<< HEAD
    
    # Load MCP orchestrator for tool selection guidance
    . (Join-Path $PSScriptRoot 'lib\aicarmine_mcp_orchestrator.ps1')
    
=======
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
    . (Join-Path $PSScriptRoot 'lib\aicarmine_cline_pretool_observer.ps1')
    $observation = Get-AICarmineClinePreToolObservation -RawInput $rawInput
    if ($null -ne $observation -and $observation.contextModification -is [string]) {
        $contextModification = $observation.contextModification
    }
<<<<<<< HEAD
    
    # Additional MCP-first enforcement layer: detect native vs MCP tool selection
    $payload = ConvertFrom-Json -InputObject $rawInput -ErrorAction SilentlyContinue
    if ($null -ne $payload) {
        $wrapperTool = $null
        $propNames = @('toolName', 'tool_name', 'tool')
        foreach ($pn in $propNames) {
            if ($payload.PSObject.Properties[$pn]) {
                $wrapperTool = [string]$payload.($pn)
                break
            }
        }
        
        # Classify tool kind
        $selectedKind = 'unknown'
        if ($wrapperTool) {
            if ($wrapperTool.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase)) {
                $selectedKind = 'mcp'
            } else {
                $selectedKind = 'native'
            }
        }
        
        # Strong enforcement: warn on native tool selection for repo operations
        $nativeWriteTools = @('write_to_file', 'replace_in_file', 'edit_file')
        $nativeReadTools = @('read_file', 'search_files', 'list_files', 'execute_command')
        
        if ($selectedKind -eq 'native') {
            $isWriteOp = $nativeWriteTools -contains $wrapperTool
            $isReadOp = $nativeReadTools -contains $wrapperTool
            
            if ($isWriteOp -or $isReadOp) {
                $mcpHint = ''
                if ($isWriteOp) {
                    $mcpHint = 'MCP FIRST: This is a write operation. Use aicarmine_repo_apply_patch or aicarmine_repo_code_apply_patch instead of native tools. Native write_to_file/replace_in_file lack truncation control and Git integration.'
                } elseif ($isReadOp) {
                    $mcpHint = 'MCP FIRST: This is a read/search operation. Use aicarmine_repo_read, aicarmine_repo_search, or aicarmine_git_readonly_* instead of native tools. Native read_file/search_files lack structured output and bounded execution.'
                }
                
                if ($mcpHint) {
                    if ([string]::IsNullOrEmpty($contextModification)) {
                        $contextModification = $mcpHint
                    } else {
                        $contextModification += [Environment]::NewLine + $mcpHint
                    }
                }
            }
        }
    }
=======
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
}
catch {
    # Hooks are fail-open; probe or observer failures must not affect Cline.
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
