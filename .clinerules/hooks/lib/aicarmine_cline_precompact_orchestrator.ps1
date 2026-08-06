# AICarmine Cline PreCompact orchestrator helper
# Coordinates cleanup and state consolidation after large-scale operations.

function Get-AICarmineClinePreCompactObservation {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput)

    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $taskIdentity = $null
        foreach ($alias in @('taskId', 'task_id', 'taskID')) {
            $property = $payload.PSObject.Properties[$alias]
            if ($null -ne $property) {
                $taskIdentity = $property.Value
                break
            }
        }

        if ($taskIdentity -isnot [string] -or [string]::IsNullOrWhiteSpace($taskIdentity)) {
            return [pscustomobject]@{ contextModification = ''; observation = $null }
        }

        $messages = [Collections.Generic.List[string]]::new()
        $codes = [Collections.Generic.List[string]]::new()

        # Check for large-scale operation completion indicators
        $hasPendingChanges = $false
        $hasUnverifiedModifications = $false
        $hasIncompleteOrchestration = $false

        # Analyze payload for orchestration state
        foreach ($prop in $payload.PSObject.Properties) {
            $name = $prop.Name.ToLowerInvariant()
            if ($name -match 'pending|unverified|incomplete|rollback') {
                if ($prop.Value -is [string] -and $prop.Value -match 'true|yes|pending|incomplete') {
                    switch ($name) {
                        'pending' { $hasPendingChanges = $true }
                        'unverified' { $hasUnverifiedModifications = $true }
                        'incomplete' { $hasIncompleteOrchestration = $true }
                    }
                }
            }
        }

        if ($hasPendingChanges) {
            [void]$codes.Add('pending_changes_before_compact')
            [void]$messages.Add('AICARMINE PRE-COMPACT: pending changes detected. Ensure all modifications are staged and verified before context compaction.')
        }

        if ($hasUnverifiedModifications) {
            [void]$codes.Add('unverified_modifications')
            [void]$messages.Add('AICARMINE PRE-COMPACT: unverified modifications detected. Run targeted verification before compacting context.')
        }

        if ($hasIncompleteOrchestration) {
            [void]$codes.Add('incomplete_orchestration')
            [void]$messages.Add('AICARMINE PRE-COMPACT: incomplete orchestration detected. Complete multi-step operations before context compaction.')
        }

        # Add MCP-first reminder for cleanup operations
        [void]$messages.Add('AICARMINE PRE-COMPACT: Use MCP tools (aicarmine_repo_read, aicarmine_git_readonly_*) for cleanup verification instead of native tools.')

        $contextModification = [string]::Join([Environment]::NewLine, @($messages | Select-Object -Unique | Select-Object -First 3))
        if ($contextModification.Length -gt 900) {
            $contextModification = $contextModification.Substring(0, 900)
        }

        $observation = [ordered]@{
            schema = 'aicarmine.cline.precompact-orchestrator.v1'
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            task_key_sha256 = (Get-AICarmineObserverSha256 -Text $taskIdentity)
            pending_changes = $hasPendingChanges
            unverified_modifications = $hasUnverifiedModifications
            incomplete_orchestration = $hasIncompleteOrchestration
            advisory_codes = @($codes)
            context_modification_emitted = -not [string]::IsNullOrEmpty($contextModification)
        }

        return [pscustomobject]@{
            contextModification = $contextModification
            observation = [pscustomobject]$observation
        }
    }
    catch {
        return [pscustomobject]@{ contextModification = ''; observation = $null }
    }
}

function Get-AICarmineObserverSha256 {
    param([AllowEmptyString()][string]$Text)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Text)
        return (($sha256.ComputeHash($bytes) | ForEach-Object { '{0:x2}' -f $_ }) -join '')
    }
    finally {
        $sha256.Dispose()
    }
}