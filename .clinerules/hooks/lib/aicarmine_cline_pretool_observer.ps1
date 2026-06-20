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
    try {
        $mutex = New-Object Threading.Mutex($false, ('Local\AICarmineClinePreTool-{0}' -f $TaskKeySha256))
        $acquired = $false
        try {
            $acquired = $mutex.WaitOne(750)
        }
        catch [Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            $mutex.Dispose()
            return $null
        }
        return $mutex
    }
    catch {
        if ($null -ne $mutex) {
            $mutex.Dispose()
        }
        return $null
    }
}

function Exit-AICarmineTaskStateMutex {
    param($Mutex)

    if ($null -ne $Mutex) {
        try {
            $Mutex.ReleaseMutex()
        }
        finally {
            $Mutex.Dispose()
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

function Get-AICarmineRoutingMetadata {
    param([AllowEmptyString()][string]$RoutingHint)

    $classes = [Collections.Generic.List[string]]::new()
    $tools = [Collections.Generic.List[string]]::new()
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
    }
    return [pscustomobject]@{
        Classes = @($classes)
        PreferredTools = @($tools)
        ReadOnly = $RoutingHint -match '(?m)^- Read-only:'
        ConstraintsPresent = $RoutingHint -match '(?m)^Constraints:$'
        ExplicitExistingDiff = $RoutingHint -match '(?i)already-provided unified_diff'
    }
}

function Write-AICarmineClineTaskRoutingState {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RoutingHint
    )

    $stateMutex = $null
    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        if ($null -eq $identity) {
            return
        }
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) {
            return
        }

        $stateMutex = Enter-AICarmineTaskStateMutex -TaskKeySha256 $identity.TaskKeySha256
        if ($null -eq $stateMutex) {
            return
        }

        $metadata = Get-AICarmineRoutingMetadata -RoutingHint $RoutingHint
        $routingHintSha256 = Get-AICarmineObserverSha256 -Text $RoutingHint
        $routingEpochSha256 = Get-AICarmineObserverSha256 -Text ($identity.TaskKeySha256 + $routingHintSha256)
        $statePath = Join-Path $root ('routing-{0}.json' -f $identity.TaskKeySha256)
        $recent = @()

        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            try {
                $item = Get-Item -LiteralPath $statePath -Force -ErrorAction Stop
                if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    $previous = Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json -ErrorAction Stop
                    $timestamp = [DateTime]::Parse([string]$previous.timestamp_utc).ToUniversalTime()
                    $age = [Math]::Max(0, [int]([DateTime]::UtcNow - $timestamp).TotalSeconds)
                    if ($previous.schema -eq 'aicarmine.cline.task-routing-state.v1' -and
                        $previous.task_key_sha256 -eq $identity.TaskKeySha256 -and
                        $previous.routing_hint_sha256 -eq $routingHintSha256 -and
                        $previous.routing_epoch_sha256 -eq $routingEpochSha256 -and $age -le 86400) {
                        $recent = @($previous.recent_tool_call_sha256 |
                            Where-Object { $_ -is [string] -and $_ -match '^[0-9a-f]{64}$' } |
                            Select-Object -Last 32)
                    }
                }
            }
            catch {
                $recent = @()
            }
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
            constraints_present = [bool]$metadata.ConstraintsPresent
            explicit_existing_diff = [bool]$metadata.ExplicitExistingDiff
            recent_tool_call_sha256 = @($recent)
        }
        Write-AICarmineObserverJson -Path $statePath -Value $state
    }
    catch {
        return
    }
    finally {
        Exit-AICarmineTaskStateMutex -Mutex $stateMutex
    }
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
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) {
            throw 'observer_root_unavailable'
        }

        $wrapperTool = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $payload -Names @('toolName', 'tool_name', 'tool'))
        $toolInput = Get-AICarmineObserverProperty -Value $payload -Names @('toolInput', 'tool_input', 'input')
        $serverName = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $toolInput -Names @('server_name', 'serverName', 'server'))
        $nestedToolName = Get-AICarmineObserverBoundedName -Value (Get-AICarmineObserverProperty -Value $toolInput -Names @('tool_name', 'toolName', 'name'))
        $mcpToolName = ''
        $selectedKind = 'unknown'
        if ([string]::Equals($wrapperTool, 'use_mcp_tool', [StringComparison]::OrdinalIgnoreCase) -and
            -not [string]::IsNullOrEmpty($nestedToolName)) {
            $selectedKind = 'mcp'
            $mcpToolName = $nestedToolName
        }
        elseif ($wrapperTool.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase)) {
            $selectedKind = 'mcp'
            $mcpToolName = $wrapperTool
        }
        elseif ($serverName.StartsWith('aicarmine_', [StringComparison]::OrdinalIgnoreCase) -and
            -not [string]::IsNullOrEmpty($nestedToolName)) {
            $selectedKind = 'mcp'
            $mcpToolName = $nestedToolName
        }
        elseif (-not [string]::IsNullOrEmpty($wrapperTool)) {
            $selectedKind = 'native'
        }

        $taskKey = ''
        if ($null -ne $identity) {
            $taskKey = $identity.TaskKeySha256
        }
        $canonicalInput = ConvertTo-AICarmineCanonicalValue -Value $toolInput -Depth 0
        $callIdentity = [ordered]@{
            selected_tool_kind = $selectedKind
            selected_wrapper_tool_name = $wrapperTool
            selected_mcp_server_name = $serverName
            selected_mcp_tool_name = $mcpToolName
            tool_input = $canonicalInput
        } | ConvertTo-Json -Compress -Depth 8
        $toolCallSha256 = Get-AICarmineObserverSha256 -Text $callIdentity

        $state = $null
        $stateFound = $false
        $stateAge = $null
        $preferredMatch = $false
        $statePath = $null
        $stateMutex = $null
        $codes = [Collections.Generic.List[string]]::new()
        $messages = [Collections.Generic.List[string]]::new()
        $repeated = $false
        try {
            if (-not [string]::IsNullOrEmpty($taskKey)) {
                $stateMutex = Enter-AICarmineTaskStateMutex -TaskKeySha256 $taskKey
                if ($null -eq $stateMutex) {
                    throw 'task_state_lock_timeout'
                }
                $statePath = Join-Path $root ('routing-{0}.json' -f $taskKey)
                if (Test-Path -LiteralPath $statePath -PathType Leaf) {
                    $stateItem = Get-Item -LiteralPath $statePath -Force -ErrorAction Stop
                    if (-not ($stateItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                        $state = Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json -ErrorAction Stop
                        $timestamp = [DateTime]::Parse([string]$state.timestamp_utc).ToUniversalTime()
                        $stateAge = [Math]::Max(0, [int]([DateTime]::UtcNow - $timestamp).TotalSeconds)
                        $expectedEpoch = Get-AICarmineObserverSha256 -Text ($taskKey + [string]$state.routing_hint_sha256)
                        if ($state.schema -eq 'aicarmine.cline.task-routing-state.v1' -and
                            [bool]$state.classified -and
                            $state.task_key_sha256 -eq $taskKey -and
                            $state.routing_epoch_sha256 -eq $expectedEpoch -and $stateAge -le 86400) {
                            $stateFound = $true
                        }
                    }
                }
            }

            if (-not $stateFound) {
                [void]$codes.Add('routing_state_missing')
            }
            else {
                $preferredTools = @($state.preferred_tools | Select-Object -First 8)
                $preferredMatch = $mcpToolName -ne '' -and ($preferredTools -contains $mcpToolName)
                if ($preferredMatch) {
                    [void]$codes.Add('recommended_mcp_selected')
                }
                elseif ($selectedKind -eq 'native' -and $preferredTools.Count -gt 0) {
                    [void]$codes.Add('native_used_while_mcp_recommended')
                }
                elseif ($selectedKind -eq 'mcp') {
                    [void]$codes.Add('nonpreferred_mcp_selected')
                }

                $mcpWriteTools = @(
                    'aicarmine_repo_code_apply_patch',
                    'aicarmine_project_memory_upsert_verified',
                    'aicarmine_project_memory_supersede',
                    'aicarmine_project_memory_mark_stale'
                )
                $nativeWriteTools = @('write_to_file', 'replace_in_file', 'apply_patch')
                $writeCandidate = ($selectedKind -eq 'mcp' -and $mcpWriteTools -contains $mcpToolName) -or
                    ($selectedKind -eq 'native' -and $nativeWriteTools -contains $wrapperTool)
                if ([bool]$state.read_only -and $writeCandidate) {
                    [void]$codes.Add('read_only_write_tool_candidate')
                }

                $recent = @($state.recent_tool_call_sha256 | Select-Object -Last 32)
                $repeated = $recent -contains $toolCallSha256
                if ($repeated) {
                    [void]$codes.Add('identical_tool_call_repeated')
                }
                $recent = @($recent | Where-Object { $_ -ne $toolCallSha256 })
                $recent += $toolCallSha256
                $state.recent_tool_call_sha256 = @($recent | Select-Object -Last 32)
                Write-AICarmineObserverJson -Path $statePath -Value $state

                if ($codes.Contains('read_only_write_tool_candidate')) {
                    [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: a write-capable tool was selected for a read-only task. The call is not blocked by this observe-only hook. Recheck the task boundary before proceeding.')
                }
                if ($repeated) {
                    [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: an identical tool call was already observed for this task. The call is not blocked. Do not repeat it unchanged unless new evidence justifies the retry.')
                }
                if ($codes.Contains('native_used_while_mcp_recommended')) {
                    [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: this task has repository MCP recommendations, but a native tool was selected. The call is not blocked. Use native fallback only after a concrete MCP failure and report that failure.')
                }
                if ($selectedKind -eq 'mcp' -and -not $preferredMatch -and
                    -not (Test-AICarminePlausibleRepositoryMcp -ToolName $mcpToolName)) {
                    [void]$messages.Add('AICARMINE PRE-TOOL OBSERVATION: the selected MCP tool belongs to a family unrelated to the repository routing state. The call is not blocked. Recheck tool relevance before proceeding.')
                }
            }
        }
        finally {
            Exit-AICarmineTaskStateMutex -Mutex $stateMutex
        }

        $contextModification = [string]::Join([Environment]::NewLine, @($messages | Select-Object -First 2))
        if ($contextModification.Length -gt 900) {
            $contextModification = $contextModification.Substring(0, 900)
        }
        $observation = [ordered]@{
            schema = 'aicarmine.cline.pretool-observation.v1'
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            task_key_sha256 = $taskKey
            routing_state_found = $stateFound
            routing_state_age_seconds = $stateAge
            selected_tool_kind = $selectedKind
            selected_wrapper_tool_name = $wrapperTool
            selected_mcp_server_name = $serverName
            selected_mcp_tool_name = $mcpToolName
            tool_call_sha256 = $toolCallSha256
            tool_input_key_names = @(Get-AICarmineToolInputKeyNames -ToolInput $toolInput)
            preferred_tool_match = $preferredMatch
            advisory_codes = @($codes)
            context_modification_emitted = -not [string]::IsNullOrEmpty($contextModification)
        }
        Write-AICarmineObservationLog -Root $root -Observation $observation
        return [pscustomobject]@{
            contextModification = $contextModification
            observation = [pscustomobject]$observation
        }
    }
    catch {
        return [pscustomobject]@{
            contextModification = ''
            observation = $null
        }
    }
}
