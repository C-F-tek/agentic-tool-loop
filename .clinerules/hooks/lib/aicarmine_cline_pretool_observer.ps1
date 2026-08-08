# AICarmine Cline PreToolUse observe-only helper

function Get-AICarmineObserverProperty {
    param($Value, [string[]]$Names)

    if ($null -eq $Value -or $Value -is [string]) {
        return $null
    }
    $properties = @($Value.PSObject.Properties)
    $limit = [Math]::Min($properties.Count, 32)
    for ($index = 0; $index -lt $limit; $index++) {
        foreach ($name in $Names) {
            if ([string]::Equals([string]$properties[$index].Name, $name, [StringComparison]::OrdinalIgnoreCase)) {
                return $properties[$index].Value
            }
        }
    }
    return $null
}

function Get-AICarmineObserverPropertyMatch {
    param($Value, [string[]]$Names)

    if ($null -eq $Value -or $Value -is [string]) {
        return [pscustomobject]@{ Found = $false; Value = $null }
    }
    $properties = @($Value.PSObject.Properties)
    $limit = [Math]::Min($properties.Count, 32)
    for ($index = 0; $index -lt $limit; $index++) {
        foreach ($name in $Names) {
            if ([string]::Equals([string]$properties[$index].Name, $name, [StringComparison]::OrdinalIgnoreCase)) {
                return [pscustomobject]@{ Found = $true; Value = $properties[$index].Value }
            }
        }
    }
    return [pscustomobject]@{ Found = $false; Value = $null }
}

$script:AICarmineTaskStateMutexTimeoutMilliseconds = 5000
$script:AICarmineObserverBeforeAtomicCommitTestHook = $null

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

function Enter-AICarmineTaskStateMutex {
    param([string]$TaskKeySha256)

    $mutex = $null
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $mutex = New-Object Threading.Mutex($false, ('Local\AICarmineClinePreTool-{0}' -f $TaskKeySha256))
        $acquired = $false
        $status = 'timeout'
        try {
            $acquired = $mutex.WaitOne($script:AICarmineTaskStateMutexTimeoutMilliseconds)
            if ($acquired) { $status = 'acquired' }
        }
        catch [Threading.AbandonedMutexException] {
            $acquired = $true
            $status = 'abandoned_acquired'
        }
        $stopwatch.Stop()
        $wait = [Math]::Min($script:AICarmineTaskStateMutexTimeoutMilliseconds, [Math]::Max(0, [int]$stopwatch.ElapsedMilliseconds))
        if (-not $acquired) {
            $mutex.Dispose()
            $mutex = $null
        }
        return [pscustomobject]@{ Acquired = $acquired; Mutex = $mutex; Status = $status; WaitMilliseconds = $wait }
    }
    catch {
        $stopwatch.Stop()
        if ($null -ne $mutex) { $mutex.Dispose() }
        return [pscustomobject]@{
            Acquired = $false
            Mutex = $null
            Status = 'error'
            WaitMilliseconds = [Math]::Min($script:AICarmineTaskStateMutexTimeoutMilliseconds, [Math]::Max(0, [int]$stopwatch.ElapsedMilliseconds))
        }
    }
}

function Exit-AICarmineTaskStateMutex {
    param($Mutex)

    if ($null -eq $Mutex) { return }
    $ownedMutex = $null
    $acquired = $false
    if ($null -ne $Mutex.PSObject.Properties['Acquired']) {
        $acquired = [bool]$Mutex.Acquired
        $ownedMutex = $Mutex.Mutex
    }
    else {
        $acquired = $true
        $ownedMutex = $Mutex
    }
    if ($null -ne $ownedMutex) {
        try {
            if ($acquired) { $ownedMutex.ReleaseMutex() }
        }
        catch {
        }
        finally {
            $ownedMutex.Dispose()
        }
    }
}

function Get-AICarmineObserverBoundedName {
    param($Value)

    if ($null -eq $Value) {
        return ''
    }
    $text = [string]$Value
    if ($text.Length -gt 120) {
        return $text.Substring(0, 120)
    }
    return $text
}

function Get-AICarmineObserverRoot {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $tempPrefix = $tempRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $ownerRoot = [IO.Path]::GetFullPath((Join-Path $tempRoot 'aicarmine-cline-hooks'))
    $observerRoot = [IO.Path]::GetFullPath((Join-Path $ownerRoot 'pretool-observer'))

    if (-not $observerRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }

    foreach ($path in @($ownerRoot, $observerRoot)) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                return $null
            }
        }
        else {
            [void][IO.Directory]::CreateDirectory($path)
            $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                return $null
            }
        }
    }
    return $observerRoot
}

