# Network Monitor Continuous Script
# Runs continuous packet capture with auto-blocking of malicious IPs
# Usage: .\network_monitor_continuous.ps1
# NOTE: Each call is independent - state resets between calls

param(
    [string]$Interface = "Wi-Fi",
    [int]$CaptureDuration = 60,
    [int]$Threshold = 2,
    [int]$LoopInterval = 10,
    [int]$MaxRuns = 100
)

function Invoke-NetworkCapture {
    param(
        [string]$Interface,
        [int]$Duration,
        [int]$Threshold
    )
    
    $jsonRequest = @{
        jsonrpc = "2.0"
        id = 100
        method = "tools/call"
        params = @{
            name = "network_capture_start"
            arguments = @{
                interface = $Interface
                duration = $Duration
                threshold = $Threshold
            }
        }
    } | ConvertTo-Json -Depth 10
    
    $result = echo $jsonRequest | python -u "$PSScriptRoot\..\codex_bridge\network_monitor_mcp_server.py" 2>$null
    return $result
}

function Get-ThreatList {
    $threatJson = @{
        jsonrpc = "2.0"
        id = 101
        method = "tools/call"
        params = @{
            name = "network_threat_list"
            arguments = @{ limit = 50 }
        }
    } | ConvertTo-Json -Depth 10
    
    $threatResult = echo $threatJson | python -u "$PSScriptRoot\..\codex_bridge\network_monitor_mcp_server.py" 2>$null
    return $threatResult
}

function Get-FirewallRules {
    $blockedJson = @{
        jsonrpc = "2.0"
        id = 102
        method = "tools/call"
        params = @{
            name = "network_firewall_list_rules"
            arguments = @{}
        }
    } | ConvertTo-Json -Depth 10
    
    $blockedResult = echo $blockedJson | python -u "$PSScriptRoot\..\codex_bridge\network_monitor_mcp_server.py" 2>$null
    return $blockedResult
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Network Monitor Continuous" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Interface: $Interface" -ForegroundColor White
Write-Host "  Capture Duration: ${CaptureDuration}s" -ForegroundColor White
Write-Host "  Threshold: $Threshold" -ForegroundColor White
Write-Host "  Loop Interval: ${LoopInterval}s" -ForegroundColor White
Write-Host "  Max Runs: $MaxRuns" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Each capture is independent. State resets between calls." -ForegroundColor Magenta
Write-Host ""

$runCount = 0
$threatsFound = 0
$ipsBlocked = 0

while ($runCount -lt $MaxRuns) {
    $runCount++
    Write-Host "`n[$runCount/$MaxRuns] Starting capture..." -ForegroundColor Cyan
    
    $result = Invoke-NetworkCapture -Interface $Interface -Duration $CaptureDuration -Threshold $Threshold
    
    if ($result -and $result.Contains('"ok": true') -and $result.Contains('Capture started')) {
        Write-Host "  Capture started successfully" -ForegroundColor Green
    } else {
        Write-Host "  Capture failed or already running" -ForegroundColor Red
    }
    
    # Wait for capture to complete
    Write-Host "  Waiting ${CaptureDuration}s for capture..." -ForegroundColor Gray
    Start-Sleep -Seconds $CaptureDuration
    
    # Check for threats
    $threatResult = Get-ThreatList
    
    if ($threatResult -and $threatResult.Contains('"total":')) {
        if ($threatResult -match '"total":\s*(\d+)') {
            $totalThreats = [int]$Matches[1]
            if ($totalThreats -gt 0) {
                $threatsFound += $totalThreats
                Write-Host "  THREATS DETECTED: $totalThreats" -ForegroundColor Red
                
                # Check blocked IPs
                $blockedResult = Get-FirewallRules
                if ($blockedResult -and $blockedResult.Contains('Block-')) {
                    $ipsBlocked++
                    Write-Host "  FIREWALL RULES ACTIVE: $ipsBlocked" -ForegroundColor Green
                }
            } else {
                Write-Host "  No threats detected" -ForegroundColor Gray
            }
        }
    }
    
    Write-Host "  Capture complete. Waiting ${LoopInterval}s before next run..." -ForegroundColor Cyan
    Start-Sleep -Seconds $LoopInterval
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  Summary" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Total runs: $runCount" -ForegroundColor White
Write-Host "  Total threats found: $threatsFound" -ForegroundColor $(if ($threatsFound -gt 0) {'Red'} else {'Gray'})
Write-Host "  Total IPs blocked: $ipsBlocked" -ForegroundColor $(if ($ipsBlocked -gt 0) {'Green'} else {'Gray'})
Write-Host ""
Write-Host "Monitor completed." -ForegroundColor Cyan
