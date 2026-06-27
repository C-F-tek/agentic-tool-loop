function Get-AICarmineClineTaskBootstrap {
    [CmdletBinding()]
    param(
        [AllowEmptyString()]
        [string]$RawInput
    )

    try {
        if ([string]::IsNullOrWhiteSpace($RawInput)) {
            return @{ contextModification = '' }
        }

        $payload = $RawInput | ConvertFrom-Json -ErrorAction Stop
        if ($payload -isnot [System.Management.Automation.PSCustomObject]) {
            return @{ contextModification = '' }
        }

        $taskIdentity = $null
        foreach ($alias in @('taskId', 'task_id', 'taskID')) {
            $property = $payload.PSObject.Properties[$alias]
            if ($null -ne $property) {
                $taskIdentity = $property.Value
                break
            }
        }

        if ($taskIdentity -isnot [string]) {
            return @{ contextModification = '' }
        }
        if ($taskIdentity.Length -eq 0 -or $taskIdentity.Length -gt 512) {
            return @{ contextModification = '' }
        }
        if ([string]::IsNullOrWhiteSpace($taskIdentity)) {
            return @{ contextModification = '' }
        }

        # Extract .gitignore patterns for reindex scope (what to index vs skip)
        $gitignorePatterns = @()
        try {
            $gitignorePath = Join-Path $PWD '.gitignore'
            if ([IO.File]::Exists($gitignorePath)) {
                $gitignorePatterns = (Get-Content -LiteralPath $gitignorePath -Force -ErrorAction Stop) |
                    Where-Object { $_ -match '^\*.*\.|^\!|\.py$|\.ps1$|\.json$|\.md$' } |
                    Select-Object -First 50
            }
        } catch {}

        # Extract user prompt keywords from input
        $promptKeywords = ''
        try {
            if ($payload -is [System.Management.Automation.PSCustomObject]) {
                foreach ($key in @('message', 'prompt', 'userPrompt', 'input')) {
                    $prop = $payload.PSObject.Properties[$key]
                    if ($null -ne $prop -and $prop.Value -is [string]) {
                        $promptKeywords = ($prop.Value -split '\s|\.|,|;' | Where-Object { $_.Length -gt 3 } | Select-Object -First 20) -join ' '
                        break
                    }
                }
            }
        } catch {}

        $lines = @(
            'AICARMINE TASK BOOTSTRAP — operational directives only',
            '',
            'Scope:',
            '- Index only tracked git files matching .gitignore allowlist',
            "- Excluded patterns: $($gitignorePatterns -join ', ')",
            "- User prompt keywords: $promptKeywords",
            '',
            'Tools (use authoritative surface, not this list):',
            '- MCP search: aicarmine_repo_search_det (fd|rg|ast-grep|ctags)',
            '- MCP validate: aicarmine_repo_validate (ruff|pyright|semgrep)',
            '- MCP code: aicarmine_repo_code (structured_edit|apply_patch)',
            '- MCP RAG: aicarmine_rag (context|reindex) / aicarmine_index_bridge (query|build)',
            '- MCP batch: aicarmine_mcp_batch_proxy (mcp_batch_execute)',
            '- MCP memory: aicarmine_project_memory (search|upsert_verified)',
            '',
            'Rules:',
            '- Evidence > hypothesis. Verify with MCP before acting.',
            '- One failed tool → native fallback + report.',
            '- No agentic loop / subagent unless explicitly requested.',
            '- Do not invent files, APIs, symbols, or commits.'
        )

        $bootstrap = $lines -join [Environment]::NewLine
        if ($bootstrap.Length -gt 1800) {
            return @{ contextModification = '' }
        }
        return @{ contextModification = $bootstrap }
    }
    catch {
        return @{ contextModification = '' }
    }
}


