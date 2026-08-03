$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"
$Python = "$AI_ROOT\venvs\codeinterpreter\Scripts\python.exe"
$WorkDir = $env:AICARMINE_JUPYTER_WORKDIR
if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_WORKDIR", "User")
}
$TokenFile = $env:AICARMINE_JUPYTER_TOKEN_FILE
if ([string]::IsNullOrWhiteSpace($TokenFile)) {
    $TokenFile = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_TOKEN_FILE", "User")
}
$Port = $env:AICARMINE_JUPYTER_PORT
if ([string]::IsNullOrWhiteSpace($Port)) {
    $Port = [Environment]::GetEnvironmentVariable("AICARMINE_JUPYTER_PORT", "User")
}

if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = $AI_ROOT
}

if ([string]::IsNullOrWhiteSpace($TokenFile)) {
    $TokenFile = "$AI_ROOT\secrets\jupyter_code_token.dpapi"
}

if ([string]::IsNullOrWhiteSpace($Port)) {
    $Port = "8889"
}

if (-not (Test-Path $Python)) {
    throw "Python Code Interpreter non trovato: $Python"
}

$Token = $env:CODE_INTERPRETER_JUPYTER_AUTH_TOKEN
if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = $env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN
}
if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = $env:OPEN_TERMINAL_API_KEY
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    if (-not (Test-Path $TokenFile)) {
        throw "Token Jupyter non trovato: $TokenFile"
    }

    $RawToken = (Get-Content $TokenFile -Raw).Trim()
    if ($RawToken.Length -eq 48 -and $RawToken -match '^[A-Za-z0-9]+$') {
        $Token = $RawToken
    }
    else {
        $SecureToken = ConvertTo-SecureString -String $RawToken
        $Token = [System.Net.NetworkCredential]::new("", $SecureToken).Password
    }
}

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$env:PYTHONHOME = $null
$env:PYTHONPATH = $null
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

Set-Location $WorkDir

& $Python -m jupyter lab `
  --ServerApp.ip=127.0.0.1 `
  --ServerApp.port=$Port `
  --ServerApp.open_browser=False `
  --IdentityProvider.token="$Token" `
  --ServerApp.password="" `
  --ServerApp.allow_origin="http://127.0.0.1:8080" `
  --ServerApp.root_dir="$WorkDir"
