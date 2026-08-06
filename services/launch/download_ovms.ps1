# Download and extract OVMS
$ovmsUrl = "https://github.com/openvinotoolkit/open_model_server/releases/download/v2024.3.0/ovms-win-2024.3.0.zip"
$ovmsZip = "$env:TEMP\ovms.zip"
$ovmsDest = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\bin"

Write-Host "Downloading OVMS from: $ovmsUrl"
Invoke-WebRequest -Uri $ovmsUrl -OutFile $ovmsZip -UseBasicParsing
Write-Host "Extracting to: $ovmsDest"
Expand-Archive -Path $ovmsZip -DestinationPath $ovmsDest -Force
Remove-Item $ovmsZip -Force
Write-Host "OVMS downloaded successfully"