function Get-AICarmineObserverChildDirectory {
    param([string]$Root, [string]$Name)

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $child = [IO.Path]::GetFullPath((Join-Path $Root $Name))
    if (-not $child.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    if (Test-Path -LiteralPath $child) {
        $item = Get-Item -LiteralPath $child -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            return $null
        }
    }
    else {
        [void][IO.Directory]::CreateDirectory($child)
        $item = Get-Item -LiteralPath $child -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            return $null
        }
    }
    return $child
}

function Write-AICarmineObserverJson {
    param([string]$Path, $Value)

    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'observer_file_is_reparse_point'
        }
    }
    $json = $Value | ConvertTo-Json -Compress -Depth 10
    [IO.File]::WriteAllText($Path, $json, (New-Object Text.UTF8Encoding($false)))
}

function Write-AICarmineObserverJsonAtomic {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    $tempPath = $null
    $backupPath = $null
    $stream = $null
    try {
        $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        $destination = [IO.Path]::GetFullPath($Path)
        $parent = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($destination))
        if (-not $destination.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
            -not (($parent.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar).StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase))) {
            throw 'atomic_state_path_outside_root'
        }
        foreach ($directoryPath in @($Root, $parent)) {
            $directoryItem = Get-Item -LiteralPath $directoryPath -Force -ErrorAction Stop
            if (-not $directoryItem.PSIsContainer -or ($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'atomic_state_directory_invalid'
            }
        }
        if (Test-Path -LiteralPath $destination) {
            $destinationItem = Get-Item -LiteralPath $destination -Force -ErrorAction Stop
            if ($destinationItem.PSIsContainer -or ($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'atomic_state_destination_invalid'
            }
        }

        $json = $Value | ConvertTo-Json -Compress -Depth 10
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($json)
        $tempPath = Join-Path $parent ('.aicarmine-state-{0}.tmp' -f [Guid]::NewGuid().ToString('N'))
        $stream = New-Object IO.FileStream($tempPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null
        if ($null -ne $script:AICarmineObserverBeforeAtomicCommitTestHook) {
            & $script:AICarmineObserverBeforeAtomicCommitTestHook
        }
        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            $backupPath = Join-Path $parent ('.aicarmine-state-backup-{0}.tmp' -f [Guid]::NewGuid().ToString('N'))
            [IO.File]::Replace($tempPath, $destination, $backupPath)
        }
        else {
            [IO.File]::Move($tempPath, $destination)
        }
        $tempPath = $null
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if (-not [string]::IsNullOrEmpty($tempPath) -and (Test-Path -LiteralPath $tempPath -PathType Leaf)) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
        if (-not [string]::IsNullOrEmpty($backupPath) -and (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
            Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-AICarmineTaskIdentity {
    param($Payload)

    $taskId = Get-AICarmineObserverProperty -Value $Payload -Names @('taskId', 'task_id', 'taskID')
    if ($null -eq $taskId -or $taskId -isnot [string] -or [string]::IsNullOrWhiteSpace($taskId)) {
        return $null
    }
    return [pscustomobject]@{
        TaskKeySha256 = Get-AICarmineObserverSha256 -Text $taskId
    }
}

function Get-AICarmineInvocationKeySha256 {
    param($Payload)

    $aliases = @('toolUseId', 'tool_use_id', 'toolCallId', 'tool_call_id', 'callId', 'call_id', 'requestId', 'request_id', 'invocationId', 'invocation_id')
    $containers = [Collections.Generic.List[object]]::new()
    [void]$containers.Add($Payload)
    foreach ($containerName in @(@('toolInput', 'tool_input', 'input'), @('toolResult', 'tool_result', 'result', 'output'))) {
        $container = Get-AICarmineObserverPropertyMatch -Value $Payload -Names $containerName
        if ($container.Found) { [void]$containers.Add($container.Value) }
    }
    foreach ($container in $containers) {
        $match = Get-AICarmineObserverPropertyMatch -Value $container -Names $aliases
        if ($match.Found -and $match.Value -is [string] -and -not [string]::IsNullOrWhiteSpace($match.Value)) {
            $bounded = [string]$match.Value
            if ($bounded.Length -gt 512) { $bounded = $bounded.Substring(0, 512) }
            return Get-AICarmineObserverSha256 -Text $bounded
        }
    }
    return ''
}

function Get-AICarmineObserverAgeSeconds {
    param($TimestampUtc)

    try {
        if ($TimestampUtc -is [DateTime]) {
            $timestamp = $TimestampUtc.ToUniversalTime()
        }
        else {
            $timestamp = [DateTime]::Parse(
                [string]$TimestampUtc,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind
            ).ToUniversalTime()
        }
        return [Math]::Max(0, [int]([DateTime]::UtcNow - $timestamp).TotalSeconds)
    }
    catch { return $null }
}

function Test-AICarmineObserverDigest {
    param($Value, [bool]$AllowEmpty)

    if ($Value -isnot [string]) { return $false }
    if ($AllowEmpty -and [string]::IsNullOrEmpty($Value)) { return $true }
    return $Value -match '^[0-9a-f]{64}$'
}

function Get-AICarmineBoundedRecentDigests {
    param($Records)

    return @($Records | Where-Object { Test-AICarmineObserverDigest -Value $_ -AllowEmpty $false } | Select-Object -Last 32)
}

function Get-AICarmineBoundedPendingCalls {
    param($Records)

    $valid = [Collections.Generic.List[object]]::new()
    foreach ($record in @($Records | Select-Object -Last 32)) {
        if ($null -eq $record -or $record -is [string]) { continue }
        $age = Get-AICarmineObserverAgeSeconds -TimestampUtc $record.timestamp_utc
        if ($null -eq $age -or $age -gt 600 -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.invocation_key_sha256) -AllowEmpty $true) -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.tool_call_sha256) -AllowEmpty $true) -or
            @('mcp', 'native', 'unknown') -notcontains [string]$record.selected_tool_kind) { continue }
        [void]$valid.Add([ordered]@{
            timestamp_utc = [string]$record.timestamp_utc
            invocation_key_sha256 = [string]$record.invocation_key_sha256
            tool_call_sha256 = [string]$record.tool_call_sha256
            selected_tool_kind = Get-AICarmineObserverBoundedName -Value $record.selected_tool_kind
            selected_wrapper_tool_name = Get-AICarmineObserverBoundedName -Value $record.selected_wrapper_tool_name
            selected_mcp_server_name = Get-AICarmineObserverBoundedName -Value $record.selected_mcp_server_name
            selected_mcp_tool_name = Get-AICarmineObserverBoundedName -Value $record.selected_mcp_tool_name
        })
    }
    return @($valid | Select-Object -Last 32)
}

