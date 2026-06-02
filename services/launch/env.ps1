# Shared launcher environment helpers.
# Keep Python env cleanup before any venv-backed process starts.

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

function Set-UserEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    # Avoid registry writes when the User value is already correct.
    $Current = [Environment]::GetEnvironmentVariable($Name, "User")

    if ($Current -ne $Value) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    }

    return $Value
}

function Clear-UserEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -ne [Environment]::GetEnvironmentVariable($Name, "User")) {
        [Environment]::SetEnvironmentVariable($Name, $null, "User")
    }
}

function Set-UserEnvDefault {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $Current = [Environment]::GetEnvironmentVariable($Name, "User")

    if ([string]::IsNullOrWhiteSpace($Current)) {
        [Environment]::SetEnvironmentVariable($Name, $DefaultValue, "User")
        return $DefaultValue
    }

    return $Current
}

function Set-EnvironmentVariables {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Variables,

        [switch]$Persistent
    )

    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        if ($Persistent) {
            $null = Set-UserEnvValue $key $value
        }
        Set-Item -Path "Env:$key" -Value $value
    }
}

function Get-OrCreate-WebUISecret {
    $Current = [Environment]::GetEnvironmentVariable("WEBUI_SECRET_KEY", "User")

    if (-not [string]::IsNullOrWhiteSpace($Current)) {
        return $Current.Trim()
    }

    # $AI_ROOT is not guaranteed before runtime configuration is initialized.
    $SecretFile = "C:\Users\carmi\AI\venvs\openwebui\.webui_secret_key"

    if (Test-Path $SecretFile) {
        $Secret = (Get-Content $SecretFile -Raw).Trim()
    }
    else {
        $Bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
        $Secret = ($Bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    }

    $null = Set-UserEnvValue "WEBUI_SECRET_KEY" $Secret
    return $Secret
}
