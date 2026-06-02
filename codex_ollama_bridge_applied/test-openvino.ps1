$ErrorActionPreference = "Stop"

. "C:\Users\carmi\AI\services\openvino-env.ps1"

$Python = [Environment]::GetEnvironmentVariable("OPENVINO_PYTHON_EXE", "User")

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "C:\Users\carmi\AI\venvs\openvino\Scripts\python.exe"
}

& $Python -c "import openvino as ov; core=ov.Core(); print(core.available_devices)"