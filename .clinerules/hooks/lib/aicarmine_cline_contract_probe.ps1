# AICarmine Cline Hook Contract Probe Helper
# Persists bounded structural metadata only; raw hook input is never persisted.

function Write-AICarmineHookContractProbe {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$HookName,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    try {
        function Get-AICarmineValueType {
            param($Value)

            if ($null -eq $Value) { return 'null' }
            if ($Value -is [bool]) { return 'boolean' }
            if ($Value -is [string]) { return 'string' }
            if ($Value -is [byte] -or
                $Value -is [sbyte] -or
                $Value -is [int16] -or
                $Value -is [uint16] -or
                $Value -is [int32] -or
                $Value -is [uint32] -or
                $Value -is [int64] -or
                $Value -is [uint64]) { return 'integer' }
            if ($Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) { return 'number' }
            if ($Value -is [array]) { return 'array' }
            if ($Value -is [System.Collections.IDictionary] -or $Value -is [pscustomobject]) { return 'object' }
            return 'unknown'
        }

        function Test-AICarmineSensitiveKey {
            param([string]$Name)

            return $Name -match '(?i)(authorization|token|secret|password|api[-_]?key|credential|cookie)'
        }

        function Get-AICarmineShape {
            param(
                $Value,
                [int]$Depth = 0
            )

            $valueType = Get-AICarmineValueType -Value $Value
            if ($Depth -ge 3) {
                return [ordered]@{
                    type = $valueType
                    truncated = $true
                }
            }

            if ($valueType -eq 'array') {
                $elementTypes = [System.Collections.Generic.List[string]]::new()
                $elementLimit = [Math]::Min($Value.Count, 16)
                for ($index = 0; $index -lt $elementLimit; $index++) {
                    $elementType = Get-AICarmineValueType -Value $Value[$index]
                    if (-not $elementTypes.Contains($elementType)) {
                        $elementTypes.Add($elementType)
                    }
                }
                return [ordered]@{
                    type = 'array'
                    count = $Value.Count
                    element_types = @($elementTypes.ToArray())
                    elements_truncated = ($Value.Count -gt $elementLimit)
                }
            }

            if ($valueType -eq 'object') {
                $properties = [System.Collections.Generic.List[object]]::new()
                $sourceProperties = @($Value.PSObject.Properties)
                $propertyLimit = [Math]::Min($sourceProperties.Count, 32)
                for ($index = 0; $index -lt $propertyLimit; $index++) {
                    $property = $sourceProperties[$index]
                    if (Test-AICarmineSensitiveKey -Name $property.Name) {
                        $properties.Add([ordered]@{
                            name = '[redacted]'
                            type = (Get-AICarmineValueType -Value $property.Value)
                            redacted = $true
                        })
                    }
                    else {
                        $properties.Add([ordered]@{
                            name = $property.Name
                            shape = (Get-AICarmineShape -Value $property.Value -Depth ($Depth + 1))
                        })
                    }
                }
                return [ordered]@{
                    type = 'object'
                    key_count = $sourceProperties.Count
                    properties = @($properties.ToArray())
                    keys_truncated = ($sourceProperties.Count -gt $propertyLimit)
                }
            }

            return [ordered]@{ type = $valueType }
        }

        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $rawBytes = $utf8.GetBytes($RawInput)
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hashBytes = $sha256.ComputeHash($rawBytes)
        }
        finally {
            $sha256.Dispose()
        }
        $rawSha256 = ($hashBytes | ForEach-Object { '{0:x2}' -f $_ }) -join ''

        $parseOk = $false
        $parsedInput = $null
        try {
            $parsedInput = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
            $parseOk = $true
        }
        catch {
            $parseOk = $false
        }

        $topLevelKeys = @()
        $shape = $null
        if ($parseOk) {
            $shape = Get-AICarmineShape -Value $parsedInput
            if ((Get-AICarmineValueType -Value $parsedInput) -eq 'object') {
                $sourceProperties = @($parsedInput.PSObject.Properties)
                $keyLimit = [Math]::Min($sourceProperties.Count, 32)
                for ($index = 0; $index -lt $keyLimit; $index++) {
                    $keyName = [string]$sourceProperties[$index].Name
                    if (Test-AICarmineSensitiveKey -Name $keyName) {
                        $topLevelKeys += '[redacted]'
                    }
                    else {
                        $topLevelKeys += $keyName
                    }
                }
                $topLevelKeys = @($topLevelKeys | Sort-Object -Unique)
            }
        }

        $tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        $probeDirectory = [System.IO.Path]::GetFullPath(
            (Join-Path $tempBase 'aicarmine-cline-hooks\contract-probe')
        )
        if (-not $probeDirectory.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
            return
        }
        [void][System.IO.Directory]::CreateDirectory($probeDirectory)

        $safeHookName = ($HookName -replace '[^A-Za-z0-9_-]', '-').ToLowerInvariant()
        $fileName = '{0}-{1}-{2}-{3}.json' -f (
            [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fffffff')
        ), $safeHookName, $PID, [Guid]::NewGuid().ToString('N')
        $probePath = Join-Path $probeDirectory $fileName

        $output = [ordered]@{
            schema = 'aicarmine.hook.contract.v1'
            hook_name = $HookName
            timestamp_utc = [DateTime]::UtcNow.ToString('o')
            process_id = $PID
            parse_ok = $parseOk
            parse_error_type = $(if ($parseOk) { $null } else { 'JsonParseError' })
            raw_utf8_bytes = $rawBytes.Length
            raw_sha256 = $rawSha256
            top_level_keys = @($topLevelKeys)
            shape = $shape
        }

        $json = $output | ConvertTo-Json -Depth 12
        [System.IO.File]::WriteAllText($probePath, $json, $utf8)
    }
    catch {
        # Probe failures must never affect hook behavior or emit diagnostics.
    }
}
