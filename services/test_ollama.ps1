$body = @{
    model    = "qwen3-task-8k"
    messages = @(
        @{ role = "system"; content = "You are a helpful assistant." },
        @{ role = "user"; content = "What is 2+2?" }
    )
    max_tokens = 10
    stream     = $false
} | ConvertTo-Json -Depth 5

Write-Host "Request body:"
Write-Host $body
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -Body $body -ContentType "application/json"
    Write-Host "Response:"
    $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}