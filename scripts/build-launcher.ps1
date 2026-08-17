param(
    [string]$Python = "C:\ide\anaconda\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "launcher\cpop_atlas_launcher.py"
$BuildRoot = Join-Path $Root ".launcher-build"
$Dist = Join-Path $BuildRoot "dist"
$Work = Join-Path $BuildRoot "work"
$Spec = Join-Path $BuildRoot "spec"
$Target = Join-Path $Root "C-Pop-Atlas.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python not found: $Python"
}

$PyInstallerAvailable = & $Python -c "import importlib.util; print('yes' if importlib.util.find_spec('PyInstaller') else 'no')"
if ($PyInstallerAvailable.Trim() -ne "yes") {
    & $Python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
}

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "C-Pop-Atlas" `
    --distpath $Dist `
    --workpath $Work `
    --specpath $Spec `
    $Source
if ($LASTEXITCODE -ne 0) { throw "Launcher build failed." }

Copy-Item -LiteralPath (Join-Path $Dist "C-Pop-Atlas.exe") -Destination $Target -Force
Write-Host "Built: $Target"
