# Compatibility wrapper for the AI-Carmine OpenWebUI launcher.
#
# Runtime implementation moved to services\launch\openwebui_runtime.ps1 so this
# historical root path remains stable for shortcuts and hard-coded references.

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

. (Join-Path $ScriptRoot "launch\env.ps1")
. (Join-Path $ScriptRoot "launch\http.ps1")
. (Join-Path $ScriptRoot "launch\process.ps1")
. (Join-Path $ScriptRoot "launch\ollama.ps1")
. (Join-Path $ScriptRoot "launch\openwebui_runtime.ps1")

