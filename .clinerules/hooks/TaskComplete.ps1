# TaskComplete Hook — AICarmine deterministic post-task cleanup
# Orchestrates observation archive summary, stale routing state purge, and reindex instructions.

try {
    $rawInput = [Console]::In.ReadToEnd()
    if ($rawInput) {
        $null = $rawInput | ConvertFrom-Json -ErrorAction Stop
    }
} catch {
    Write-Warning "[TaskComplete] Invalid JSON input: $($_.Exception.Message)"
    $rawInput = ''
}

$observerRoot = $null
try {
    $tempPath = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $ownerPath = [IO.Path]::GetFullPath([IO.Path]::Combine($tempPath, 'aicarmine-cline-hooks'))
    $observerPath = [IO.Path]::GetFullPath([IO.Path]::Combine($ownerPath, 'pretool-observer'))
    if ([IO.Directory]::Exists($observerPath)) {
        $observerRoot = $observerPath
    }
} catch {
    # Observer root unavailable — continue without observation archive.
}

$lines = @()

# ─── 1. Observation archive summary ─────────────────────────────────────
if ($null -ne $observerRoot) {
    try {
        $obsDir = [IO.Path]::Combine($observerRoot, 'observations')
        $postObsDir = [IO.Path]::Combine($observerRoot, 'post-observations')
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

        $lines += 'AICARMINE TASK COMPLETE — POST-TASK CLEANUP'
        $lines += ''
        $lines += 'Observation archive summary:'
        $lines += "- PreTool observations: $obsCount"
        $lines += "- PostTool observations: $postObsCount"
        $lines += "- Routing state files: $routingCount"
        $lines += ""
        $lines += "Action:"
        $lines += "- Observation archives are preserved for the session; they are read-only and do not affect Cline."
    } catch {
        $lines += "AICARMINE TASK COMPLETE — observation archive unavailable"
    }

    # ─── 2. Stale routing state purge (older than 24h) ──────────────────
    try {
        $cutoff = [DateTime]::UtcNow.AddHours(-24)
        $purged = 0
        foreach ($file in @(Get-ChildItem -LiteralPath $observerRoot -Filter 'routing-*.json' -File -Force -ErrorAction Stop)) {
            try {
                $item = Get-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                if ($item.LastWriteTimeUtc -lt $cutoff) {
                    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                    $purged++
                }
            } catch { continue }
        }
        if ($purged -gt 0) {
            $lines += ""
            $lines += "Stale routing state purged: $purged files removed (older than 24h)."
        }
    } catch {
        # Routing purge is advisory; do not block on failure.
    }
}

# ─── 3. Check existing reindex status from previous runs ──────────────
# Read any existing reindex_status.json to see if reindex was already done
$hooksDir = $PSScriptRoot
$metaFile = Join-Path $hooksDir 'reindex_status.json'
$existingStatus = $null
if ([IO.File]::Exists($metaFile)) {
    try {
        $existingStatus = Get-Content -LiteralPath $metaFile -Force -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        $existingStatus = $null
    }
}

$reindexStatus = [ordered]@{
    success     = $false
    timestamp   = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    results     = @()
    message     = "Reindex not yet executed — instructions output in contextModification"
}

if ($null -ne $existingStatus -and $existingStatus.success) {
    # Reindex was already done successfully
    $lines += ""
    $lines += "REINDEX STATUS: Already completed at $($existingStatus.timestamp)"
    $lines += "- Message: $($existingStatus.message)"
    $lines += "- No action needed."

    # Keep existing status file unchanged
    $reindexStatus = [ordered]@{
        success     = $true
        timestamp   = $existingStatus.timestamp
        results     = $existingStatus.results
        message     = $existingStatus.message
    }
} else {
    # Reindex not done or failed — output instructions
    $lines += ""
    $lines += "MANDATORY REINDEX BEFORE TASK END:"
    $lines += ""
    if ($null -ne $existingStatus -and -not $existingStatus.success) {
        $lines += "Previous reindex attempt failed. Retry now:"
    } else {
        $lines += "Execute the following mcp_batch_execute call NOW:"
    }
    $lines += ""
    $lines += "use_mcp_tool('aicarmine_mcp_batch_proxy', 'mcp_batch_execute', {"
    $lines += "  'operations': ["
    $lines += "    {'server': 'aicarmine_rag', 'tool': 'aicarmine_rag_reindex', 'args': {'source': 'git', 'mode': 'delta'}}, "
    $lines += "    {'server': 'aicarmine_repo_symbol_index', 'tool': 'aicarmine_repo_symbol_index_build', 'args': {}}, "
    $lines += "    {'server': 'aicarmine_index_bridge', 'tool': 'aicarmine_index_bridge_build', 'args': {}}, "
    $lines += "    {'server': 'aicarmine_wily', 'tool': 'wily_build', 'args': {'mode': 'delta'}}"
    $lines += "  ],"
    $lines += "  'compress': true"
    $lines += "})"
    $lines += ""
    $lines += "Do NOT end the task until reindex batch completes successfully."

    # Write updated metadata (still not done)
    $reindexStatus = [ordered]@{
        success     = $false
        timestamp   = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        results     = @()
        message     = "Reindex not yet executed — instructions output in contextModification"
    }
}

try {
    $hooksDir = $PSScriptRoot
    $metaFile = Join-Path $hooksDir 'reindex_status.json'
    $reindexStatus | ConvertTo-Json -Depth 3 -Compress | Set-Content -LiteralPath $metaFile -Force -ErrorAction Stop
} catch {
    Write-Warning "[TaskComplete] Metadata write failed: $_"
}

# ─── 5. Output ──────────────────────────────────────────────────────────
if ($lines.Count -gt 1500) {
    $lines = $lines[0..1499]
}

$output = [string]::Join([Environment]::NewLine, $lines)

# Collect any warnings that occurred during execution
$errorMessages = @()
try {
    # Check for observer root issues
    if ($null -eq $observerRoot) {
        $errorMessages += "Observer root not found — observation archive unavailable"
    }
} catch {
    $errorMessages += $_.Exception.Message
}

[ordered]@{
    cancel = $false
    contextModification = $output
    errorMessage = ($errorMessages -join '; ')
} | ConvertTo-Json -Compress
