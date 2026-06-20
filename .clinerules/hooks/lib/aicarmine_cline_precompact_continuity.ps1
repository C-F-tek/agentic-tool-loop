# AICarmine Cline PreCompact bounded continuity helper

function New-AICarminePreCompactPacket {
    param(
        [string[]]$Classes,
        [string[]]$PreferredTools,
        [string[]]$Constraints,
        [object[]]$Failures,
        [int]$PendingCount
    )

    $failureLimit = [Math]::Min(3, @($Failures).Count)
    $secondaryLimit = [Math]::Min(3, [Math]::Max(0, @($Classes).Count - 1))
    $toolLimit = [Math]::Min(6, @($PreferredTools).Count)
    while ($true) {
        $lines = [Collections.Generic.List[string]]::new()
        [void]$lines.Add('AICARMINE COMPACTION CONTINUITY')
        [void]$lines.Add('')
        [void]$lines.Add('Task routing:')
        [void]$lines.Add(('- primary: {0}' -f $Classes[0]))
        $secondary = @($Classes | Select-Object -Skip 1 -First $secondaryLimit)
        $secondaryText = 'none'
        if ($secondary.Count -gt 0) { $secondaryText = [string]::Join(', ', $secondary) }
        [void]$lines.Add(('- secondary: {0}' -f $secondaryText))

        $selectedTools = @($PreferredTools | Select-Object -First $toolLimit)
        if ($selectedTools.Count -gt 0) {
            [void]$lines.Add('')
            [void]$lines.Add('Preferred MCP sequence:')
            for ($index = 0; $index -lt $selectedTools.Count; $index++) {
                [void]$lines.Add(('{0}. {1}' -f ($index + 1), $selectedTools[$index]))
            }
        }

        if (@($Constraints).Count -gt 0) {
            [void]$lines.Add('')
            [void]$lines.Add('Constraints:')
            foreach ($constraint in $Constraints) {
                [void]$lines.Add(('- {0}' -f $constraint))
            }
        }

        $selectedFailures = @($Failures | Select-Object -First $failureLimit)
        if ($selectedFailures.Count -gt 0) {
            [void]$lines.Add('')
            [void]$lines.Add('Observed recent failures:')
            foreach ($failure in $selectedFailures) {
                [void]$lines.Add(('- {0} | {1} | {2}' -f $failure.ToolIdentity, $failure.FailureSignal, $failure.AgeBucket))
            }
        }

        [void]$lines.Add('')
        [void]$lines.Add('Pending tool observations:')
        [void]$lines.Add(('- count: {0}' -f ([Math]::Min(32, [Math]::Max(0, $PendingCount)))))
        [void]$lines.Add('')
        [void]$lines.Add('Continuation rules:')
        [void]$lines.Add('- Continue from the current task boundary; do not restart completed work.')
        [void]$lines.Add('- Revalidate live repository/runtime state before any write.')
        [void]$lines.Add('- Do not repeat an unchanged call that has an observed failure.')
        [void]$lines.Add('- Native fallback requires a concrete observed MCP failure.')
        [void]$lines.Add('- Preserve read-only and no-write constraints after compaction.')

        $packet = [string]::Join([Environment]::NewLine, $lines.ToArray())
        if ($packet.Length -le 1800) { return $packet }
        if ($failureLimit -gt 2) {
            $failureLimit = 2
            continue
        }
        if ($secondaryLimit -gt 0) {
            $secondaryLimit--
            continue
        }
        if ($toolLimit -gt 0) {
            $toolLimit--
            continue
        }
        return ''
    }
}

