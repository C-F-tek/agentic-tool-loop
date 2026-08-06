# AICarmine Cline PostToolUse correlation-only helper

function Get-AICarminePostOutcomeField {
    param($Payload, $ResultValue, [string[]]$Names)

    $top = Get-AICarmineObserverPropertyMatch -Value $Payload -Names $Names
    if ($top.Found) { return $top }
    return Get-AICarmineObserverPropertyMatch -Value $ResultValue -Names $Names
}

function Test-AICarminePostErrorPresent {
    param($Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) { return -not [string]::IsNullOrWhiteSpace($Value) }
    if ($Value -is [Array]) { return $Value.Count -gt 0 }
    return @($Value.PSObject.Properties).Count -gt 0
}

function Get-AICarminePostResultType {
    param([bool]$Present, $Value)

    if (-not $Present) { return 'missing' }
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [string]) { return 'string' }
    if ($Value -is [bool]) { return 'boolean' }
    if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64]) { return 'integer' }
    if ($Value -is [decimal] -or $Value -is [double] -or $Value -is [single]) { return 'number' }
    if ($Value -is [Array]) { return 'array' }
    if ($null -ne $Value.PSObject) { return 'object' }
    return 'other'
}

function Get-AICarminePostOutcomeMetadata {
    param($Payload)

    $resultMatch = Get-AICarmineObserverPropertyMatch -Value $Payload -Names @('toolResult', 'tool_result', 'result', 'output')
    $resultValue = $resultMatch.Value
    $isError = Get-AICarminePostOutcomeField -Payload $Payload -ResultValue $resultValue -Names @('isError', 'is_error')
    $success = Get-AICarminePostOutcomeField -Payload $Payload -ResultValue $resultValue -Names @('success', 'ok')
    $error = Get-AICarminePostOutcomeField -Payload $Payload -ResultValue $resultValue -Names @('error', 'errorMessage', 'error_message')
    $status = Get-AICarminePostOutcomeField -Payload $Payload -ResultValue $resultValue -Names @('status', 'state')

    $outcome = 'unknown'
    $failureSignal = 'none'
    if ($isError.Found -and $isError.Value -is [bool] -and [bool]$isError.Value) {
        $outcome = 'failure'; $failureSignal = 'is_error_true'
    }
    elseif ($success.Found -and $success.Value -is [bool] -and -not [bool]$success.Value) {
        $outcome = 'failure'; $failureSignal = 'success_false'
    }
    elseif ($error.Found -and (Test-AICarminePostErrorPresent -Value $error.Value)) {
        $outcome = 'failure'; $failureSignal = 'error_field_present'
    }
    elseif ($status.Found -and $status.Value -is [string] -and
        @('failed', 'failure', 'error', 'errored', 'cancelled', 'canceled', 'timeout', 'timed_out') -contains $status.Value.ToLowerInvariant()) {
        $outcome = 'failure'; $failureSignal = 'status_failure'
    }
    elseif ($resultMatch.Found -and $resultValue -is [string] -and $resultValue.TrimStart() -match '^(Error:|MCP error:|Tool error:)') {
        $outcome = 'failure'; $failureSignal = 'result_error_prefix'
    }
    elseif (($success.Found -and $success.Value -is [bool] -and [bool]$success.Value) -or
        ($isError.Found -and $isError.Value -is [bool] -and -not [bool]$isError.Value -and $resultMatch.Found) -or
        ($status.Found -and $status.Value -is [string] -and @('success', 'succeeded', 'completed', 'complete', 'ok') -contains $status.Value.ToLowerInvariant())) {
        $outcome = 'success'
    }

    $resultType = Get-AICarminePostResultType -Present $resultMatch.Found -Value $resultValue
    $resultSha = ''
    $resultBytes = 0
    if ($resultMatch.Found) {
        $canonical = ConvertTo-AICarmineCanonicalValue -Value $resultValue -Depth 0
        $resultSha = Get-AICarmineObserverSha256 -Text ($canonical | ConvertTo-Json -Compress -Depth 8)
        if ($resultValue -is [string]) { $resultBytes = (New-Object Text.UTF8Encoding($false)).GetByteCount($resultValue) }
    }

    $errorMessage = ''
    $errorObject = $null
    if ($error.Found) {
        if ($error.Value -is [string]) { $errorMessage = [string]$error.Value }
        elseif ($null -ne $error.Value) {
            $errorObject = $error.Value
            $message = Get-AICarmineObserverPropertyMatch -Value $errorObject -Names @('message', 'errorMessage', 'error_message')
            if ($message.Found -and $message.Value -is [string]) { $errorMessage = [string]$message.Value }
        }
    }
    $errorType = ''
    foreach ($source in @($errorObject, $resultValue, $Payload)) {
        $typeMatch = Get-AICarmineObserverPropertyMatch -Value $source -Names @('type', 'error_type', 'errorType', 'name', 'code')
        if ($typeMatch.Found -and $typeMatch.Value -is [string] -and $typeMatch.Value -match '^[A-Za-z0-9._:-]{1,120}$') {
            $errorType = [string]$typeMatch.Value
            break
        }
    }
    $errorMessageSha = ''
    $errorMessageBytes = 0
    if (-not [string]::IsNullOrEmpty($errorMessage)) {
        $errorMessageSha = Get-AICarmineObserverSha256 -Text $errorMessage
        $errorMessageBytes = (New-Object Text.UTF8Encoding($false)).GetByteCount($errorMessage)
    }
    return [pscustomobject]@{
        Outcome = $outcome
        FailureSignal = $failureSignal
        ResultType = $resultType
        ResultSha256 = $resultSha
        ResultUtf8Bytes = $resultBytes
        ErrorType = $errorType
        ErrorMessageSha256 = $errorMessageSha
        ErrorMessageUtf8Bytes = $errorMessageBytes
    }
}

