# File Integrity Monitor for Windows Security Posture
# Monitors critical system files and generates hash baselines
# Usage: .\file_integrity_monitor.ps1 [-Action: baseline|check|report]

param(
    [ValidateSet("baseline", "check", "report")]
    [string]$Action = "baseline",
    [string]$OutputPath = "C:\Users\sanit\agentic-tool-loop\output\security\file_integrity.json"
)

# Critical paths to monitor
$CriticalPaths = @(
    "C:\Windows\System32",
    "C:\Program Files",
    "C:\Program Files (x86)",
    "C:\Windows",
    "$env:APPDATA\Startup",
    "$env:LOCALAPPDATA\Programs"
)

# Critical executables to track
$CriticalExecutables = @(
    "C:\Windows\System32\cmd.exe",
    "C:\Windows\System32\powershell.exe",
    "C:\Windows\System32\net.exe",
    "C:\Windows\System32\net1.exe",
    "C:\Windows\System32\sc.exe",
    "C:\Windows\System32\reg.exe",
    "C:\Windows\System32\taskmgr.exe",
    "C:\Windows\System32\services.msc",
    "C:\Windows\System32\msconfig.exe"
)

function Get-FileHashes {
    param(
        [string[]]$Paths,
        [bool]$Recursive
    )
    
    $hashes = @{}
    
    foreach ($path in $Paths) {
        if (Test-Path $path) {
            if ((Get-Item $path).PSIsContainer -eq $true) {
                if ($Recursive) {
                    $files = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
                        $_.Extension -match '\.(exe|dll|sys|ps1|bat|cmd)'
                    }
                    foreach ($file in $files) {
                        try {
                            $hash = Get-FileHash $file.FullName -Algorithm SHA256
                            $hashes[$file.FullName] = $hash.Hash
                        } catch {}
                    }
                } else {
                    $files = Get-ChildItem $path -File -ErrorAction SilentlyContinue
                    foreach ($file in $files) {
                        try {
                            $hash = Get-FileHash $file.FullName -Algorithm SHA256
                            $hashes[$file.FullName] = $hash.Hash
                        } catch {}
                    }
                }
            } else {
                try {
                    $hash = Get-FileHash $path -Algorithm SHA256
                    $hashes[$path] = $hash.Hash
                } catch {}
            }
        }
    }
    
    return $hashes
}

function Create-Baseline {
    Write-Host "Creating file integrity baseline..." -ForegroundColor Cyan
    
    $baseline = @{
        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        action = "baseline"
        critical_executables = @{}
        system_directory_hashes = @{}
        program_files_hashes = @{}
        startup_scripts = @{}
    }
    
    # Hash critical executables
    foreach ($exe in $CriticalExecutables) {
        if (Test-Path $exe) {
            try {
                $hash = Get-FileHash $exe -Algorithm SHA256
                $baseline.critical_executables[$exe] = $hash.Hash
            } catch {
                Write-Host "  Warning: Could not hash $exe" -ForegroundColor Yellow
            }
        }
    }
    
    # Hash System32 directory (limited to prevent excessive output)
    Write-Host "  Hashing C:\Windows\System32 (executables only)..." -ForegroundColor Gray
    try {
        $systemFiles = Get-ChildItem "C:\Windows\System32" -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Extension -match '\.(exe|dll|sys)' -and $_.Length -gt 1000
        } | Select-Object -First 500
        foreach ($file in $systemFiles) {
            try {
                $hash = Get-FileHash $file.FullName -Algorithm SHA256
                $baseline.system_directory_hashes[$file.FullName] = $hash.Hash
            } catch {}
        }
    } catch {
        Write-Host "  Error hashing System32: $_" -ForegroundColor Red
    }
    
    # Hash startup scripts
    $startupPath = "$env:APPDATA\Startup"
    if (Test-Path $startupPath) {
        $startupFiles = Get-ChildItem $startupPath -ErrorAction SilentlyContinue | Where-Object {
            $_.Extension -match '\.(ps1|bat|cmd)'
        }
        foreach ($file in $startupFiles) {
            try {
                $hash = Get-FileHash $file.FullName -Algorithm SHA256
                $baseline.startup_scripts[$file.FullName] = $hash.Hash
            } catch {}
        }
    }
    
    # Ensure output directory exists
    $outputDir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    
    # Save baseline
    $baseline | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8
    
    Write-Host "  Baseline saved to $OutputPath" -ForegroundColor Green
    Write-Host "  Critical executables tracked: $($baseline.critical_executables.Count)" -ForegroundColor Gray
    Write-Host "  System files tracked: $($baseline.system_directory_hashes.Count)" -ForegroundColor Gray
    Write-Host "  Startup scripts tracked: $($baseline.startup_scripts.Count)" -ForegroundColor Gray
}

