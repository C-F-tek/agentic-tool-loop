$response = Invoke-RestMethod -Uri "http://127.0.0.1:3572/jobs/job-5db0016f" -Method Get
$response | ConvertTo-Json -Depth 3