# Test Ollama native tool calls
$uri = "http://127.0.0.1:11434/api/chat"
$body = @{
    model = "mio-qwen-code-toolnative:latest"
    messages = @(
        @{
            role = "user"
            content = "test"
        }
    )
    stream = $false
    tools = @(
        @{
            type = "function"
            function = @{
                name = "test"
                description = "test"
                parameters = @{
                    type = "object"
                    properties = @{
                        test = @{type = "string"}
                    }
                }
            }
        }
    )
} | ConvertTo-Json -Compress

$headers = @{
    "Content-Type" = "application/json"
}

try {
    $response = Invoke-RestMethod -Uri $uri -Method POST -Body $body -Headers $headers
    Write-Output "Response: $($response | ConvertTo-Json -Compress)"
} catch {
    Write-Output "Error: $_"
}