$body = @{
    task      = "Qual è la capitale della Francia?"
    max_steps = 3
} | ConvertTo-Json -Depth 5

Write-Host "Request body:"
Write-Host $body
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:3572/planner-lab/start" -Method Post -Body $body -ContentType "application/json"
    Write-Host "Response:"
    $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Error: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $respBody = $reader.ReadToEnd()
        Write-Host "Response body: $respBody"
        $reader.Close()
        $stream.Close()
    }
}