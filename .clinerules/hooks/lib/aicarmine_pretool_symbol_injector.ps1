# AICarmine Pre-Tool Call Symbol Injector (Compact Mode)
# Injects minimal structured tool context to reduce token usage.
# Uses .docs/mcp_routing_table.json for compact intent-based lookup.

function Get-AICarminePreToolSymbolInjection {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput,

        [Parameter(Mandatory = $false)]
        [string]$SymbolReferencePath,

        [Parameter(Mandatory = $false)]
        [string]$RoutingTablePath
    )

    Set-StrictMode -Version 2.0

    if ([string]::IsNullOrWhiteSpace($RawInput)) {
        return ''
    }

    # Load routing table (compact, ~8KB)
    $routingTable = $null
    if ([string]::IsNullOrWhiteSpace($RoutingTablePath)) {
        $possiblePaths = @(
            (Join-Path $PSScriptRoot '../../../.docs/mcp_routing_table.json'),
            (Join-Path $PSScriptRoot '../../../../.docs/mcp_routing_table.json'),
            (Join-Path $env:USERPROFILE 'agentic-tool-loop/.docs/mcp_routing_table.json')
        )
        foreach ($path in $possiblePaths) {
            if (Test-Path -LiteralPath $path -ErrorAction SilentlyContinue) {
                $RoutingTablePath = $path
                break
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($RoutingTablePath)) {
        try {
            $routingTable = Get-Content -LiteralPath $RoutingTablePath -Raw -ErrorAction Stop | ConvertFrom-Json
        }
        catch {
            return ''
        }
    }

    # Extract tool name from input
    $toolName = $null
    try {
        $parsed = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        if ($null -ne $parsed.tools -and $parsed.tools.Count -gt 0) {
            $tool = $parsed.tools[0]
            $toolName = $tool.name ?? $tool.tool ?? $tool.function_name
        }
        elseif ($null -ne $parsed.tool) {
            $toolName = $parsed.tool.name ?? $parsed.tool
        }
        elseif ($null -ne $parsed.tool_name) {
            $toolName = $parsed.tool_name
        }
    }
    catch {
        return ''
    }

    if ([string]::IsNullOrWhiteSpace($toolName)) {
        return ''
    }

    $toolNameStr = [string]$toolName

    # Build compact injection
    $injectionParts = @()
    $injectionParts += "TOOL_CONTEXT:"
    $injectionParts += "  name: $toolNameStr"

    # Try routing table lookup first
    if ($null -ne $routingTable -and $null -ne $routingTable.routing_rules) {
        $matchedRule = $null
        foreach ($rule in $routingTable.routing_rules) {
            if ($rule.tool -eq $toolNameStr) {
                $matchedRule = $rule
                break
            }
        }

        if ($null -ne $matchedRule) {
            $injectionParts += "  server: $($matchedRule.server)"
            $injectionParts += "  params: $($matchedRule.params)"
        }
    }

    # Fallback to symbol reference for category info
    if ([string]::IsNullOrWhiteSpace($SymbolReferencePath)) {
        $possiblePaths = @(
            (Join-Path $PSScriptRoot '../../../.docs/tool_symbol_reference.json'),
            (Join-Path $PSScriptRoot '../../../../.docs/tool_symbol_reference.json')
        )
        foreach ($path in $possiblePaths) {
            if (Test-Path -LiteralPath $path -ErrorAction SilentlyContinue) {
                $SymbolReferencePath = $path
                break
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($SymbolReferencePath)) {
        try {
            $symbolRef = Get-Content -LiteralPath $SymbolReferencePath -Raw -ErrorAction Stop | ConvertFrom-Json
            foreach ($entry in $symbolRef.tool_entries) {
                if ([string]$entry.tool_name -eq $toolNameStr) {
                    $injectionParts += "  category: $([string]$entry.category)"
                    $injectionParts += "  read_only: $([bool]$entry.read_only)"
                    if ($entry.confirmation_required) {
                        $injectionParts += "  confirmation_gate: $([string]$entry.confirmation_gate)"
                    }
                    break
                }
            }
        }
        catch {
            # Fail open
        }
    }

    return [string]::Join('', $injectionParts)
}

function Get-AICarminePreToolSymbolObservation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    $injection = Get-AICarminePreToolSymbolInjection -RawInput $RawInput
    return [pscustomobject]@{
        contextModification = $injection
    }
}