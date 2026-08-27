$dest = "$env:APPDATA\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json"
$dir = [System.IO.Path]::GetDirectoryName($dest)

if (!(Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

Copy-Item -Path "mcp.json" -Destination $dest -Force

Write-Output "Installed MCP settings to: $dest"