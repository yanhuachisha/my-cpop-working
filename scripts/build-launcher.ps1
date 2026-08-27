param(
    [string]$Python = "C:\ide\anaconda\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "launcher\cpop_atlas_launcher.py"
$IconGenerator = Join-Path $Root "scripts\generate-launcher-icon.py"
$Icon = Join-Path $Root "launcher\assets\my-c-pop-working.ico"
$BuildRoot = Join-Path $Root ".launcher-build"
$Dist = Join-Path $BuildRoot "dist"
$Work = Join-Path $BuildRoot "work"
$Spec = Join-Path $BuildRoot "spec"
$Target = Join-Path $Root "My-C-Pop-Working.exe"
$DesktopTarget = Join-Path ([Environment]::GetFolderPath("Desktop")) "My-C-Pop-Working.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python not found: $Python"
}

$PyInstallerAvailable = & $Python -c "import importlib.util; print('yes' if importlib.util.find_spec('PyInstaller') else 'no')"
if ($PyInstallerAvailable.Trim() -ne "yes") {
    & $Python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
}

$PillowAvailable = & $Python -c "import importlib.util; print('yes' if importlib.util.find_spec('PIL') else 'no')"
if ($PillowAvailable.Trim() -ne "yes") {
    & $Python -m pip install pillow
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Pillow." }
}

& $Python $IconGenerator
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Icon)) {
    throw "Launcher icon generation failed."
}

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "My-C-Pop-Working" `
    --icon $Icon `
    --distpath $Dist `
    --workpath $Work `
    --specpath $Spec `
    $Source
if ($LASTEXITCODE -ne 0) { throw "Launcher build failed." }

Copy-Item -LiteralPath (Join-Path $Dist "My-C-Pop-Working.exe") -Destination $Target -Force
if ([Environment]::GetFolderPath("Desktop")) {
    Copy-Item -LiteralPath $Target -Destination $DesktopTarget -Force
    Write-Host "Built: $Target"
    Write-Host "Desktop copy: $DesktopTarget"
} else {
    Write-Host "Built: $Target"
}
