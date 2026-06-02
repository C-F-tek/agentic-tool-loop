# Shared launcher process helpers.

function Get-PortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        $Conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1

        if ($null -eq $Conn) {
            return $null
        }

        return Get-CimInstance Win32_Process -Filter "ProcessId=$($Conn.OwningProcess)" |
            Select-Object ProcessId,Name,CommandLine
    }
    catch {
        return $null
    }
}

function Stop-PortOwner {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $false)]
        [string]$LocalAddress = "127.0.0.1"
    )

    try {
        $conns = Get-NetTCPConnection -LocalAddress $LocalAddress -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

        foreach ($conn in $conns) {
            if ($null -ne $conn.OwningProcess -and $conn.OwningProcess -gt 0) {
                Write-Host "Stop $Label port=$Port PID=$($conn.OwningProcess)"
                Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        Write-Warning "Impossibile controllare porta $Port ($Label): $($_.Exception.Message)"
    }
}

function Start-OpenVINOProviderIfEnabled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Enabled,

        [Parameter(Mandatory = $true)]
        [string]$Script,

        [Parameter(Mandatory = $true)]
        [string]$HealthUrl,

        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    if ($Enabled -ne "1") {
        Write-Host "OpenVINO/NPU provider disabilitato. ENABLE_OPENVINO_PROVIDER=$Enabled"
        return
    }

    if (Test-HttpHealth $HealthUrl) {
        Write-Host "OpenVINO/NPU provider gia' attivo: $HealthUrl"
        return
    }

    if (-not (Test-Path $Script)) {
        throw "ENABLE_OPENVINO_PROVIDER=1 ma script provider non trovato: $Script"
    }

    $Owner = Get-PortOwner -Port $Port
    if ($null -ne $Owner) {
        Write-Warning "OpenVINO/NPU provider: porta $Port occupata ma health non sano."
        Write-Warning "PID=$($Owner.ProcessId) Name=$($Owner.Name)"
        Write-Warning "CommandLine=$($Owner.CommandLine)"
        throw "OpenVINO/NPU provider bloccato: porta $Port occupata da processo non sano."
    }

    Write-Host "Avvio OpenVINO/NPU provider su porta $Port..."

    $Proc = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$Script`"" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "OpenVINO/NPU provider processo avviato: PID=$($Proc.Id)"

    for ($i = 0; $i -lt 60; $i++) {
        if (Test-HttpHealth $HealthUrl) {
            Write-Host "OpenVINO/NPU provider attivo: $HealthUrl"
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "OpenVINO/NPU provider non risponde su $HealthUrl dopo 60 secondi"
}