function Get-AICarmineBoundedRecentOutcomes {
    param($Records)

    $valid = [Collections.Generic.List[object]]::new()
    foreach ($record in @($Records | Select-Object -Last 32)) {
        if ($null -eq $record -or $record -is [string]) { continue }
        $age = Get-AICarmineObserverAgeSeconds -TimestampUtc $record.timestamp_utc
        if ($null -eq $age -or $age -gt 86400 -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.invocation_key_sha256) -AllowEmpty $true) -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.tool_call_sha256) -AllowEmpty $true) -or
            @('mcp', 'native', 'unknown') -notcontains [string]$record.selected_tool_kind -or
            @('success', 'failure', 'unknown') -notcontains [string]$record.outcome -or
            @('is_error_true', 'success_false', 'error_field_present', 'status_failure', 'result_error_prefix', 'none') -notcontains [string]$record.failure_signal -or
            @('invocation_id', 'tool_call_sha256', 'unique_identity') -notcontains [string]$record.correlation_method -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.result_sha256) -AllowEmpty $true) -or
            -not (Test-AICarmineObserverDigest -Value ([string]$record.error_message_sha256) -AllowEmpty $true)) { continue }
        $errorType = [string]$record.error_type
        if (-not [string]::IsNullOrEmpty($errorType) -and $errorType -notmatch '^[A-Za-z0-9._:-]{1,120}$') { $errorType = '' }
        [void]$valid.Add([ordered]@{
            timestamp_utc = [string]$record.timestamp_utc
            invocation_key_sha256 = [string]$record.invocation_key_sha256
            tool_call_sha256 = [string]$record.tool_call_sha256
            selected_tool_kind = Get-AICarmineObserverBoundedName -Value $record.selected_tool_kind
            selected_wrapper_tool_name = Get-AICarmineObserverBoundedName -Value $record.selected_wrapper_tool_name
            selected_mcp_server_name = Get-AICarmineObserverBoundedName -Value $record.selected_mcp_server_name
            selected_mcp_tool_name = Get-AICarmineObserverBoundedName -Value $record.selected_mcp_tool_name
            outcome = [string]$record.outcome
            failure_signal = [string]$record.failure_signal
            correlation_method = [string]$record.correlation_method
            result_sha256 = [string]$record.result_sha256
            error_type = $errorType
            error_message_sha256 = [string]$record.error_message_sha256
        })
    }
    return @($valid | Select-Object -Last 32)
}

function Get-AICarmineRoutingConstraintOrder {
    return @('read_only')
}

