param(
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Continue"

$SyncScript = "C:\Users\carmi\AI\services\sync-lab-from-main.ps1"
$LogDir = "C:\Users\carmi\AI\logs"
$LogFile = Join-Path $LogDir "lab-mirror-watchdog.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)

    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

if (-not (Test-Path $SyncScript)) {
    throw "Sync script non trovato: $SyncScript"
}

Write-Log "Lab mirror watchdog avviato. IntervalSeconds=$IntervalSeconds"

while ($true) {
    $enabled = [Environment]::GetEnvironmentVariable("ENABLE_AICARMINE_LAB_MIRROR", "User")

    if ([string]::IsNullOrWhiteSpace($enabled)) {
        $enabled = "0"
        [Environment]::SetEnvironmentVariable("ENABLE_AICARMINE_LAB_MIRROR", $enabled, "User")
    }

    if ($enabled -eq "1") {
        try {
            Write-Log "Mirror enabled. Avvio sync."
            powershell -NoProfile -ExecutionPolicy Bypass -File $SyncScript -Quiet
            Write-Log "Sync OK."
        }
        catch {
            Write-Log "Sync ERROR: $($_.Exception.Message)"
        }
    }
    else {
        Write-Log "Mirror disabled. ENABLE_AICARMINE_LAB_MIRROR=$enabled"
    }

    Start-Sleep -Seconds $IntervalSeconds
}