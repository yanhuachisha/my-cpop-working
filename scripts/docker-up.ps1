param(
  [switch]$WithDb
)

$ErrorActionPreference = "Stop"
$dockerBinDir = "C:\Program Files\Docker\Docker\resources\bin"
$dockerExe = Join-Path $dockerBinDir "docker.exe"

if (-not (Test-Path $dockerExe)) {
  throw "Docker Desktop is not installed or docker.exe was not found at $dockerExe"
}

$env:PATH = "$dockerBinDir;$env:PATH"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($WithDb) {
  & $dockerExe compose --profile db up --build
} else {
  & $dockerExe compose up --build
}