function Get-AICarmineValidatedRoutingState {
    param([string]$Root, [string]$TaskKeySha256)

    $statePath = Join-Path $Root ('routing-{0}.json' -f $TaskKeySha256)
    $missing = [pscustomobject]@{ Found = $false; State = $null; Path = $statePath; AgeSeconds = $null }
    try {
        $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        $resolvedPath = [IO.Path]::GetFullPath($statePath)
        if (-not $resolvedPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) { return $missing }
        $item = Get-Item -LiteralPath $resolvedPath -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $missing }
        $state = [IO.File]::ReadAllText($resolvedPath, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop
        $age = Get-AICarmineObserverAgeSeconds -TimestampUtc $state.timestamp_utc
        $expectedEpoch = Get-AICarmineObserverSha256 -Text ($TaskKeySha256 + [string]$state.routing_hint_sha256)
        if ($state.schema -ne 'aicarmine.cline.task-routing-state.v1' -or -not [bool]$state.classified -or
            $state.task_key_sha256 -ne $TaskKeySha256 -or
            -not (Test-AICarmineObserverDigest -Value ([string]$state.routing_hint_sha256) -AllowEmpty $false) -or
            $state.routing_epoch_sha256 -ne $expectedEpoch -or $null -eq $age -or $age -gt 86400) { return $missing }
        foreach ($arrayName in @('recent_tool_call_sha256', 'pending_tool_calls', 'recent_tool_outcomes')) {
            $property = $state.PSObject.Properties[$arrayName]
            if ($null -eq $property -or @($property.Value).Count -gt 32) { return $missing }
        }

        $legacyConstraintNames = @(
            'read_only',
            'no_source_write',
            'no_memory_write',
            'no_service_mutation',
            'no_commit',
            'no_push',
            'existing_diff_only',
            'explicit_memory_write',
            'explicit_source_write'
        )
        $constraints = [Collections.Generic.List[string]]::new()
        $constraintProperty = $state.PSObject.Properties['constraints']
        if ($null -eq $constraintProperty) {
            Add-Member -InputObject $state -NotePropertyName constraints -NotePropertyValue @()
        }
        else {
            if ($constraintProperty.Value -isnot [Array]) { return $missing }
            $rawConstraints = @($constraintProperty.Value)
            if ($rawConstraints.Count -gt 9) { return $missing }
            $seen = @{}
            foreach ($constraint in $rawConstraints) {
                if ($constraint -isnot [string] -or $legacyConstraintNames -notcontains [string]$constraint -or
                    $seen.ContainsKey([string]$constraint)) { return $missing }
                $seen[[string]$constraint] = $true
            }
            if ($seen.ContainsKey('read_only')) { [void]$constraints.Add('read_only') }
            $state.constraints = @($constraints)
        }
        $state.read_only = $constraints.Contains('read_only')
        return [pscustomobject]@{ Found = $true; State = $state; Path = $resolvedPath; AgeSeconds = $age }
    }
    catch { return $missing }
}

function Get-AICarmineRoutingMetadata {
    param([AllowEmptyString()][string]$RoutingHint)

    $classes = [Collections.Generic.List[string]]::new()
    $tools = [Collections.Generic.List[string]]::new()
    $readOnly = $false
    $section = ''
    foreach ($line in @($RoutingHint -split '\r?\n')) {
        if ($line -eq 'Task classes:') {
            $section = 'classes'
            continue
        }
        if ($line -eq 'Preferred sequence:') {
            $section = 'tools'
            continue
        }
        if ($line -eq 'Constraints:') {
            $section = 'constraints'
            continue
        }
        if ($section -eq 'classes' -and $line -match '^- (.{1,120})$' -and $classes.Count -lt 8) {
            [void]$classes.Add([string]$Matches[1])
        }
        elseif ($section -eq 'tools' -and $line -match '^\d+\. (.{1,120})$' -and $tools.Count -lt 8) {
            [void]$tools.Add([string]$Matches[1])
        }
        elseif ($section -eq 'constraints' -and
            $line.StartsWith('- Read-only:', [StringComparison]::OrdinalIgnoreCase)) {
            $readOnly = $true
        }
    }
    $constraints = @()
    if ($readOnly) { $constraints = @('read_only') }
    return [pscustomobject]@{
        Classes = @($classes)
        PreferredTools = @($tools)
        Constraints = @($constraints)
        ReadOnly = $readOnly
        ConstraintsPresent = $RoutingHint -match '(?m)^Constraints:$'
        ExplicitExistingDiff = $RoutingHint -match '(?i)already-provided unified_diff'
    }
}

