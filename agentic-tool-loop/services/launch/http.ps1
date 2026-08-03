# Shared launcher HTTP helpers.

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $false)]
        [int]$TimeoutSec = 5,

        [Parameter(Mandatory = $false)]
        [string]$ValidateProperty
    )

    try {
        $Response = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec
        if ($PSBoundParameters.ContainsKey('ValidateProperty')) {
            return ($null -ne $Response.$ValidateProperty)
        }
        return ($null -ne $Response)
    }
    catch {
        return $false
    }
}

function Test-HttpHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Test-HttpEndpoint -Url $Url
}
