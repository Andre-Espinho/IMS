# Builds the Windows installer end to end:
#   1. backend tests
#   2. frozen backend (PyInstaller)
#   3. frontend build + Electron installer (electron-builder)
# Output: release\IMS Setup <version>.exe
$ErrorActionPreference = 'Continue'  # native tools write progress to stderr; check exit codes
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo 'backend'
$frontend = Join-Path $repo 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$npm = 'C:\Program Files\nodejs\npm.cmd'
if (-not (Test-Path $npm)) { $npm = 'npm.cmd' }
# npm run calls npm and node by name, so Node's folder must be on PATH.
$env:Path = (Split-Path $npm) + ';' + $env:Path

function Step($name, [scriptblock]$body) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { throw "Failed: $name (exit $LASTEXITCODE)" }
}

Step 'Backend tests' {
    Push-Location $backend
    $env:PYTHONPATH = '.'
    & $python -m pytest -q tests
    Pop-Location
}

Step 'Freeze backend' { & (Join-Path $PSScriptRoot 'build-backend.ps1') }

Step 'Install frontend dependencies' {
    Push-Location $frontend
    & $npm install
    Pop-Location
}

Step 'Build installer' {
    Push-Location $frontend
    # No code-signing certificate yet: skip signing so the build does not look for one.
    $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
    & $npm run dist
    Pop-Location
}

$installer = Get-ChildItem (Join-Path $repo 'release') -Filter 'IMS Setup *.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $installer) { throw 'Installer not found in release\' }
Write-Host "Installer ready: $($installer.FullName)" -ForegroundColor Green
