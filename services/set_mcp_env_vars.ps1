#!/usr/bin/env pwsh
# Set persistent environment variables for MCP compression and configuration
# Run this script to configure user-level environment variables

$variables = @(
    @{ Name = "AICARMINE_REPO_MCP_COMPRESSION"; Value = "1" },
    @{ Name = "AICARMINE_REPO_MMP_MAX_TEXT_CHARS"; Value = "24000" },
    @{ Name = "AICARMINE_REPO_MMP_STDIO_TRANSPORT"; Value = "content-length" }
)

foreach ($v in $variables) {
    [Environment]::SetEnvironmentVariable($v.Name, $v.Value, "User")
    Write-Host ("Set: " + $v.Name + "=" + $v.Value)
}

Write-Host ""
Write-Host "Persistent environment variables set successfully."
Write-Host "These will be available on next shell session."
Write-Host ""
Write-Host "To verify, run:"
Write-Host "  [Environment]::GetEnvironmentVariable('AICARMINE_REPO_MCP_COMPRESSION','User')"