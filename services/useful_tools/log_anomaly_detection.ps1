# Log Anomaly Detection with Local AI (Ollama)
# Analyzes Windows security logs and detects anomalous behavior patterns
# Usage: .\log_anomaly_detection.ps1 [-Action: analyze|baseline|alert]

param(
    [ValidateSet("analyze", "baseline", "alert")]
    [string]$Action = "analyze",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$Model = "phi3:mini",
    [string]$OutputPath = "C:\Users\sanit\agentic-tool-loop\output\security\anomaly_report.json"
)

function Get-SecurityLogs {
    Write-Host "Collecting Windows Security Logs..." -ForegroundColor Cyan
    
    $logs = @{
        event_logs = @()
        failed_logons = @()
        privilege_escalations = @()
        new_services = @()
        modified_firewall_rules = @()
    }
    
    # Get failed logon attempts (Event ID 4625)
    try {
        $failedLogons = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id = 4625
            StartTime = (Get-Date).AddDays(-7)
        } -ErrorAction SilentlyContinue | Select-Object -First 100 | ForEach-Object {
            @{
                time = $_.TimeCreated
                username = $_.Properties[0].Value
                source_ip = $_.Properties[19].Value
                reason = $_.Properties[8].Value
            }
        }
        $logs.failed_logons = $failedLogons
    } catch {
        Write-Host "  Warning: Could not collect failed logons: $_" -ForegroundColor Yellow
    }
    
    # Get privilege escalation events (Event ID 4672)
    try {
        $privEsc = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id = 4672
            StartTime = (Get-Date).AddDays(-7)
        } -ErrorAction SilentlyContinue | Select-Object -First 50 | ForEach-Object {
            @{
                time = $_.TimeCreated
                username = $_.Properties[0].Value
                privileges = $_.Properties[2].Value
            }
        }
        $logs.privilege_escalations = $privEsc
    } catch {
        Write-Host "  Warning: Could not collect privilege escalation events: $_" -ForegroundColor Yellow
    }
    
    # Get new service creation events (Event ID 7045)
    try {
        $newServices = Get-WinEvent -FilterHashtable @{
            LogName = 'System'
            Id = 7045
            StartTime = (Get-Date).AddDays(-7)
        } -ErrorAction SilentlyContinue | Select-Object -First 50 | ForEach-Object {
            @{
                time = $_.TimeCreated
                service_name = $_.Properties[5].Value
                service_path = $_.Properties[6].Value
                run_type = $_.Properties[7].Value
            }
        }
        $logs.new_services = $newServices
    } catch {
        Write-Host "  Warning: Could not collect new service events: $_" -ForegroundColor Yellow
    }
    
    return $logs
}

function Analyze-WithOllama {
    param(
        [object]$Logs
    )
    
    Write-Host "Sending logs to Ollama for anomaly analysis..." -ForegroundColor Cyan
    
    # Convert logs to text format for AI analysis
    $logText = ""
    
    if ($Logs.failed_logons.Count -gt 0) {
        $logText += "Failed Logon Attempts (last 7 days):`n"
        foreach ($log in $Logs.failed_logons) {
            $logText += "  $($log.time) - User: $($log.username), Source: $($log.source_ip), Reason: $($log.reason)`n"
        }
    }
    
    if ($Logs.privilege_escalations.Count -gt 0) {
        $logText += "`nPrivilege Escalation Events:`n"
        foreach ($log in $Logs.privilege_escalations) {
            $logText += "  $($log.time) - User: $($log.username), Privileges: $($log.privileges)`n"
        }
    }
    
    if ($Logs.new_services.Count -gt 0) {
        $logText += "`nNew Service Creation Events:`n"
        foreach ($log in $Logs.new_services) {
            $logText += "  $($log.time) - Service: $($log.service_name), Path: $($log.service_path), Type: $($log.run_type)`n"
        }
    }
    
    # Build prompt for Ollama
    $prompt = @"
You are a security analyst AI. Analyze the following Windows security log events and identify anomalous patterns that could indicate:

1. Brute force attacks (multiple failed logons from same IP)
2. Privilege escalation attempts
3. Suspicious service installations
4. Lateral movement indicators
5. Data exfiltration attempts

Security Log Events:
$logText

Provide a structured analysis with:
- Risk level (LOW, MEDIUM, HIGH, CRITICAL)
- Anomaly descriptions
- Recommended actions
- Confidence score (0-100)
"@

    $requestBody = @{
        model = $Model
        prompt = $prompt
        stream = $false
    } | ConvertTo-Json

    try {
        $response = Invoke-RestMethod -Uri "$OllamaUrl/api/generate" -Method Post -Body $requestBody -ContentType "application/json"
        
        $analysis = @{
            analysis_time = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
            ollama_model = $Model
            ollama_url = $OllamaUrl
            ai_analysis = $response.response
            risk_level = if ($response.response -match 'CRITICAL') { 'CRITICAL' }
                        elseif ($response.response -match 'HIGH') { 'HIGH' }
                        elseif ($response.response -match 'MEDIUM') { 'MEDIUM' }
                        else { 'LOW' }
            log_summary = @{
                failed_logons = $Logs.failed_logons.Count
                privilege_escalations = $Logs.privilege_escalations.Count
                new_services = $Logs.new_services.Count
            }
        }
        
        return $analysis
    } catch {
        Write-Host "  Error connecting to Ollama: $_" -ForegroundColor Red
        return @{
            error = "Could not connect to Ollama at $OllamaUrl"
            model = $Model
            message = "Ensure Ollama is running and the model '$Model' is available"
        }
    }
}

