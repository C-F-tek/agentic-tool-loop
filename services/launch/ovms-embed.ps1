# OVMS Embedding Service Launch Script
# Starts OVMS embedding service on port 3551

$OVMS_EXE = "C:\Users\someo\agentic-tool-loop\ovms-runtime\ovms\ovms.exe"
$CONFIG_PATH = "C:\Users\someo\agentic-tool-loop\services\launch\models-ovms-embed\config.json"
$PORT = 3551

Write-Host "Starting OVMS Embedding Service on port $PORT..."
Write-Host "Config: $CONFIG_PATH"
Write-Host "Binary: $OVMS_EXE"

& $OVMS_EXE `
  --rest_port $PORT `
  --rest_bind_address 127.0.0.1 `
  --config_path $CONFIG_PATH
