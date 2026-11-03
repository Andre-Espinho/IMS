# Freezes the Python backend into a folder with PyInstaller.
# Output: build-output\backend\ims-backend\ims-backend.exe (+ its _internal folder)
# Native tools (pip, PyInstaller) write progress to stderr; check exit codes instead of that output.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$out = Join-Path $repo 'build-output'

if (-not (Test-Path $python)) { throw "Backend venv not found at $python. Create it first (see README)." }

Push-Location $backend
try {
    & $python -m pip install -q -r requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

    & $python -m PyInstaller --noconfirm --clean --onedir --name ims-backend `
        --distpath (Join-Path $out 'backend') `
        --workpath (Join-Path $out 'pyinstaller-work') `
        --specpath (Join-Path $out 'pyinstaller-spec') `
        --paths . `
        --collect-all uvicorn `
        --collect-all msal `
        --collect-submodules ims `
        --hidden-import multipart `
        run_server.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
}
finally {
    Pop-Location
}

$exe = Join-Path $out 'backend\ims-backend\ims-backend.exe'
if (-not (Test-Path $exe)) { throw "Expected $exe, not found" }
Write-Host "Backend built: $exe"
