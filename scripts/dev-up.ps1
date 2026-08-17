param(
    [int]$ApiPort = 8001,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$ApiUrl = "http://localhost:$ApiPort"

Write-Host "Starting C-Pop Atlas API on $ApiUrl"
Start-Process `
    -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$ApiPort" `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden

Start-Sleep -Seconds 2

Write-Host "Starting C-Pop Atlas web on http://localhost:$WebPort"
$Command = "set `"NEXT_PUBLIC_API_BASE_URL=$ApiUrl`" && npm run dev -- --hostname 0.0.0.0 --port $WebPort"
Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/d", "/s", "/c", $Command `
    -WorkingDirectory $FrontendDir `
    -WindowStyle Hidden

Write-Host "Done. Open http://localhost:$WebPort"
