# Shared launcher Ollama helpers.

function Test-OllamaEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Test-HttpEndpoint -Url "$Url/api/tags" -ValidateProperty 'models'
}

function Start-EndpointScriptIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Script
    )

    if (-not (Test-Path $Script)) {
        throw "$Name script non trovato: $Script"
    }

    if (Test-OllamaEndpoint $Url) {
        Write-Host "$Name gia' attivo e sano su $Url"
        return
    }

    $Owner = Get-PortOwner -Port $Port
    if ($null -ne $Owner) {
        Write-Warning "$($Name): porta $Port occupata ma endpoint non sano."
        Write-Warning "PID=$($Owner.ProcessId) Name=$($Owner.Name)"
        Write-Warning "CommandLine=$($Owner.CommandLine)"
        throw "$Name bloccato: porta $Port occupata da processo non sano."
    }

    Write-Host "Avvio $Name su $Url..."

    $Proc = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "$Name processo avviato: PID=$($Proc.Id)"

    for ($i = 0; $i -lt 60; $i++) {
        if (Test-OllamaEndpoint $Url) {
            Write-Host "$Name attivo e sano su $Url"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "$Name non risponde correttamente su $Url dopo 60 secondi"
}

function Ensure-OllamaModel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [string]$HostPort,

        [Parameter(Mandatory = $true)]
        [string]$Model,

        [Parameter(Mandatory = $true)]
        [string]$BaseModel,

        [Parameter(Mandatory = $true)]
        [string]$ModelFile
    )

    if (-not (Test-Path $ModelFile)) {
        throw "Modelfile non trovato: $ModelFile"
    }

    if (-not (Test-OllamaEndpoint $Url)) {
        throw "Endpoint Ollama non sano: $Url"
    }

    $Tags = Invoke-RestMethod -Uri "$Url/api/tags" -TimeoutSec 10
    $Names = @($Tags.models | ForEach-Object { $_.name })

    if ($Names -contains $Model -or $Names -contains "$Model`:latest") {
        Write-Host "$Model gia' presente su $HostPort"
        return
    }

    $OllamaExe = (Get-Command ollama.exe -ErrorAction Stop).Source
    $PreviousOllamaHost = $env:OLLAMA_HOST

    try {
        $env:OLLAMA_HOST = $HostPort

        Write-Host "$Model non presente su $HostPort. Pull base model $BaseModel..."
        & $OllamaExe pull $BaseModel

        Write-Host "Creazione $Model su $HostPort..."
        & $OllamaExe create $Model -f $ModelFile
    }
    finally {
        if ([string]::IsNullOrWhiteSpace($PreviousOllamaHost)) {
            Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue
        }
        else {
            $env:OLLAMA_HOST = $PreviousOllamaHost
        }
    }
}
