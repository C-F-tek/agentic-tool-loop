$ErrorActionPreference = "Stop"

$Root = "C:\Users\carmi\AI\services"
$Py = [Environment]::GetEnvironmentVariable("AICARMINE_LABTOOLS_PYTHON", "User")
if ([string]::IsNullOrWhiteSpace($Py)) {
    $Py = "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"
}
if (-not (Test-Path $Py)) {
    throw "Python labtools non trovato: $Py"
}

function Set-EnvDefault {
    param([string]$Name, [string]$Value)
    $current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($current)) {
        $current = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    if ([string]::IsNullOrWhiteSpace($current)) {
        $current = $Value
    }
    Set-Item -Path "Env:$Name" -Value $current
}

# Vulkan/task Ollama backend. This model selects/corrects the internal repo tool.
# The public OpenWebUI tool wrapper is deterministic inside the 3572 broker.
Set-EnvDefault "AICARMINE_VULKAN_BROKER_OLLAMA_URL" "http://127.0.0.1:11435/api/chat"
Set-EnvDefault "AICARMINE_VULKAN_BROKER_MODEL" "qwen3-task-8k"
Set-EnvDefault "AICARMINE_LAB_REPO" "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
Set-EnvDefault "AICARMINE_REAL_REPO" "C:\Users\carmi\ProjectsDir\blender-audio-project"
Set-EnvDefault "AICARMINE_VULKAN_MAX_TOOL_RESULT_CHARS" "9000"
Set-EnvDefault "AICARMINE_VULKAN_NUM_CTX" "12288"
Set-EnvDefault "AICARMINE_VULKAN_NUM_PREDICT" "768"
Set-EnvDefault "AICARMINE_VULKAN_INTERPRETER_NUM_PREDICT" "1024"
Set-EnvDefault "AICARMINE_VULKAN_WRAPPER_NUM_PREDICT" "1536"
Set-EnvDefault "AICARMINE_VULKAN_TEMPERATURE" "0"
Set-EnvDefault "AICARMINE_VULKAN_KEEP_ALIVE" "5m"

# Bridge -> Agent split.
# Register ONLY http://127.0.0.1:3571/openapi.json in OpenWebUI.
# The agent on 3572 is internal and should not be registered as an OpenWebUI tool.
Set-EnvDefault "AICARMINE_VULKAN_AGENT_URL" "http://127.0.0.1:3572/vulkan/agent"
Set-EnvDefault "AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS" "360"

function Test-HttpJson {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $r = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec
        return ($null -ne $r)
    } catch {
        return $false
    }
}

function Get-PortListeners {
    param([int]$Port)
    return @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess -Unique)
}

function Get-ProcessLabel {
    param([int]$OwnerPid)
    try {
        $proc = Get-Process -Id $OwnerPid -ErrorAction Stop
        if ($proc.Path) { return "$($proc.ProcessName) PID=$OwnerPid path=$($proc.Path)" }
        return "$($proc.ProcessName) PID=$OwnerPid"
    } catch {
        return "PID=$OwnerPid"
    }
}

function New-ElevatedKillCommand {
    param([int[]]$OwnerPids)
    $pidList = ($OwnerPids | Sort-Object -Unique) -join ","
    return "Start-Process PowerShell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command `$pids=@($pidList); foreach(`$p in `$pids){ taskkill /PID `$p /T /F }'"
}

function Assert-PortFree {
    param([int]$Port, [string]$Label)
    $listeners = Get-PortListeners -Port $Port
    if ($listeners.Count -eq 0) { return }

    $ownerPids = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
    $details = @($ownerPids | ForEach-Object { Get-ProcessLabel -OwnerPid $_ }) -join "; "
    $elevated = New-ElevatedKillCommand -OwnerPids $ownerPids

    throw @"
Porta ${Port} ancora occupata da ${Label}: $details
Lo script non avvia nuovi server per evitare bind duplicati.
Esegui PowerShell come Amministratore oppure lancia questo comando:
$elevated
Poi rilancia: .\aicarmine-vulkan-tool-broker.ps1
"@
}

