$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$VenvPython = Join-Path "venv" "Scripts/python.exe"

if (-not (Test-Path $VenvPython)) {
    & $Python -c "import sys; raise SystemExit('Python 3.11+ is required') if sys.version_info < (3, 11) else None"
    & $Python -m venv venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if (-not (Test-Path "runtime/windows-amd64/sing-box.exe") -or -not (Test-Path "runtime/windows-amd64/libcronet.dll")) {
    ./scripts/fetch_runtime_windows.ps1 -Arch amd64
}

& $VenvPython -m PyInstaller --clean -y specs/windows.spec

$ReleaseDir = "release"
$StageDir = Join-Path $ReleaseDir "WorkVPN-windows-amd64"
$ZipPath = Join-Path $ReleaseDir "WorkVPN-windows-amd64.zip"
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null
Remove-Item -Recurse -Force $StageDir -ErrorAction SilentlyContinue
Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $StageDir | Out-Null
Copy-Item "dist/WorkVPN.exe" $StageDir
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
Write-Host "Release: $ZipPath"