function Write-AICarmineClineTaskRoutingState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$RoutingHint
    )

    $lockResult = $null
    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        if ($null -eq $identity) { return }
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) { return }

        $metadata = Get-AICarmineRoutingMetadata -RoutingHint $RoutingHint
        $routingHintSha256 = Get-AICarmineObserverSha256 -Text $RoutingHint
        $routingEpochSha256 = Get-AICarmineObserverSha256 -Text ($identity.TaskKeySha256 + $routingHintSha256)
        $lockResult = Enter-AICarmineTaskStateMutex -TaskKeySha256 $identity.TaskKeySha256
        if ($null -eq $lockResult -or -not $lockResult.Acquired) { return }

        $previousResult = Get-AICarmineValidatedRoutingState -Root $root -TaskKeySha256 $identity.TaskKeySha256
        $recent = @()
        $pending = @()
        $outcomes = @()
        if ($previousResult.Found -and $previousResult.State.routing_hint_sha256 -eq $routingHintSha256 -and
            $previousResult.State.routing_epoch_sha256 -eq $routingEpochSha256) {
            $recent = @(Get-AICarmineBoundedRecentDigests -Records $previousResult.State.recent_tool_call_sha256)
            $pending = @(Get-AICarmineBoundedPendingCalls -Records $previousResult.State.pending_tool_calls)
            $outcomes = @(Get-AICarmineBoundedRecentOutcomes -Records $previousResult.State.recent_tool_outcomes)
        }

        $state = [ordered]@{
            schema = 'aicarmine.cline.task-routing-state.v1'
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            task_key_sha256 = $identity.TaskKeySha256
            routing_hint_sha256 = $routingHintSha256
            routing_epoch_sha256 = $routingEpochSha256
            classified = $metadata.Classes.Count -gt 0
            read_only = [bool]$metadata.ReadOnly
            classes = @($metadata.Classes)
            preferred_tools = @($metadata.PreferredTools)
            constraints = @($metadata.Constraints)
            constraints_present = [bool]$metadata.ConstraintsPresent
            explicit_existing_diff = [bool]$metadata.ExplicitExistingDiff
            recent_tool_call_sha256 = @($recent)
            pending_tool_calls = @($pending)
            recent_tool_outcomes = @($outcomes)
        }
        Write-AICarmineObserverJsonAtomic -Root $root -Path (Join-Path $root ('routing-{0}.json' -f $identity.TaskKeySha256)) -Value $state
    }
    catch { return }
    finally { Exit-AICarmineTaskStateMutex -Mutex $lockResult }
}

function ConvertTo-AICarmineCanonicalValue {
    param($Value, [int]$Depth)

    if ($null -eq $Value) {
        return [ordered]@{ type = 'null' }
    }
    if ($Value -is [string]) {
        $utf8Bytes = (New-Object Text.UTF8Encoding($false)).GetByteCount($Value)
        return [ordered]@{
            type = 'string'
            utf8_bytes = $utf8Bytes
            sha256 = Get-AICarmineObserverSha256 -Text $Value
        }
    }
    if ($Value -is [bool]) {
        return [ordered]@{ type = 'boolean'; value = [bool]$Value }
    }
    if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64]) {
        return [ordered]@{ type = 'integer'; value = $Value }
    }
    if ($Value -is [decimal] -or $Value -is [double] -or $Value -is [single]) {
        return [ordered]@{ type = 'number'; value = $Value }
    }
    if ($Depth -ge 3) {
        return [ordered]@{ type = 'bounded'; depth = $Depth }
    }
    if ($Value -is [Array]) {
        $items = [Collections.Generic.List[object]]::new()
        $limit = [Math]::Min($Value.Count, 32)
        for ($index = 0; $index -lt $limit; $index++) {
            [void]$items.Add((ConvertTo-AICarmineCanonicalValue -Value $Value[$index] -Depth ($Depth + 1)))
        }
        return [ordered]@{ type = 'array'; items = @($items) }
    }

    $properties = @($Value.PSObject.Properties | Sort-Object Name)
    $bounded = [ordered]@{}
    $limit = [Math]::Min($properties.Count, 32)
    for ($index = 0; $index -lt $limit; $index++) {
        $name = Get-AICarmineObserverBoundedName -Value $properties[$index].Name
        $bounded[$name] = ConvertTo-AICarmineCanonicalValue -Value $properties[$index].Value -Depth ($Depth + 1)
    }
    return [ordered]@{ type = 'object'; properties = $bounded }
}

function Get-AICarmineToolInputKeyNames {
    param($ToolInput)

    if ($null -eq $ToolInput -or $ToolInput -is [string]) {
        return @()
    }
    $sensitive = @('authorization', 'token', 'secret', 'password', 'api-key', 'api_key', 'credential', 'cookie')
    $names = [Collections.Generic.List[string]]::new()
    $properties = @($ToolInput.PSObject.Properties)
    $limit = [Math]::Min($properties.Count, 32)
    for ($index = 0; $index -lt $limit; $index++) {
        $name = Get-AICarmineObserverBoundedName -Value $properties[$index].Name
        if ($sensitive -contains $name.ToLowerInvariant()) {
            $name = '[redacted]'
        }
        if (-not $names.Contains($name)) {
            [void]$names.Add($name)
        }
    }
    return @($names | Sort-Object)
}