function Get-AICarmineClineTaskResumeObservation {
    [CmdletBinding()]
    param(
        [AllowEmptyString()]
        [string]$RawInput
    )

    try {
        if ([string]::IsNullOrWhiteSpace($RawInput)) {
            return @{ contextModification = '' }
        }

        $observerRoot = $null
        try {
            $tempPath = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
            $ownerPath = [IO.Path]::GetFullPath([IO.Path]::Combine($tempPath, 'aicarmine-cline-hooks'))
            if ([IO.Directory]::Exists($ownerPath)) {
                $observerRoot = $ownerPath
            }
        } catch {}

        if ($null -eq $observerRoot) {
            # No observer root — do NOT inject any hint message during ongoing chat
            return @{ contextModification = '' }
        }

        try {
            $obsDir = Join-Path $observerRoot 'observations'
            $postObsDir = Join-Path $observerRoot 'post-observations'
            $routingFiles = @(Get-ChildItem -LiteralPath $observerRoot -Filter 'routing-*.json' -File -Force -ErrorAction Stop)

            $obsCount = 0
            $postObsCount = 0
            if ([IO.Directory]::Exists($obsDir)) {
                $obsCount = (Get-ChildItem -LiteralPath $obsDir -Filter 'observation-*.json' -File -Force -ErrorAction Stop).Count
            }
            if ([IO.Directory]::Exists($postObsDir)) {
                $postObsCount = (Get-ChildItem -LiteralPath $postObsDir -Filter 'post-observation-*.json' -File -Force -ErrorAction Stop).Count
            }
            $routingCount = @($routingFiles).Count

            # Read reindex status metadata from TaskComplete
            $hooksDir = $PSScriptRoot
            $metaFile = Join-Path $hooksDir 'reindex_status.json'
            $reindexMeta = $null
            if ([IO.File]::Exists($metaFile)) {
                try {
                    $reindexMeta = Get-Content -LiteralPath $metaFile -Force -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
                } catch {
                    $reindexMeta = $null
                }
            }

            # Only inject reindex status when we have actual observation data
            $hasObservations = ($obsCount -gt 0) -or ($postObsCount -gt 0)

            if ($hasObservations) {
                $contextModification = "AICARMINE TASK RESUME — session state appended to bootstrap:`n`n"
                $contextModification += "Observation archive (current session):`n"
                $contextModification += "- PreTool: $obsCount | PostTool: $postObsCount | Routing: $routingCount`n"
                $contextModification += "`n"

                # Inject reindex status metadata from TaskComplete
                if ($null -ne $reindexMeta) {
                    $contextModification += "Reindex status (from TaskComplete):`n"
                    $contextModification += "- Success: $($reindexMeta.success)`n"
                    $contextModification += "- Message: $($reindexMeta.message)`n"
                    $contextModification += "- Timestamp: $($reindexMeta.timestamp)`n"
                    if ($reindexMeta.success) {
                        $contextModification += "- Action: Reindex already completed; skip.`n"
                    } else {
                        $contextModification += "- Action: Reindex failed at TaskComplete; run mcp_batch_execute NOW.`n"
                    }
                }

                $contextModification += "`n"
                $contextModification += "Resume action:`n"
                $contextModification += "- Review recent tool outcomes for failure signals.`n"
                $contextModification += "- Do NOT re-run TaskStart bootstrap; use existing MCP routing from TaskStart."
            } else {
                # No observations — only inject reindex status if available
                if ($null -ne $reindexMeta) {
                    $contextModification = "Reindex status (from TaskComplete):`n"
                    $contextModification += "- Success: $($reindexMeta.success)`n"
                    $contextModification += "- Message: $($reindexMeta.message)`n"
                    $contextModification += "- Timestamp: $($reindexMeta.timestamp)`n"
                    if ($reindexMeta.success) {
                        $contextModification += "- Action: Reindex already completed; skip."
                    } else {
                        $contextModification += "- Action: Reindex failed at TaskComplete; run mcp_batch_execute NOW."
                    }
                } else {
                    # Nothing to inject — return empty
                    return @{ contextModification = '' }
                }
            }

            return @{ contextModification = $contextModification }
        } catch {
            return @{ contextModification = "AICARMINE TASK RESUME — session state unavailable; continue with existing bootstrap." }
        }
    } catch {
        return @{ contextModification = '' }
    }
}
