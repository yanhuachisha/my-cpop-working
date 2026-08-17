param(
    [ValidateSet("start", "stop", "status", "install")]
    [string]$Action = "start",
    [int]$Port = 9191
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LocalRoot = Join-Path $Root ".local"
$BridgeDir = Join-Path $LocalRoot "kugou-bridge"
$PidFile = Join-Path $LocalRoot "kugou-bridge.pid"
$OutLog = Join-Path $LocalRoot "kugou-bridge.out.log"
$ErrLog = Join-Path $LocalRoot "kugou-bridge.err.log"
$Repository = "https://github.com/Yu9191/KuGou.git"

function Get-BridgeConnection {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Install-Bridge {
    New-Item -ItemType Directory -Force -Path $LocalRoot | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $BridgeDir ".git"))) {
        Write-Host "Cloning optional Yu9191/KuGou metadata bridge..."
        git clone --depth 1 $Repository $BridgeDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to clone Kugou bridge." }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $BridgeDir "node_modules"))) {
        Write-Host "Installing bridge dependencies..."
        Push-Location $BridgeDir
        try {
            npm.cmd install --omit=dev
            if ($LASTEXITCODE -ne 0) { throw "Failed to install Kugou bridge dependencies." }
        }
        finally {
            Pop-Location
        }
    }
}

if ($Action -eq "status") {
    $Connection = Get-BridgeConnection
    if ($Connection) {
        Write-Host "Kugou metadata bridge is online at http://127.0.0.1:$Port (PID $($Connection.OwningProcess))."
    }
    else {
        Write-Host "Kugou metadata bridge is offline."
    }
    exit 0
}

if ($Action -eq "stop") {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "No managed bridge PID file found; nothing was stopped."
        exit 0
    }
    $ManagedPid = [int](Get-Content -Raw -LiteralPath $PidFile)
    $Connection = Get-BridgeConnection
    if ($Connection -and $Connection.OwningProcess -eq $ManagedPid) {
        Stop-Process -Id $ManagedPid -Force
        Write-Host "Kugou metadata bridge stopped."
    }
    else {
        Write-Host "The saved PID does not own port $Port; nothing was stopped."
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

Install-Bridge
if ($Action -eq "install") {
    Write-Host "Bridge installed at $BridgeDir."
    exit 0
}

$Existing = Get-BridgeConnection
if ($Existing) {
    Write-Host "Port $Port is already in use (PID $($Existing.OwningProcess)); bridge start skipped."
    exit 0
}

$env:PORT = "$Port"
$Process = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList "start" `
    -WorkingDirectory $BridgeDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Start-Sleep -Seconds 4
$Connection = Get-BridgeConnection
if (-not $Connection) {
    throw "Bridge did not start. Check $ErrLog."
}

Set-Content -LiteralPath $PidFile -Value $Connection.OwningProcess -Encoding Ascii
Write-Host "Kugou metadata bridge is online at http://127.0.0.1:$Port."
Write-Host "Only metadata search is used by C-Pop Atlas; audio and full lyrics stay disabled."
