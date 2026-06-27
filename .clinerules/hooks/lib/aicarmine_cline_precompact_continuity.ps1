# AICarmine Cline PreCompact continuity helper
# Preserves task context across Cline context compaction (conversation truncation).
# When Cline compacting the conversation, this hook injects a compacted-context
# summary so the agent retains MCP routing state, observation counts, and
# index freshness status after truncation.

function Get-AICarmineObserverRoot {
    param()
    try {
        $tempPath = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        $ownerPath = [IO.Path]::GetFullPath([IO.Path]::Combine($tempPath, 'aicarmine-cline-hooks'))
        if ([IO.Directory]::Exists($ownerPath)) { return $ownerPath }
    } catch {}
    return $null
}

function Get-AICarmineBoundedRecentOutcomes {
    param([object[]]$Records)
    if ($null -eq $Records) { return @() }
    $arr = @($Records | Where-Object { $_ -ne $null })
    if ($arr.Count -gt 32) { $arr = $arr[-32..($arr.Count - 1)] }
    return $arr
}

function Get-AICarmineBoundedPendingCalls {
    param([object[]]$Records)
    if ($null -eq $Records) { return @() }
    $arr = @($Records | Where-Object { $_ -ne $null })
    if ($arr.Count -gt 32) { $arr = $arr[-32..($arr.Count - 1)] }
    return $arr
}

function Get-AICarmineObserverPropertyMatch {
    param([object]$Value, [string[]]$Names)

    if ($null -eq $Value -or $null -eq $Names) {
        return [pscustomobject]@{ Found = $false; Value = $null; PropertyName = '' }
    }

    foreach ($name in $Names) {
        try {
            $prop = $Value.PSObject.Properties | Where-Object { $_.Name -eq $name }
            if ($null -ne $prop -and $null -ne $prop.Value) {
                return [pscustomobject]@{ Found = $true; Value = $prop.Value; PropertyName = $name }
            }
        } catch {}
    }
    return [pscustomobject]@{ Found = $false; Value = $null; PropertyName = '' }
}

function Get-AICarmineObserverSha256 {
    param([string]$Text)
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $hash = $sha.ComputeHash($bytes)
        $sha.Dispose()
        $hex = -join ($hash | ForEach-Object { '{0:x2}' -f $_ })
        return $hex.Substring(0, 16)
    } catch { return 'sha256_unavailable' }
}

function Get-AICarmineTaskIdentity {
    param([object]$Payload)

    if ($null -eq $Payload -or $null -eq $Payload.PSObject.TypeName) {
        return $null
    }

    $taskKey = $null
    foreach ($alias in @('taskId', 'task_id', 'taskID')) {
        $prop = $Payload.PSObject.Properties[$alias]
        if ($null -ne $prop) { $taskKey = [string]$prop.Value; break }
    }

    if ([string]::IsNullOrEmpty($taskKey)) { return $null }

    $sha = Get-AICarmineObserverSha256 -Text $taskKey
    return [pscustomobject]@{ TaskKeySha256 = $sha }
}

function Write-AICarmineObserverJson {
    param([string]$Path, [object]$Value)
    try {
        $dir = [IO.Path]::GetDirectoryName($Path)
        if (-not [IO.Directory]::Exists($dir)) { New-Item -LiteralPath $dir -ItemType Directory -Force -ErrorAction Stop | Out-Null }
        $Value | ConvertTo-Json -Compress -Depth 8 | Set-Content -LiteralPath $Path -NoNewline -ErrorAction Stop
    } catch {}
}

function Get-AICarmineObserverChildDirectory {
    param([string]$Root, [string]$Name)
    try {
        $dir = Join-Path $Root $Name
        if ([IO.Directory]::Exists($dir)) { return $dir }
        New-Item -LiteralPath $dir -ItemType Directory -Force -ErrorAction Stop | Out-Null
        return $dir
    } catch { return $null }
}

function Write-AICarmineObserverJsonAtomic {
    param([string]$Root, [string]$Path, [object]$Value)
    try {
        $tempPath = "$Path.tmp.$$"
        Write-AICarmineObserverJson -Path $tempPath -Value $Value
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        Rename-Item -LiteralPath $tempPath -NewName ([IO.Path]::GetFileName($Path)) -Force -ErrorAction Stop
    } catch {}
}

function Enter-AICarmineTaskStateMutex {
    param([string]$TaskKeySha256)
    return [pscustomobject]@{ Status = 'not_implemented'; Acquired = $true; WaitMilliseconds = 0 }
}

function Exit-AICarmineTaskStateMutex {
    param([object]$Mutex)
    # No-op for non-mutex implementation
}

function Get-AICarmineValidatedRoutingState {
    param([string]$Root, [string]$TaskKeySha256)
    try {
        $path = Join-Path $Root "routing-$TaskKeySha256.json"
        if ([IO.File]::Exists($path)) {
            $json = [IO.File]::ReadAllText($path)
            $state = $json | ConvertFrom-Json -ErrorAction Stop
            return [pscustomobject]@{ Found = $true; State = $state; Path = $path }
        }
    } catch {}
    return [pscustomobject]@{ Found = $false; State = $null; Path = '' }
}