function Get-AICarmineClinePreCompactContinuity {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput)

    $lockResult = $null
    $lockStatus = 'not_required'
    $lockWait = 0
    $stateFound = $false
    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        if ($null -eq $identity) {
            return [pscustomobject]@{
                ContextModification = ''
                StateFound = $false
                LockStatus = $lockStatus
                LockWaitMilliseconds = $lockWait
            }
        }
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) { throw 'observer_root_unavailable' }

        $snapshot = $null
        try {
            $lockResult = Enter-AICarmineTaskStateMutex -TaskKeySha256 $identity.TaskKeySha256
            $lockStatus = [string]$lockResult.Status
            $lockWait = [int]$lockResult.WaitMilliseconds
            if (-not $lockResult.Acquired) {
                return [pscustomobject]@{
                    ContextModification = ''
                    StateFound = $false
                    LockStatus = $lockStatus
                    LockWaitMilliseconds = $lockWait
                }
            }

            $stateResult = Get-AICarmineValidatedRoutingState -Root $root -TaskKeySha256 $identity.TaskKeySha256
            $stateFound = [bool]$stateResult.Found
            if ($stateFound) {
                $state = $stateResult.State
                $classes = [Collections.Generic.List[string]]::new()
                foreach ($className in @($state.classes | Select-Object -First 4)) {
                    $bounded = Get-AICarmineObserverBoundedName -Value $className
                    if (-not [string]::IsNullOrWhiteSpace($bounded)) { [void]$classes.Add($bounded) }
                }

                $tools = [Collections.Generic.List[string]]::new()
                foreach ($toolName in @($state.preferred_tools | Select-Object -First 6)) {
                    $bounded = Get-AICarmineObserverBoundedName -Value $toolName
                    if ($bounded.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase)) {
                        [void]$tools.Add($bounded)
                    }
                }

                $constraintOrder = @(Get-AICarmineRoutingConstraintOrder)
                $constraints = [Collections.Generic.List[string]]::new()
                foreach ($constraint in $constraintOrder) {
                    if (@($state.constraints) -contains $constraint) { [void]$constraints.Add($constraint) }
                }

                $pending = @(Get-AICarmineBoundedPendingCalls -Records $state.pending_tool_calls)
                $outcomes = @(Get-AICarmineBoundedRecentOutcomes -Records $state.recent_tool_outcomes)
                $failureCandidates = [Collections.Generic.List[object]]::new()
                foreach ($outcome in $outcomes) {
                    $age = Get-AICarmineObserverAgeSeconds -TimestampUtc $outcome.timestamp_utc
                    if ($outcome.outcome -ne 'failure' -or $null -eq $age -or $age -gt 600) { continue }
                    $toolIdentity = Get-AICarmineObserverBoundedName -Value $outcome.selected_mcp_tool_name
                    if ([string]::IsNullOrEmpty($toolIdentity)) {
                        $toolIdentity = Get-AICarmineObserverBoundedName -Value $outcome.selected_wrapper_tool_name
                    }
                    if ([string]::IsNullOrEmpty($toolIdentity)) { $toolIdentity = 'unknown_tool' }
                    $ageBucket = 'less_than_10m'
                    if ($age -lt 60) { $ageBucket = 'less_than_1m' }
                    elseif ($age -lt 300) { $ageBucket = 'less_than_5m' }
                    [void]$failureCandidates.Add([pscustomobject]@{
                        AgeSeconds = [int]$age
                        ToolIdentity = $toolIdentity
                        FailureSignal = [string]$outcome.failure_signal
                        AgeBucket = $ageBucket
                    })
                }
                $recentFailures = @($failureCandidates | Sort-Object AgeSeconds | Select-Object -First 3)
                $snapshot = [pscustomobject]@{
                    Classes = @($classes)
                    PreferredTools = @($tools)
                    Constraints = @($constraints)
                    PendingCount = [Math]::Min(32, $pending.Count)
                    Failures = @($recentFailures)
                }
            }
        }
        finally {
            Exit-AICarmineTaskStateMutex -Mutex $lockResult
            $lockResult = $null
        }

        if ($null -eq $snapshot -or @($snapshot.Classes).Count -eq 0) {
            return [pscustomobject]@{
                ContextModification = ''
                StateFound = $stateFound
                LockStatus = $lockStatus
                LockWaitMilliseconds = $lockWait
            }
        }
        $packet = New-AICarminePreCompactPacket -Classes $snapshot.Classes -PreferredTools $snapshot.PreferredTools -Constraints $snapshot.Constraints -Failures $snapshot.Failures -PendingCount $snapshot.PendingCount
        return [pscustomobject]@{
            ContextModification = [string]$packet
            StateFound = $stateFound
            LockStatus = $lockStatus
            LockWaitMilliseconds = $lockWait
        }
    }
    catch {
        return [pscustomobject]@{
            ContextModification = ''
            StateFound = $false
            LockStatus = $lockStatus
            LockWaitMilliseconds = $lockWait
        }
    }
    finally {
        if ($null -ne $lockResult) { Exit-AICarmineTaskStateMutex -Mutex $lockResult }
    }
}