function Get-AICarmineToolCallMetadata {
    param($Payload)

    $wrapperTool = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $Payload -Names @('toolName', 'tool_name', 'tool'))
    $toolInputMatch = Get-AICarmineObserverPropertyMatch -Value $Payload -Names @('toolInput', 'tool_input', 'input')
    $toolInput = $toolInputMatch.Value
    $serverName = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $toolInput -Names @('server_name', 'serverName', 'server'))
    $nestedToolName = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $toolInput -Names @('tool_name', 'toolName', 'name'))
    $mcpToolName = ''
    $selectedKind = 'unknown'
    if ([string]::Equals($wrapperTool, 'use_mcp_tool', [StringComparison]::OrdinalIgnoreCase) -and -not [string]::IsNullOrEmpty($nestedToolName)) {
        $selectedKind = 'mcp'; $mcpToolName = $nestedToolName
    }
    elseif ($wrapperTool.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase)) {
        $selectedKind = 'mcp'; $mcpToolName = $wrapperTool
    }
    elseif ($serverName.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase) -and -not [string]::IsNullOrEmpty($nestedToolName)) {
        $selectedKind = 'mcp'; $mcpToolName = $nestedToolName
    }
    elseif (-not [string]::IsNullOrEmpty($wrapperTool)) { $selectedKind = 'native' }

    $toolCallSha256 = ''
    if ($toolInputMatch.Found) {
        $canonicalInput = ConvertTo-AICarmineCanonicalValue -Value $toolInput -Depth 0
        $callIdentity = [ordered]@{
            selected_tool_kind = $selectedKind
            selected_wrapper_tool_name = $wrapperTool
            selected_mcp_server_name = $serverName
            selected_mcp_tool_name = $mcpToolName
            tool_input = $canonicalInput
        } | ConvertTo-Json -Compress -Depth 8
        $toolCallSha256 = Get-AICarmineObserverSha256 -Text $callIdentity
    }
    return [pscustomobject]@{
        SelectedToolKind = $selectedKind
        SelectedWrapperToolName = $wrapperTool
        SelectedMcpServerName = $serverName
        SelectedMcpToolName = $mcpToolName
        ToolCallSha256 = $toolCallSha256
        InvocationKeySha256 = Get-AICarmineInvocationKeySha256 -Payload $Payload
        ToolInputPresent = [bool]$toolInputMatch.Found
        ToolInputKeyNames = @(Get-AICarmineToolInputKeyNames -ToolInput $toolInput)
    }
}

function Test-AICarminePlausibleRepositoryMcp {
    param([string]$ToolName)

    return $ToolName -match '^aicarmine_(repo_|git_readonly_|project_memory_|job_|sqlite_readonly_|codex_ops_|mcp_|service_state_|rag_)'
}

function Write-AICarmineObservationLog {
    param([string]$Root, $Observation)

    $directory = Get-AICarmineObserverChildDirectory -Root $Root -Name 'observations'
    if ([string]::IsNullOrEmpty($directory)) {
        throw 'observation_directory_unavailable'
    }
    $name = 'observation-{0}-{1}.json' -f [DateTime]::UtcNow.Ticks, [Guid]::NewGuid().ToString('N')
    Write-AICarmineObserverJson -Path (Join-Path $directory $name) -Value $Observation

    $files = @(Get-ChildItem -LiteralPath $directory -Filter 'observation-*.json' -File -Force |
        Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
        Sort-Object LastWriteTimeUtc -Descending)
    if ($files.Count -gt 128) {
        foreach ($file in @($files | Select-Object -Skip 128)) {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
        }
    }
}