function Create-AnomalyBaseline {
    Write-Host "Creating anomaly detection baseline..." -ForegroundColor Cyan
    
    $logs = Get-SecurityLogs
    
    $baseline = @{
        baseline_time = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        action = "baseline"
        failed_logon_average = if ($logs.failed_logons.Count -gt 0) {
            $logs.failed_logons.Count
        } else { 0 }
        privilege_escalation_average = if ($logs.privilege_escalations.Count -gt 0) {
            $logs.privilege_escalations.Count
        } else { 0 }
        new_service_average = if ($logs.new_services.Count -gt 0) {
            $logs.new_services.Count
        } else { 0 }
    }
    
    $outputDir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    
    $baseline | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8
    
    Write-Host "  Baseline saved to $OutputPath" -ForegroundColor Green
    Write-Host "  Failed logons baseline: $($baseline.failed_logon_average)" -ForegroundColor Gray
    Write-Host "  Privilege escalations baseline: $($baseline.privilege_escalation_average)" -ForegroundColor Gray
    Write-Host "  New services baseline: $($baseline.new_service_average)" -ForegroundColor Gray
}

function Check-Anomalies {
    Write-Host "Checking for security anomalies..." -ForegroundColor Cyan
    
    $logs = Get-SecurityLogs
    
    # Get baseline if available
    $baselinePath = "C:\Users\sanit\agentic-tool-loop\output\security\anomaly_baseline.json"
    $baseline = $null
    if (Test-Path $baselinePath) {
        $baseline = Get-Content $baselinePath | ConvertFrom-Json
    }
    
    $anomalies = @()
    
    # Check for brute force (>5 failed logons from same IP)
    if ($logs.failed_logons.Count -gt 5) {
        $anomalies += @{
            type = "brute_force_suspect"
            severity = "HIGH"
            description = "Multiple failed logon attempts detected"
            count = $logs.failed_logons.Count
            threshold = 5
            timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        }
    }
    
    # Check for privilege escalation spikes
    if ($logs.privilege_escalations.Count -gt 10) {
        $anomalies += @{
            type = "privilege_escalation_spike"
            severity = "MEDIUM"
            description = "Unusual number of privilege escalation events"
            count = $logs.privilege_escalations.Count
            threshold = 10
            timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        }
    }
    
    # Check for suspicious service installations
    foreach ($service in $logs.new_services) {
        $suspiciousPaths = @('Temp', 'AppData', 'ProgramData', 'Downloads')
        foreach ($path in $suspiciousPaths) {
            if ($service.service_path -like "*$path*" -or $service.run_type -like '*"%*"') {
                $anomalies += @{
                    type = "suspicious_service_install"
                    severity = "HIGH"
                    description = "Potentially suspicious service installation detected"
                    service_name = $service.service_name
                    service_path = $service.service_path
                    timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
                }
                break
            }
        }
    }
    
    # Analyze with Ollama if available
    $ai_analysis = $null
    try {
        $ai_analysis = Analyze-WithOllama -Logs $logs
    } catch {
        Write-Host "  AI analysis skipped: $_" -ForegroundColor Yellow
    }
    
    $result = @{
        check_time = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        anomalies_found = $anomalies.Count
        anomalies = $anomalies
        ai_analysis = $ai_analysis
    }
    
    # Save result
    $outputDir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    $result | ConvertTo-Json -Depth 10 | Set-Content $OutputPath -Encoding UTF8
    
    Write-Host "  Anomalies found: $($anomalies.Count)" -ForegroundColor $(if ($anomalies.Count -gt 0) {'Red'} else {'Gray'})
    Write-Host "  Report saved to $OutputPath" -ForegroundColor Green
    
    return $result
}

# Main execution
switch ($Action) {
    "baseline" { Create-AnomalyBaseline }
    "analyze" { Check-Anomalies }
    "alert" { Check-Anomalies }
}