function Test-AICarminePostIdentityMatch {
    param($Pending, $Metadata)

    return [string]::Equals([string]$Pending.selected_tool_kind, [string]$Metadata.SelectedToolKind, [StringComparison]::Ordinal) -and
        [string]::Equals([string]$Pending.selected_wrapper_tool_name, [string]$Metadata.SelectedWrapperToolName, [StringComparison]::Ordinal) -and
        [string]::Equals([string]$Pending.selected_mcp_server_name, [string]$Metadata.SelectedMcpServerName, [StringComparison]::Ordinal) -and
        [string]::Equals([string]$Pending.selected_mcp_tool_name, [string]$Metadata.SelectedMcpToolName, [StringComparison]::Ordinal)
}

function Write-AICarminePostObservationLog {
    param([string]$Root, $Observation)

    $directory = Get-AICarmineObserverChildDirectory -Root $Root -Name 'post-observations'
    if ([string]::IsNullOrEmpty($directory)) { throw 'post_observation_directory_unavailable' }
    $name = 'post-observation-{0}-{1}.json' -f [DateTime]::UtcNow.Ticks, [Guid]::NewGuid().ToString('N')
    Write-AICarmineObserverJson -Path (Join-Path $directory $name) -Value $Observation
    $files = @(Get-ChildItem -LiteralPath $directory -Filter 'post-observation-*.json' -File -Force |
        Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
        Sort-Object LastWriteTimeUtc -Descending)
    if ($files.Count -gt 128) {
        foreach ($file in @($files | Select-Object -Skip 128)) {
            Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
        }
    }
}

