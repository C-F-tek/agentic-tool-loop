$procs = Get-Process | Where-Object {$_.Path -like '*ovms.exe'}
if ($procs) {
    $procs | Select-Object Id,ProcessName,StartTime,WorkingSet | Format-Table -AutoSize
} else {
    Write-Host "No ovms.exe process found"
}

# Also check ports
Get-NetTCPConnection -LocalPort 3550 -ErrorAction SilentlyContinue | Select-Object LocalPort,State,OwningProcess | Format-Table -AutoSize