function Get-AICarmineToolCallMetadata {
    param([object]$Payload)

    $toolKind = ''
    $wrapperName = ''
    $mcpServer = ''
    $mcpTool = ''
    $invocationSha = ''
    $callSha = ''

    try {
        $kindMatch = Get-AICarmineObserverPropertyMatch -Value $Payload -Names @('tool', 'tool_kind', 'selected_tool_kind')
        if ($kindMatch.Found -and $kindMatch.Value -is [string]) { $toolKind = [string]$kindMatch.Value }

        $serverMatch = Get-AICarmineObserverPropertyMatch -Value $Payload -Names @('mcp_server_name', 'mcpServerName', 'server')
        if ($serverMatch.Found -and $serverMatch.Value -is [string]) { $mcpServer = [string]$serverMatch.Value }

        $toolMatch = Get-AICarmineObserverPropertyMatch -Value $Payload -Names @('mcp_tool_name', 'mcpToolName', 'tool_name', 'tool_name')
        if ($toolMatch.Found -and $toolMatch.Value -is [string]) { $mcpTool = [string]$toolMatch.Value }
    } catch {}

    return [pscustomobject]@{
        SelectedToolKind = $toolKind
        SelectedWrapperToolName = $wrapperName
        SelectedMcpServerName = $mcpServer
        SelectedMcpToolName = $mcpTool
        InvocationKeySha256 = $invocationSha
        ToolCallSha256 = $callSha
    }
}

function Get-AICarmineClinePreCompactContinuity {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput)

    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) { throw 'observer_root_unavailable' }

        $taskKey = ''
        if ($null -ne $identity) { $taskKey = $identity.TaskKeySha256 }

        # Load routing state to extract observation counts and index freshness
        $stateResult = Get-AICarmineValidatedRoutingState -Root $root -TaskKeySha256 $taskKey
        $recentOutcomes = @()
        $pendingCalls = @()
        $observationCounts = @{ pre = 0; post = 0 }
        $indexFreshness = 'unknown'

        if ($stateResult.Found) {
            $state = $stateResult.State
            $recentOutcomes = @(Get-AICarmineBoundedRecentOutcomes -Records $state.recent_tool_outcomes)
            $pendingCalls = @(Get-AICarmineBoundedPendingCalls -Records $state.pending_tool_calls)

            # Count observations from archived files
            try {
                $obsDir = Join-Path $root 'observations'
                $postObsDir = Join-Path $root 'post-observations'
                if ([IO.Directory]::Exists($obsDir)) {
                    $observationCounts.pre = (Get-ChildItem -LiteralPath $obsDir -Filter 'observation-*.json' -File -Force -ErrorAction Stop).Count
                }
                if ([IO.Directory]::Exists($postObsDir)) {
                    $observationCounts.post = (Get-ChildItem -LiteralPath $postObsDir -Filter 'post-observation-*.json' -File -Force -ErrorAction Stop).Count
                }
            } catch {}

            # Check index freshness from task metadata
            try {
                if ($null -ne $state.index_rag_fresh -and $state.index_rag_fresh -is [bool]) {
                    if ($state.index_rag_fresh) { $indexFreshness = 'fresh' } else { $indexFreshness = 'stale' }
                }
            } catch {}
        }

        # Count failure signals from recent outcomes
        $failureCount = 0
        foreach ($outcome in $recentOutcomes) {
            if ($null -ne $outcome.failure_signal -and $outcome.failure_signal -ne 'none') { $failureCount++ }
        }

        # Build compact context summary for post-compaction continuity
        $summaryParts = @()
        $summaryParts += "AICARMINE PRE-COMPACT CONTINUITY"
        $summaryParts += ""
        $summaryParts += "Task context preserved across Cline compaction:"
        $summaryParts += "- Observation counts: pre=$($observationCounts.pre), post=$($observationCounts.post)"
        $summaryParts += "- Recent outcomes tracked: $($recentOutcomes.Count) (failures: $failureCount)"
        $summaryParts += "- Pending calls retained: $($pendingCalls.Count)"
        $summaryParts += "- Index freshness: $indexFreshness"

        if ($failureCount -gt 0) {
            $summaryParts += ""
            $summaryParts += "WARNING: $failureCount recent failure signal(s) detected. Do not repeat identical tool calls unchanged."
            $summaryParts += "Diagnose the failing stage before selecting a fallback."
        }

        if ($indexFreshness -eq 'stale' -or $indexFreshness -eq 'unknown') {
            $summaryParts += ""
            $summaryParts += "Index note: RAG/Symbol/Bridge indexes may be stale after source modifications."
            $summaryParts += "Consider running batch reindex: mcp_batch_execute with aicarmine_rag_reindex + symbol_index_build + bridge_build"
        }

        $contextModification = [string]::Join([Environment]::NewLine, $summaryParts)
        if ($contextModification.Length -gt 1500) {
            $contextModification = $contextModification.Substring(0, 1500)
        }

        return [pscustomobject]@{ contextModification = $contextModification; observation = $null }
    }
    catch {
        return [pscustomobject]@{ contextModification = ''; observation = $null }
    }
}