function Check-Integrity {
    Write-Host "Checking file integrity against baseline..." -ForegroundColor Cyan
    
    if (-not (Test-Path $OutputPath)) {
        Write-Host "  ERROR: No baseline found. Run with -Action baseline first." -ForegroundColor Red
        return @{ error = "No baseline available" }
    }
    
    $baseline = Get-Content $OutputPath | ConvertFrom-Json
    
    $violations = @()
    $unchanged = 0
    
    # Check critical executables
    foreach ($exe in $baseline.critical_executables.Keys) {
        if (Test-Path $exe) {
            try {
                $currentHash = (Get-FileHash $exe -Algorithm SHA256).Hash
                if ($currentHash -ne $baseline.critical_executables[$exe]) {
                    $violations += @{
                        type = "modified"
                        path = $exe
                        old_hash = $baseline.critical_executables[$exe]
                        new_hash = $currentHash
                        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
                    }
                    Write-Host "  VIOLATION: $exe modified!" -ForegroundColor Red
                } else {
                    $unchanged++
                }
            } catch {
            Write-Host "  Error checking ${exe}: ${_}" -ForegroundColor Yellow
            }
        } else {
            $violations += @{
                type = "deleted"
                path = $exe
                baseline_hash = $baseline.critical_executables[$exe]
                timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
            }
            Write-Host "  VIOLATION: $exe deleted!" -ForegroundColor Red
        }
    }
    
    # Check startup scripts
    foreach ($script in $baseline.startup_scripts.Keys) {
        if (Test-Path $script) {
            try {
                $currentHash = (Get-FileHash $script -Algorithm SHA256).Hash
                if ($currentHash -ne $baseline.startup_scripts[$script]) {
                    $violations += @{
                        type = "modified"
                        path = $script
                        old_hash = $baseline.startup_scripts[$script]
                        new_hash = $currentHash
                        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
                    }
                    Write-Host "  VIOLATION: $script modified!" -ForegroundColor Red
                } else {
                    $unchanged++
                }
            } catch {}
        } else {
            $violations += @{
                type = "deleted"
                path = $script
                baseline_hash = $baseline.startup_scripts[$script]
                timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
            }
        }
    }
    
    $result = @{
        check_time = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        baseline_time = $baseline.timestamp
        violations_found = $violations.Count
        unchanged_files = $unchanged
        violations = $violations
    }
    
    return $result
}

function Get-SecurityReport {
    Write-Host "Generating security report..." -ForegroundColor Cyan
    
    $report = @{
        report_time = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        system_info = @{
            hostname = $env:COMPUTERNAME
            username = $env:USERNAME
            os_version = (Get-CimInstance -ClassName Win32_OperatingSystem).Caption
        }
        file_integrity_status = if (Test-Path $OutputPath) {
            $baseline = Get-Content $OutputPath | ConvertFrom-Json
            @{
                baseline_exists = $true
                baseline_time = $baseline.timestamp
                tracked_executables = $baseline.critical_executables.Count
                tracked_system_files = $baseline.system_directory_hashes.Count
            }
        } else {
            @{ baseline_exists = $false; message = "No baseline available" }
        }
    }
    
    $report.active_processes = @()
    $report.network_connections = @()
    
    # Get running processes
    $processes = Get-Process | Where-Object {
        $_.Name -notin @('System', 'Idle')
    } | Select-Object Name, Id, Path, WorkingSet, StartTime | Sort-Object WorkingSet -Descending | Select-Object -First 50
    
    $report.active_processes = $processes
    
    # Get network connections
    $connections = Get-NetTCPConnection | Where-Object {
        $_.State -notin @('Closed', 'Listen', 'TimeWait')
    } | Select-Object OwningProcess, RemoteAddress, RemotePort, State | Sort-Object OwningProcess
    
    $report.network_connections = $connections
    
    # Save report
    $reportPath = "C:\Users\sanit\agentic-tool-loop\output\security\security_report.json"
    $reportDir = Split-Path $reportPath -Parent
    if (-not (Test-Path $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content $reportPath -Encoding UTF8
    
    Write-Host "  Report saved to $reportPath" -ForegroundColor Green
    Write-Host "  Processes tracked: $($processes.Count)" -ForegroundColor Gray
    Write-Host "  Active connections: $($connections.Count)" -ForegroundColor Gray
}

# Main execution
switch ($Action) {
    "baseline" { Create-Baseline }
    "check" { Check-Integrity }
    "report" { Get-SecurityReport }
}