function Get-AICarmineClinePreToolObservation {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput)

    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) { throw 'observer_root_unavailable' }
        $toolMetadata = Get-AICarmineToolCallMetadata -Payload $payload
        $taskKey = ''
        if ($null -ne $identity) { $taskKey = $identity.TaskKeySha256 }

        $stateFound = $false
        $stateAge = $null
        $preferredMatch = $false
        $codes = [Collections.Generic.List[string]]::new()
        $messages = [Collections.Generic.List[string]]::new()
        $repeated = $false
        $identicalFailure = $false
        $nativeAfterMcpFailure = $false
        $unrelatedMcp = $false
        $lockStatus = 'not_required'
        $lockWait = 0
        $lockResult = $null

        if ([string]::IsNullOrEmpty($taskKey)) {
            [void]$codes.Add('routing_state_missing')
        }
        else {
            try {
                $lockResult = Enter-AICarmineTaskStateMutex -TaskKeySha256 $taskKey
                $lockStatus = [string]$lockResult.Status
                $lockWait = [int]$lockResult.WaitMilliseconds
                if (-not $lockResult.Acquired) {
                    if ($lockStatus -eq 'timeout') { [void]$codes.Add('state_lock_timeout') }
                    else { [void]$codes.Add('state_lock_error') }
                }
                else {
                    $stateResult = Get-AICarmineValidatedRoutingState -Root $root -TaskKeySha256 $taskKey
                    $stateFound = [bool]$stateResult.Found
                    $stateAge = $stateResult.AgeSeconds
                    if (-not $stateFound) {
                        [void]$codes.Add('routing_state_missing')
                    }
                    else {
                        $state = $stateResult.State
                        $preferredTools = @($state.preferred_tools | Select-Object -First 8)
                        $preferredMatch = $toolMetadata.SelectedMcpToolName -ne '' -and ($preferredTools -contains $toolMetadata.SelectedMcpToolName)
                        if ($preferredMatch) { [void]$codes.Add('recommended_mcp_selected') }
                        elseif ($toolMetadata.SelectedToolKind -eq 'native' -and $preferredTools.Count -gt 0) { [void]$codes.Add('native_used_while_mcp_recommended') }
                        elseif ($toolMetadata.SelectedToolKind -eq 'mcp') { [void]$codes.Add('nonpreferred_mcp_selected') }

                        $mcpWriteTools = @('aicarmine_repo_code_apply_patch', 'aicarmine_project_memory_upsert_verified', 'aicarmine_project_memory_supersede', 'aicarmine_project_memory_mark_stale')
                        $nativeWriteTools = @('write_to_file', 'replace_in_file', 'apply_patch')
                        $writeCandidate = ($toolMetadata.SelectedToolKind -eq 'mcp' -and $mcpWriteTools -contains $toolMetadata.SelectedMcpToolName) -or
                            ($toolMetadata.SelectedToolKind -eq 'native' -and $nativeWriteTools -contains $toolMetadata.SelectedWrapperToolName)
                        if ([bool]$state.read_only -and $writeCandidate) { [void]$codes.Add('read_only_write_tool_candidate') }

                        $recent = @(Get-AICarmineBoundedRecentDigests -Records $state.recent_tool_call_sha256)
                        if (-not [string]::IsNullOrEmpty($toolMetadata.ToolCallSha256)) {
                            $repeated = $recent -contains $toolMetadata.ToolCallSha256
                            if ($repeated) { [void]$codes.Add('identical_tool_call_repeated') }
                        }
                        $outcomes = @(Get-AICarmineBoundedRecentOutcomes -Records $state.recent_tool_outcomes)
                        $recentFailures = @($outcomes | Where-Object {
                            $_.outcome -eq 'failure' -and (Get-AICarmineObserverAgeSeconds -TimestampUtc $_.timestamp_utc) -le 600
                        })
                        if (-not [string]::IsNullOrEmpty($toolMetadata.ToolCallSha256) -and
                            @($recentFailures | Where-Object { $_.tool_call_sha256 -eq $toolMetadata.ToolCallSha256 }).Count -gt 0) {
                            $identicalFailure = $true
                            [void]$codes.Add('identical_tool_call_after_observed_failure')
                        }
                        if ($toolMetadata.SelectedToolKind -eq 'native' -and
                            @($recentFailures | Where-Object { $_.selected_tool_kind -eq 'mcp' }).Count -gt 0) {
                            $nativeAfterMcpFailure = $true
                            [void]$codes.Add('native_after_observed_mcp_failure')
                        }
                        if ($toolMetadata.SelectedToolKind -eq 'mcp' -and -not $preferredMatch -and
                            -not (Test-AICarminePlausibleRepositoryMcp -ToolName $toolMetadata.SelectedMcpToolName)) { $unrelatedMcp = $true }

                        if (-not [string]::IsNullOrEmpty($toolMetadata.ToolCallSha256)) {
                            $recent = @($recent | Where-Object { $_ -ne $toolMetadata.ToolCallSha256 })
                            $recent += $toolMetadata.ToolCallSha256
                        }
                        $state.recent_tool_call_sha256 = @($recent | Select-Object -Last 32)
                        $state.recent_tool_outcomes = @($outcomes)
                        $pending = @(Get-AICarmineBoundedPendingCalls -Records $state.pending_tool_calls)
                        if (-not [string]::IsNullOrEmpty($toolMetadata.InvocationKeySha256)) {
                            $pending = @($pending | Where-Object { $_.invocation_key_sha256 -ne $toolMetadata.InvocationKeySha256 })
                        }
                        $pending += [ordered]@{
                            timestamp_utc = [DateTime]::UtcNow.ToString('o')
                            invocation_key_sha256 = $toolMetadata.InvocationKeySha256
                            tool_call_sha256 = $toolMetadata.ToolCallSha256
                            selected_tool_kind = $toolMetadata.SelectedToolKind
                            selected_wrapper_tool_name = $toolMetadata.SelectedWrapperToolName
                            selected_mcp_server_name = $toolMetadata.SelectedMcpServerName
                            selected_mcp_tool_name = $toolMetadata.SelectedMcpToolName
                        }
                        $state.pending_tool_calls = @($pending | Select-Object -Last 32)
                        Write-AICarmineObserverJsonAtomic -Root $root -Path $stateResult.Path -Value $state
                    }
                }
            }
            finally { Exit-AICarmineTaskStateMutex -Mutex $lockResult }
        }

