# AICarmine Pre-Tool Call Symbol Injector
# Injects structured tool context into the prompt before tool execution.
# This enables immediate symbol comprehension without thinking overhead.

function Get-AICarminePreToolSymbolInjection {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput,

        [Parameter(Mandatory = $false)]
        [string]$SymbolReferencePath
    )

    Set-StrictMode -Version 2.0

    if ([string]::IsNullOrWhiteSpace($RawInput)) {
        return ''
    }

    # If SymbolReferencePath not provided, try default locations
    if ([string]::IsNullOrWhiteSpace($SymbolReferencePath)) {
        $possiblePaths = @(
            (Join-Path $PSScriptRoot '../../../.docs/tool_symbol_reference.json'),
            (Join-Path $PSScriptRoot '../../../../.docs/tool_symbol_reference.json'),
            (Join-Path $env:USERPROFILE 'agentic-tool-loop/.docs/tool_symbol_reference.json')
        )
        foreach ($path in $possiblePaths) {
            if (Test-Path -LiteralPath $path -ErrorAction SilentlyContinue) {
                $SymbolReferencePath = $path
                break
            }
        }
    }

    $symbolRef = $null
    if (-not [string]::IsNullOrWhiteSpace($SymbolReferencePath)) {
        try {
            $symbolRef = Get-Content -LiteralPath $SymbolReferencePath -Raw -ErrorAction Stop | ConvertFrom-Json
        }
        catch {
            # Fail open: symbol injection is optional
            return ''
        }
    }

    $parsedInput = $null
    try {
        $parsedInput = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
    }
    catch {
        return ''
    }

    # Extract tool name and arguments
    $toolName = $null
    $toolArgs = @{}

    # Handle different input formats
    if ($null -ne $parsedInput.tools) {
        $tools = $parsedInput.tools
        if ($tools -is [System.Array] -and $tools.Count -gt 0) {
            $tool = $tools[0]
            if ($null -ne $tool) {
                $toolName = Get-AICarmineObserverProperty -Value $tool -Names @('name', 'tool', 'function_name')
                $toolArgsObj = Get-AICarmineObserverProperty -Value $tool -Names @('arguments', 'input', 'parameters')
                if ($null -ne $toolArgsObj) {
                    $toolArgs = $toolArgsObj
                }
            }
        }
    }
    elseif ($null -ne $parsedInput.tool) {
        $toolName = Get-AICarmineObserverProperty -Value $parsedInput -Names @('tool', 'name')
        $toolArgsObj = Get-AICarmineObserverProperty -Value $parsedInput -Names @('arguments', 'input', 'parameters')
        if ($null -ne $toolArgsObj) {
            $toolArgs = $toolArgsObj
        }
    }
    elseif ($null -ne $parsedInput.tool_name) {
        $toolName = $parsedInput.tool_name
        $toolArgsObj = Get-AICarmineObserverProperty -Value $parsedInput -Names @('arguments', 'input', 'parameters', 'args')
        if ($null -ne $toolArgsObj) {
            $toolArgs = $toolArgsObj
        }
    }

    if ([string]::IsNullOrWhiteSpace($toolName)) {
        return ''
    }

    $toolNameStr = [string]$toolName

    # Build injection context from symbol reference
    $injectionParts = @()

    if ($null -ne $symbolRef -and $null -ne $symbolRef.tool_entries) {
        # Find matching tool entry
        $toolEntry = $null
        foreach ($entry in $symbolRef.tool_entries) {
            if ([string]$entry.tool_name -eq $toolNameStr) {
                $toolEntry = $entry
                break
            }
        }

        if ($null -ne $toolEntry) {
            $category = [string]$toolEntry.category
            $description = [string]$toolEntry.description
            $readOnly = [bool]$toolEntry.read_only
            $confirmationRequired = [bool]$toolEntry.confirmation_required

            # Build injection block
            $injectionParts += "TOOL_CONTEXT:"
            $injectionParts += "  name: $toolNameStr"
            $injectionParts += "  category: $category"
            $injectionParts += "  description: $description"
            $injectionParts += "  read_only: $readOnly"

            if ($confirmationRequired) {
                $gate = [string]$toolEntry.confirmation_gate
                $injectionParts += "  confirmation_required: true"
                $injectionParts += "  confirmation_gate: $gate"
            }

            # Add related tools if available
            if ($null -ne $toolEntry.related_tools -and $toolEntry.related_tools.Count -gt 0) {
                $related = [string]::join(', ', $toolEntry.related_tools)
                $injectionParts += "  related_tools: $related"
            }

            # Add common parameter hints based on category
            $categoryLower = $category.ToLowerInvariant()
            if ($categoryLower -match '^repo/(read|list|search)') {
                $injectionParts += "  common_params: path, max_chars"
            }
            elseif ($categoryLower -match '^job/') {
                $injectionParts += "  common_params: job_id"
            }
            elseif ($categoryLower -match '^memory/') {
                $injectionParts += "  common_params: query, scope, key"
            }
            elseif ($categoryLower -match '^validate/') {
                $injectionParts += "  common_params: path, timeout_seconds"
            }
        }
        else {
            # Tool not in reference, provide minimal context
            $injectionParts += "TOOL_CONTEXT:"
            $injectionParts += "  name: $toolNameStr"
            $injectionParts += "  category: unknown"
            $injectionParts += "  description: Tool not in symbol reference - verify via MCP tools/list"
            $injectionParts += "  read_only: true"
        }
    }
    else {
        # No symbol reference available, provide minimal context
        $injectionParts += "TOOL_CONTEXT:"
        $injectionParts += "  name: $toolNameStr"
        $injectionParts += "  category: unknown"
        $injectionParts += "  description: Symbol reference not available"
        $injectionParts += "  read_only: true"
    }

    # Format as compact injection string
    $injection = [string]::Join('', $injectionParts)
    return $injection
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