# Test Ollama native tool calls with correct format
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
} | ConvertTo-Json -Depth 10

Write-Output "Body: $body"

$headers = @{
    "Content-Type" = "application/json"
}

try {
    $response = Invoke-RestMethod -Uri $uri -Method POST -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -Headers $headers
    Write-Output "Response: $($response | ConvertTo-Json -Depth 10 -Compress)"
} catch {
    Write-Output "Error: $_"
}