<<<<<<< HEAD
        # Quantum/pre-quantum engineering awareness layer
        $taskText = ''
        $msgProp = $payload.PSObject.Properties['message']
        if ($null -ne $msgProp) { $taskText = [string]$msgProp.Value }
        if ($null -ne $payload.messages) { $taskText = ($payload.messages | Select-Object -First 1 | ConvertTo-Json).ToString() }
        $taskLower = $taskText.ToLower()
        
        # Detect quantum engineering task context
        $isQuantumTask = $taskLower -match '(?i)(quantum|qubit|circuit|gate|statevector|bloch|nisq|vqe|qaoa|qnn|quantum.?computing|pre.?quantum|hybrid.?quantum)'
        
=======
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
        if ($lockStatus -notin @('timeout', 'error')) {
            if ($codes.Contains('read_only_write_tool_candidate')) {
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: a write-capable tool was selected for a read-only task. The call is not blocked by this observe-only hook. Recheck the task boundary before proceeding.')
            }
            if ($identicalFailure) {
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: this identical tool call previously produced an observed failure. The call is not blocked. Do not retry it unchanged; change a discriminating argument or diagnose the failing stage.')
            }
            elseif ($nativeAfterMcpFailure) {
<<<<<<< HEAD
                $mcpToolsList = 'aicarmine_repo_read, aicarmine_repo_search, aicarmine_git_readonly_*, aicarmine_rag_context'
                if ($isQuantumTask) {
                    $mcpToolsList += ', aicarmine_project_memory_search (for quantum experiment metadata)'
                }
                [void]$messages.Add("AICARMINE PRE-TOOL OBSERVATION: a prior MCP failure was observed in this routing epoch before this native tool selection. The call is not blocked. Report the failed MCP call and ensure the fallback addresses that concrete failure. MCP tools ($mcpToolsList) are preferred over native Cline tools (read_file, search_files, execute_command git).")
=======
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: a prior MCP failure was observed in this routing epoch before this native tool selection. The call is not blocked. Report the failed MCP call and ensure the fallback addresses that concrete failure.')
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
            }
            elseif ($repeated) {
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: an identical tool call was already observed for this task. The call is not blocked. Do not repeat it unchanged unless new evidence justifies the retry.')
            }
            elseif ($codes.Contains('native_used_while_mcp_recommended')) {
<<<<<<< HEAD
                $mcpAdvise = 'MCP tools provide truncation control, structured output, Git/SQLite/RAG integration. Native tools are too generic.'
                if ($isQuantumTask) {
                    $mcpAdvise += ' Quantum/pre-quantum engineering tasks require MCP tools for bounded statevector visualization, circuit JSON export, and experiment metadata tracking.'
                }
                [void]$messages.Add("AICARMINE PRE-TOOL OBSERVATION: this task has repository MCP recommendations, but a native tool was selected. The call is not blocked. Use native fallback only after a concrete MCP failure and report that failure. $mcpAdvise")
=======
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: this task has repository MCP recommendations, but a native tool was selected. The call is not blocked. Use native fallback only after a concrete MCP failure and report that failure.')
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
            }
            if ($unrelatedMcp) {
                [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: the selected MCP tool belongs to a family unrelated to the repository routing state. The call is not blocked. Recheck tool relevance before proceeding.')
            }
        }
        $contextModification = [string]::Join([Environment]::NewLine, @($messages | Select-Object -Unique | Select-Object -First 2))
        if ($contextModification.Length -gt 900) { $contextModification = $contextModification.Substring(0, 900) }
        $observation = [ordered]@{
            schema = 'aicarmine.cline.pretool-observation.v1'
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            task_key_sha256 = $taskKey
            routing_state_found = $stateFound
            routing_state_age_seconds = $stateAge
            selected_tool_kind = $toolMetadata.SelectedToolKind
            selected_wrapper_tool_name = $toolMetadata.SelectedWrapperToolName
            selected_mcp_server_name = $toolMetadata.SelectedMcpServerName
            selected_mcp_tool_name = $toolMetadata.SelectedMcpToolName
            tool_call_sha256 = $toolMetadata.ToolCallSha256
            tool_input_key_names = @($toolMetadata.ToolInputKeyNames)
            preferred_tool_match = $preferredMatch
            advisory_codes = @($codes)
            context_modification_emitted = -not [string]::IsNullOrEmpty($contextModification)
            state_lock_status = $lockStatus
            state_lock_wait_ms = $lockWait
        }
        Write-AICarmineObservationLog -Root $root -Observation $observation
        return [pscustomobject]@{ contextModification = $contextModification; observation = [pscustomobject]$observation }
    }
    catch { return [pscustomobject]@{ contextModification = ''; observation = $null } }
}