function Stop-PortOwner {
    param([int]$Port, [string]$Label)

    $listeners = Get-PortListeners -Port $Port
    if ($listeners.Count -eq 0) {
        Write-Host "${Label} port ${Port} already free"
        return
    }

    foreach ($listener in $listeners) {
        $ownerPid = [int]$listener.OwningProcess
        if ($ownerPid -le 0) { continue }
        Write-Host "Stopping ${Label} on port ${Port} PID=$ownerPid"
        try {
            Stop-Process -Id $ownerPid -Force -ErrorAction Stop
        } catch {
            Write-Warning "Stop-Process failed for PID=$ownerPid on port ${Port}: $($_.Exception.Message)"
            Write-Warning "Trying taskkill /T /F for PID=$ownerPid"
            & taskkill.exe /PID $ownerPid /T /F | Out-Host
        }
    }

    for ($i = 0; $i -lt 20; $i++) {
        if ((Get-PortListeners -Port $Port).Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    }

    Assert-PortFree -Port $Port -Label $Label
}

function Stop-StartedProcessTree {
    param([System.Diagnostics.Process]$Proc, [string]$Label)
    if ($null -eq $Proc) { return }
    try {
        if (-not $Proc.HasExited) {
            Write-Host "Stopping $Label PID=$($Proc.Id)"
            Stop-Process -Id $Proc.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Test-OllamaTask {
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/tags" -TimeoutSec 3
        return ($null -ne $tags.models)
    } catch {
        return $false
    }
}

Set-Location $Root

# Aggiungi services al PYTHONPATH prima di lanciare uvicorn
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = "$Root"
} else {
    # Assicurati che Root sia incluso in PYTHONPATH
    if ($env:PYTHONPATH -notlike "*$Root*") {
        $env:PYTHONPATH = "$Root;$env:PYTHONPATH"
    }
}

# Verifica che 'services' sia importabile
try {
    & $Py -c "import sys; print('PYTHONPATH:', sys.path); import services; print('OK: services imported')" 2>&1 | Out-Host
} catch {
    Write-Warning "Import test failed: $_"
}

$agentProc = $null
try {
    if (-not (Test-OllamaTask)) {
        throw "Ollama Task GPU0/Vulkan non raggiungibile su http://127.0.0.1:11435. Avvia prima ollama-task-vulkan.ps1 oppure openwebui.ps1."
    }

    Stop-PortOwner -Port 3571 -Label "old Vulkan Bridge"
    Stop-PortOwner -Port 3572 -Label "old Vulkan Agent"
    Assert-PortFree -Port 3571 -Label "old Vulkan Bridge"
    Assert-PortFree -Port 3572 -Label "old Vulkan Agent"

    Write-Host "Starting internal Vulkan Agent on 127.0.0.1:3572..."
    
    # Passa PYTHONPATH esplicitamente ad uvicorn invece di affidarsi all'ereditazione
    $uvicornArgs = @("-m", "uvicorn", "aicarmine_vulkan_tool_broker:app", "--host", "127.0.0.1", "--port", "3572")
    if ($env:PYTHONPATH) {
        $uvicornArgs = ("--extra-search-path", $env:PYTHONPATH) + $uvicornArgs
    }
    
    $agentProc = Start-Process `
        -FilePath $Py `
        -ArgumentList $uvicornArgs `
        -WorkingDirectory $Root `
        -Environment @{PYTHONPATH=$env:PYTHONPATH} `
        -WindowStyle Minimized `
        -PassThru

    for ($i = 0; $i -lt 60; $i++) {
        if ($agentProc.HasExited) {
            throw "Vulkan Agent interno terminato durante startup: PID=$($agentProc.Id) ExitCode=$($agentProc.ExitCode)"
        }
        if (Test-HttpJson "http://127.0.0.1:3572/health" 2) { break }
        Start-Sleep -Seconds 1
    }

    if (-not (Test-HttpJson "http://127.0.0.1:3572/health" 2)) {
        throw "Vulkan Agent interno non raggiungibile su http://127.0.0.1:3572/health"
    }

    Write-Host "AI-Carmine Vulkan Bridge:"
    Write-Host "  Bridge port     = 3571  (REGISTER THIS IN OPENWEBUI)"
    Write-Host "  Agent port      = 3572  (internal only)"
    Write-Host "  Agent URL       = $env:AICARMINE_VULKAN_AGENT_URL"
    Write-Host "  Ollama backend  = $env:AICARMINE_VULKAN_BROKER_OLLAMA_URL"
    Write-Host "  Backend model   = $env:AICARMINE_VULKAN_BROKER_MODEL"
    Write-Host "  OpenAPI         = http://127.0.0.1:3571/openapi.json"

    & $Py -m uvicorn aicarmine_vulkan_bridge_server:app --host 127.0.0.1 --port 3571
}
finally {
    Stop-StartedProcessTree -Proc $agentProc -Label "Vulkan Agent"
    Stop-PortOwner -Port 3572 -Label "Vulkan Agent cleanup"
}
