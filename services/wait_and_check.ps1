Start-Sleep -Seconds 15
$response = Invoke-RestMethod -Uri "http://127.0.0.1:3572/jobs.json" -Method Get
$job = $response.jobs | Where-Object {$_.job_id -eq "job-5db0016f"}
Write-Host "Status: $($job.status)"
Write-Host "Updated: $($job.updated_at)"