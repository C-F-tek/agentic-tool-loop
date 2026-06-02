$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"
$Python = "$AI_ROOT\venvs\codeinterpreter\Scripts\python.exe"
$WorkDir = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_WORKDIR", "User")
$TokenFile = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_TOKEN_FILE", "User")

if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = "$AI_ROOT\code-interpreter-workdir"
}

if ([string]::IsNullOrWhiteSpace($TokenFile)) {
    $TokenFile = "$AI_ROOT\secrets\jupyter_code_token.dpapi"
}

if (-not (Test-Path $Python)) {
    throw "Python Code Interpreter non trovato: $Python"
}

if (-not (Test-Path $TokenFile)) {
    throw "Token Jupyter non trovato: $TokenFile"
}

$RawToken = (Get-Content $TokenFile -Raw).Trim()
$SecureToken = ConvertTo-SecureString -String $RawToken
$Token = [System.Net.NetworkCredential]::new("", $SecureToken).Password

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$env:PYTHONHOME = $null
$env:PYTHONPATH = $null
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

Set-Location $WorkDir

& $Python -m jupyter lab `
  --ServerApp.ip=127.0.0.1 `
  --ServerApp.port=8888 `
  --ServerApp.open_browser=False `
  --IdentityProvider.token="$Token" `
  --ServerApp.password="" `
  --ServerApp.allow_origin="http://127.0.0.1:8080" `
  --ServerApp.root_dir="$WorkDir"