function Get-AICarmineClinePostToolObservation {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$RawInput)

    try {
        $payload = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $identity = Get-AICarmineTaskIdentity -Payload $payload
        $root = Get-AICarmineObserverRoot
        if ([string]::IsNullOrEmpty($root)) { throw 'observer_root_unavailable' }
        $toolMetadata = Get-AICarmineToolCallMetadata -Payload $payload
        $outcomeMetadata = Get-AICarminePostOutcomeMetadata -Payload $payload
        $taskKey = ''
        if ($null -ne $identity) { $taskKey = $identity.TaskKeySha256 }

        $stateFound = $false
        $correlationStatus = 'routing_state_missing'
        $correlationMethod = 'none'
        $lockStatus = 'not_required'
        $lockWait = 0
        $matched = $null
        $lockResult = $null

        if (-not [string]::IsNullOrEmpty($taskKey)) {
            try {
                $lockResult = Enter-AICarmineTaskStateMutex -TaskKeySha256 $taskKey
                $lockStatus = [string]$lockResult.Status
                $lockWait = [int]$lockResult.WaitMilliseconds
                if (-not $lockResult.Acquired) {
                    if ($lockStatus -eq 'timeout') { $correlationStatus = 'lock_timeout' }
                    else { $correlationStatus = 'lock_error' }
                }
                else {
                    $stateResult = Get-AICarmineValidatedRoutingState -Root $root -TaskKeySha256 $taskKey
                    $stateFound = [bool]$stateResult.Found
                    if (-not $stateFound) {
                        $correlationStatus = 'routing_state_missing'
                    }
                    else {
                        $state = $stateResult.State
                        $pending = @(Get-AICarmineBoundedPendingCalls -Records $state.pending_tool_calls)
                        $outcomes = @(Get-AICarmineBoundedRecentOutcomes -Records $state.recent_tool_outcomes)
                        $candidates = @()

                        if (-not [string]::IsNullOrEmpty($toolMetadata.InvocationKeySha256)) {
                            $candidates = @($pending | Where-Object { $_.invocation_key_sha256 -eq $toolMetadata.InvocationKeySha256 })
                            if ($candidates.Count -eq 1) {
                                $matched = $candidates[0]; $correlationStatus = 'correlated'; $correlationMethod = 'invocation_id'
                            }
                            elseif ($candidates.Count -gt 1) { $correlationStatus = 'ambiguous' }
                        }
                        if ($null -eq $matched -and $correlationStatus -ne 'ambiguous' -and -not [string]::IsNullOrEmpty($toolMetadata.ToolCallSha256)) {
                            $candidates = @($pending | Where-Object { $_.tool_call_sha256 -eq $toolMetadata.ToolCallSha256 })
                            if ($candidates.Count -eq 1) {
                                $matched = $candidates[0]; $correlationStatus = 'correlated'; $correlationMethod = 'tool_call_sha256'
                            }
                            elseif ($candidates.Count -gt 1) { $correlationStatus = 'ambiguous' }
                        }
                        if ($null -eq $matched -and $correlationStatus -ne 'ambiguous' -and
                            ([string]::IsNullOrEmpty($toolMetadata.InvocationKeySha256) -or -not [string]::IsNullOrEmpty($toolMetadata.ToolCallSha256))) {
                            $candidates = @($pending | Where-Object { Test-AICarminePostIdentityMatch -Pending $_ -Metadata $toolMetadata })
                            if ($candidates.Count -eq 1) {
                                $matched = $candidates[0]; $correlationStatus = 'correlated'; $correlationMethod = 'unique_identity'
                            }
                            elseif ($candidates.Count -gt 1) { $correlationStatus = 'ambiguous' }
                            else { $correlationStatus = 'missing' }
                        }
                        elseif ($null -eq $matched -and $correlationStatus -ne 'ambiguous') { $correlationStatus = 'missing' }

                        if ($correlationStatus -eq 'correlated') {
                            $pending = @($pending | Where-Object { $_ -ne $matched })
                            $invocationDigest = [string]$matched.invocation_key_sha256
                            $callDigest = [string]$matched.tool_call_sha256
                            if (-not [string]::IsNullOrEmpty($invocationDigest)) {
                                $outcomes = @($outcomes | Where-Object { $_.invocation_key_sha256 -ne $invocationDigest })
                            }
                            $outcomes += [ordered]@{
                                timestamp_utc = [DateTime]::UtcNow.ToString('o')
                                invocation_key_sha256 = $invocationDigest
                                tool_call_sha256 = $callDigest
                                selected_tool_kind = [string]$matched.selected_tool_kind
                                selected_wrapper_tool_name = [string]$matched.selected_wrapper_tool_name
                                selected_mcp_server_name = [string]$matched.selected_mcp_server_name
                                selected_mcp_tool_name = [string]$matched.selected_mcp_tool_name
                                outcome = $outcomeMetadata.Outcome
                                failure_signal = $outcomeMetadata.FailureSignal
                                correlation_method = $correlationMethod
                                result_sha256 = $outcomeMetadata.ResultSha256
                                error_type = $outcomeMetadata.ErrorType
                                error_message_sha256 = $outcomeMetadata.ErrorMessageSha256
                            }
                        }
                        $state.pending_tool_calls = @($pending | Select-Object -Last 32)
                        $state.recent_tool_outcomes = @($outcomes | Select-Object -Last 32)
                        Write-AICarmineObserverJsonAtomic -Root $root -Path $stateResult.Path -Value $state
                    }
                }
            }
            finally { Exit-AICarmineTaskStateMutex -Mutex $lockResult }
        }

        if ($null -ne $matched) {
            if ([string]::IsNullOrEmpty($toolMetadata.InvocationKeySha256)) {
                $toolMetadata.InvocationKeySha256 = [string]$matched.invocation_key_sha256
            }
            if ([string]::IsNullOrEmpty($toolMetadata.ToolCallSha256)) {
                $toolMetadata.ToolCallSha256 = [string]$matched.tool_call_sha256
            }
        }

        $codes = [Collections.Generic.List[string]]::new()
        [void]$codes.Add(('tool_outcome_{0}' -f $outcomeMetadata.Outcome))
        switch ($correlationStatus) {
            'correlated' { [void]$codes.Add(('correlated_by_{0}' -f $correlationMethod)) }
            'ambiguous' { [void]$codes.Add('correlation_ambiguous') }
            'missing' { [void]$codes.Add('pretool_observation_missing') }
            'routing_state_missing' { [void]$codes.Add('routing_state_missing') }
            'lock_timeout' { [void]$codes.Add('state_lock_timeout') }
            'lock_error' { [void]$codes.Add('state_lock_error') }
        }
        $contextModification = ''
        if ($correlationStatus -eq 'correlated' -and $outcomeMetadata.Outcome -eq 'failure') {
            $contextModification = 'AICARMINE POST-TOOL OBSERVATION: the correlated tool call produced an observed failure. Do not repeat the same call unchanged. Diagnose the failing stage before selecting a fallback.'
        }
        if ($contextModification.Length -gt 500) { $contextModification = $contextModification.Substring(0, 500) }
        $observation = [ordered]@{
            schema = 'aicarmine.cline.posttool-observation.v1'
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            task_key_sha256 = $taskKey
            routing_state_found = $stateFound
            correlation_status = $correlationStatus
            correlation_method = $correlationMethod
            invocation_key_sha256 = $toolMetadata.InvocationKeySha256
            tool_call_sha256 = $toolMetadata.ToolCallSha256
            selected_tool_kind = $toolMetadata.SelectedToolKind
            selected_wrapper_tool_name = $toolMetadata.SelectedWrapperToolName
            selected_mcp_server_name = $toolMetadata.SelectedMcpServerName
            selected_mcp_tool_name = $toolMetadata.SelectedMcpToolName
            outcome = $outcomeMetadata.Outcome
            failure_signal = $outcomeMetadata.FailureSignal
            result_type = $outcomeMetadata.ResultType
            result_sha256 = $outcomeMetadata.ResultSha256
            result_utf8_bytes = [int]$outcomeMetadata.ResultUtf8Bytes
            error_type = $outcomeMetadata.ErrorType
            error_message_sha256 = $outcomeMetadata.ErrorMessageSha256
            error_message_utf8_bytes = [int]$outcomeMetadata.ErrorMessageUtf8Bytes
            advisory_codes = @($codes)
            context_modification_emitted = -not [string]::IsNullOrEmpty($contextModification)
            state_lock_status = $lockStatus
            state_lock_wait_ms = $lockWait
        }
        Write-AICarminePostObservationLog -Root $root -Observation $observation
        return [pscustomobject]@{ contextModification = $contextModification; observation = [pscustomobject]$observation }
    }
    catch { return [pscustomobject]@{ contextModification = ''; observation = $null } }
}
